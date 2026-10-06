"""SQLite access with the standard-library sqlite3 module (D-016).

Schema: docs/api-contract.md. This item creates the `slides` table; the
`jobs` table arrives with the job queue (roadmap item 5).

Every operation opens its own short-lived connection. The registry poller
thread and the API's request threads therefore never share a connection
object (sqlite3 connections must not be shared across threads by default).
WAL journal mode lets readers keep reading while the poller writes.
"""

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
"""


class SlideStatus(StrEnum):
    """Lifecycle of a slide file in the acquisition folder."""

    ARRIVING = "arriving"  # seen, still waiting for its size to settle
    REGISTERING = "registering"  # hashing and reading metadata
    READY = "ready"
    UNREADABLE = "unreadable"


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
