"""SQLite access with the standard-library sqlite3 module (D-016).

Schema: docs/api-contract.md. Tables: `slides` (registry) and `jobs`
(job queue).

Every operation opens its own short-lived connection. The registry poller
thread and the API's request threads therefore never share a connection
object (sqlite3 connections must not be shared across threads by default).
WAL journal mode lets readers keep reading while the poller writes.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

DB_FILENAME = "device.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS slides (
  id            TEXT PRIMARY KEY,
  file_path     TEXT NOT NULL UNIQUE,
  sha256        TEXT,
  status        TEXT NOT NULL,
  width         INTEGER,
  height        INTEGER,
  level_count   INTEGER,
  mpp_x         REAL,
  mpp_y         REAL,
  detected_at   TEXT NOT NULL,
  registered_at TEXT,
  error_code    TEXT,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id             TEXT PRIMARY KEY,
  slide_id       TEXT NOT NULL REFERENCES slides(id),
  status         TEXT NOT NULL,
  stage          TEXT,
  progress_done  INTEGER,
  progress_total INTEGER,
  error_code     TEXT,
  error_message  TEXT,
  created_at     TEXT NOT NULL,
  started_at     TEXT,
  finished_at    TEXT,
  models_json    TEXT,
  timings_json   TEXT,
  result_json    TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_slide ON jobs(slide_id, created_at);

-- At most one queued or running job per slide (D-033). A partial index
-- covers only the rows matching its WHERE clause, so finished jobs don't
-- count. The database rejects a second active job with IntegrityError,
-- even if two requests insert at the same moment.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_active
  ON jobs(slide_id) WHERE status IN ('queued', 'running');
"""


class SlideStatus(StrEnum):
    """Lifecycle of a slide file in the acquisition folder."""

    ARRIVING = "arriving"  # seen, still waiting for its size to settle
    REGISTERING = "registering"  # hashing and reading metadata
    READY = "ready"
    UNREADABLE = "unreadable"


class JobStatus(StrEnum):
    """Lifecycle of an analysis job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def utc_now_iso() -> str:
    """Current time as ISO 8601 UTC with a trailing Z, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success (roll back on error), always close."""
    # timeout: wait up to 5 s for another connection's write lock instead
    # of failing immediately with "database is locked".
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row  # rows readable by column name
    try:
        # `with conn` handles the transaction only; it does not close.
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Create the data directory and tables if missing; enable WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        # WAL is stored in the database file, so setting it once persists.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def ensure_arriving(db_path: Path, file_path: str, detected_at: str) -> str:
    """Return the slide ID for a path, inserting an `arriving` row if new."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM slides WHERE file_path = ?", (file_path,)
        ).fetchone()
        if row is not None:
            # Left over from a restart mid-registration: start over.
            conn.execute(
                "UPDATE slides SET status = ? WHERE id = ?",
                (SlideStatus.ARRIVING, row["id"]),
            )
            return row["id"]
        slide_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO slides (id, file_path, status, detected_at)"
            " VALUES (?, ?, ?, ?)",
            (slide_id, file_path, SlideStatus.ARRIVING, detected_at),
        )
        return slide_id


def set_status(db_path: Path, slide_id: str, status: SlideStatus) -> None:
    """Change a slide's status without touching other columns."""
    with connect(db_path) as conn:
        conn.execute("UPDATE slides SET status = ? WHERE id = ?", (status, slide_id))


def mark_ready(
    db_path: Path, slide_id: str, sha256: str, metadata: dict, registered_at: str
) -> None:
    """Store hash and allowlisted metadata and mark the slide ready."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE slides SET status = ?, sha256 = ?, width = ?, height = ?,"
            " level_count = ?, mpp_x = ?, mpp_y = ?, registered_at = ?,"
            " error_code = NULL, error_message = NULL WHERE id = ?",
            (
                SlideStatus.READY,
                sha256,
                metadata["width"],
                metadata["height"],
                metadata["level_count"],
                metadata["mpp_x"],
                metadata["mpp_y"],
                registered_at,
                slide_id,
            ),
        )


def mark_unreadable(
    db_path: Path, slide_id: str, sha256: str, code: str, message: str
) -> None:
    """Store the hash and an error, and mark the slide unreadable."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE slides SET status = ?, sha256 = ?, error_code = ?,"
            " error_message = ? WHERE id = ?",
            (SlideStatus.UNREADABLE, sha256, code, message, slide_id),
        )


def paths_with_status(db_path: Path, statuses: Iterable[SlideStatus]) -> set[str]:
    """File paths of all slides currently in one of the given statuses."""
    statuses = list(statuses)
    placeholders = ", ".join("?" * len(statuses))
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT file_path FROM slides WHERE status IN ({placeholders})",
            statuses,
        ).fetchall()
    return {row["file_path"] for row in rows}


def get_slide(db_path: Path, slide_id: str) -> sqlite3.Row | None:
    """One slide row by ID, or None."""
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM slides WHERE id = ?", (slide_id,)).fetchone()


def list_slides(db_path: Path) -> list[sqlite3.Row]:
    """All slide rows, most recently detected first."""
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM slides ORDER BY detected_at DESC, id"
        ).fetchall()


def insert_job(db_path: Path, slide_id: str, created_at: str) -> str:
    """Insert a `queued` job and return its ID.

    Raises sqlite3.IntegrityError if the slide already has an active job.
    """
    job_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (id, slide_id, status, created_at) VALUES (?, ?, ?, ?)",
            (job_id, slide_id, JobStatus.QUEUED, created_at),
        )
    return job_id


def get_job(db_path: Path, job_id: str) -> sqlite3.Row | None:
    """One job row by ID, or None."""
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_jobs(db_path: Path, slide_id: str | None = None) -> list[sqlite3.Row]:
    """Job rows, newest first; only one slide's jobs if `slide_id` is given."""
    # created_at is to the second, so rowid (insertion order) breaks ties.
    with connect(db_path) as conn:
        if slide_id is None:
            return conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM jobs WHERE slide_id = ?"
            " ORDER BY created_at DESC, rowid DESC",
            (slide_id,),
        ).fetchall()


# The job updates below include the expected current status in their WHERE
# clause, so a late or repeated write can never change a finished job.


def mark_job_running(db_path: Path, job_id: str, started_at: str) -> None:
    """Move a queued job to `running`."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, started_at = ? WHERE id = ? AND status = ?",
            (JobStatus.RUNNING, started_at, job_id, JobStatus.QUEUED),
        )


def update_job_progress(
    db_path: Path, job_id: str, stage: str, done: int | None, total: int | None
) -> None:
    """Store a running job's stage and patch counts."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET stage = ?, progress_done = ?, progress_total = ?"
            " WHERE id = ? AND status = ?",
            (stage, done, total, job_id, JobStatus.RUNNING),
        )


def mark_job_completed(
    db_path: Path,
    job_id: str,
    finished_at: str,
    result: dict | None,
    models: list[dict],
    timings_s: dict,
) -> None:
    """Store a running job's result, models, and timings and mark it completed."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, result_json = ?,"
            " models_json = ?, timings_json = ? WHERE id = ? AND status = ?",
            (
                JobStatus.COMPLETED,
                finished_at,
                None if result is None else json.dumps(result),
                json.dumps(models),
                json.dumps(timings_s),
                job_id,
                JobStatus.RUNNING,
            ),
        )


def mark_job_failed(
    db_path: Path, job_id: str, finished_at: str, code: str, message: str
) -> None:
    """Mark a queued or running job failed with an error code and message."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, error_code = ?,"
            " error_message = ? WHERE id = ? AND status IN (?, ?)",
            (
                JobStatus.FAILED,
                finished_at,
                code,
                message,
                job_id,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
            ),
        )


def interrupt_unfinished_jobs(
    db_path: Path, code: str, message: str, finished_at: str
) -> int:
    """Fail every queued or running job with the given code; return how many."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, error_code = ?,"
            " error_message = ? WHERE status IN (?, ?)",
            (
                JobStatus.FAILED,
                finished_at,
                code,
                message,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
            ),
        )
        return cursor.rowcount


def count_active_jobs(db_path: Path) -> tuple[int, int]:
    """Number of (running, queued) jobs."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM jobs WHERE status IN (?, ?)"
            " GROUP BY status",
            (JobStatus.RUNNING, JobStatus.QUEUED),
        ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}
    return counts.get(JobStatus.RUNNING, 0), counts.get(JobStatus.QUEUED, 0)
