"""FIFO job queue with a single worker thread (REQ-008 to REQ-010, REQ-017).

    POST /v1/jobs --submit()--> SQLite row (queued) + queue.Queue
                                        |
                        one "job-worker" thread (D-005)
                                        |
                pipeline(slide, report) --report()--> in-memory JobState
                                        |               (SSE reads this)
                          SQLite row (completed | failed)

Two copies of progress exist on purpose (D-034):
- The in-memory JobState is updated on every report() and carries a
  version number. SSE streams poll it and send an event when the version
  changes.
- SQLite is the durable copy. Progress is written there at most about once
  per second (and on every stage change), so a fast pipeline doesn't turn
  into thousands of disk writes.

When a job finishes, its final row is written to SQLite *before* its
JobState is dropped. So when a reader finds no JobState for a job, the
database row is already final.

On startup, jobs left queued or running are failed with INTERRUPTED
(REQ-009); see app/main.py. Nothing is ever retried (REQ-017).
"""

import dataclasses
import logging
import queue
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.db import JobStatus
from app.errors import ErrorCode
from app.pipeline import Pipeline, PipelineError, Stage

logger = logging.getLogger(__name__)

DB_WRITE_INTERVAL_S = 1.0
INTERRUPTED_MESSAGE = "The service restarted before the job finished"
INFERENCE_FAILED_MESSAGE = "Analysis failed"


@dataclass(frozen=True)
class JobState:
    """Latest in-memory progress of an active job; replaced, never mutated."""

    # Frozen, so a snapshot handed to another thread can't change under it.
    status: JobStatus
    stage: str | None = None
    done: int | None = None
    total: int | None = None
    version: int = 0


class _Stopping(Exception):
    """Raised inside report() when the service is shutting down."""


class _Reporter:
    """The `report` callback for one job: updates memory, throttles DB writes."""

    def __init__(self, jobs: "JobQueue", job_id: str) -> None:
        """Bind the reporter to its queue and job."""
        self._jobs = jobs
        self._job_id = job_id
        self._last_write: float | None = None
        self._written_stage: str | None = None
        self._unwritten = False

    def __call__(
        self, stage: Stage, done: int | None = None, total: int | None = None
    ) -> None:
        """Publish progress; raise _Stopping if the service is shutting down."""
        # Checking here gives the pipeline a safe point to stop at: between
        # two steps, never in the middle of one.
        if self._jobs._stop.is_set():
            raise _Stopping
        self._jobs._update_state(self._job_id, stage=stage, done=done, total=total)
        self._unwritten = True
        now = self._jobs._clock()
        due = self._last_write is None or (
            now - self._last_write >= self._jobs._db_write_interval
        )
        if stage != self._written_stage or due:
            self.flush()
            self._last_write = now

    def flush(self) -> None:
        """Write the latest in-memory progress to SQLite if it isn't there yet."""
        if not self._unwritten:
            return
        state = self._jobs.snapshot(self._job_id)
        if state is None:
            return
        db.update_job_progress(
            self._jobs._db_path, self._job_id, state.stage, state.done, state.total
        )
        self._written_stage = state.stage
        self._unwritten = False


class JobQueue:
    """Runs analysis jobs one at a time, in submission order."""

    def __init__(
        self,
        db_path: Path,
        pipeline: Pipeline,
        *,
        clock: Callable[[], float] = time.monotonic,
        db_write_interval: float = DB_WRITE_INTERVAL_S,
    ) -> None:
        """Configure the queue; no jobs run until start()."""
        self._db_path = db_path
        self._pipeline = pipeline
        self._clock = clock
        self._db_write_interval = db_write_interval
        # queue.Queue is first-in, first-out and safe to use from request
        # threads and the worker thread at the same time.
        # None is a wake-up sentinel put there by stop().
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._states: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the worker thread."""
        self._thread = threading.Thread(
            target=self._run, name="job-worker", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the worker to stop at the next safe point and wait for it."""
        self._stop.set()
        self._queue.put(None)  # wake the worker if it is waiting for a job
        if self._thread is not None:
            self._thread.join(timeout)

    def submit(self, slide_id: str) -> sqlite3.Row:
        """Create a queued job for a slide and return its row as created.

        Raises sqlite3.IntegrityError if the slide already has an active job.
        """
        job_id = db.insert_job(self._db_path, slide_id, db.utc_now_iso())
        # Read the row before queueing it, so the caller always gets the
        # `queued` row even if the worker starts the job immediately.
        row = db.get_job(self._db_path, job_id)
        # State before the queue: the worker expects to find the state.
        with self._lock:
            self._states[job_id] = JobState(status=JobStatus.QUEUED)
        self._queue.put(job_id)
        logger.info("Job %s queued for slide %s", job_id, slide_id)
        return row

    def snapshot(self, job_id: str) -> JobState | None:
        """The latest in-memory state of an active job, or None once it has finished."""
        with self._lock:
            return self._states.get(job_id)

    def _update_state(self, job_id: str, **changes) -> None:
        """Replace a job's state with the given fields changed and the version bumped."""
        with self._lock:
            old = self._states[job_id]
            self._states[job_id] = dataclasses.replace(
                old, **changes, version=old.version + 1
            )

    def _run(self) -> None:
        """Thread body: take the next job ID off the queue and run it."""
        logger.info("Job worker started")
        while True:
            job_id = self._queue.get()  # blocks until a job or stop()
            if self._stop.is_set():
                # Jobs still queued stay `queued` in SQLite; the next
                # startup marks them INTERRUPTED (REQ-009).
                break
            try:
                self._run_job(job_id)
            except Exception as exc:  # noqa: BLE001 - the worker must keep running
                logger.error("Job %s worker error: %s", job_id, type(exc).__name__)

    def _run_job(self, job_id: str) -> None:
        """Run one job through the pipeline and store how it ended."""
        try:
            job = db.get_job(self._db_path, job_id)
            slide_id = job["slide_id"]
            slide = db.get_slide(self._db_path, slide_id)
            db.mark_job_running(self._db_path, job_id, db.utc_now_iso())
            self._update_state(job_id, status=JobStatus.RUNNING)
            logger.info("Job %s started for slide %s", job_id, slide_id)

            reporter = _Reporter(self, job_id)
            started = time.monotonic()
            try:
                outcome = self._pipeline(slide, reporter, job_id=job_id)
            except PipelineError as exc:
                reporter.flush()
                self._fail(job_id, slide_id, exc.code, exc.message)
            except _Stopping:
                reporter.flush()
                self._fail(job_id, slide_id, ErrorCode.INTERRUPTED, INTERRUPTED_MESSAGE)
            except Exception as exc:  # noqa: BLE001 - any other failure is INFERENCE_FAILED
                # Fixed message and exception type only: exception text can
                # contain file paths (REQ-006).
                logger.error(
                    "Job %s pipeline error for slide %s: %s",
                    job_id,
                    slide_id,
                    type(exc).__name__,
                )
                reporter.flush()
                self._fail(
                    job_id,
                    slide_id,
                    ErrorCode.INFERENCE_FAILED,
                    INFERENCE_FAILED_MESSAGE,
                )
            else:
                reporter.flush()
                db.mark_job_completed(
                    self._db_path,
                    job_id,
                    db.utc_now_iso(),
                    outcome.result,
                    outcome.models,
                    outcome.timings_s,
                )
                logger.info(
                    "Job %s completed for slide %s in %.1f s",
                    job_id,
                    slide_id,
                    time.monotonic() - started,
                )
        finally:
            # Only after the final DB write (see the module docstring).
            with self._lock:
                self._states.pop(job_id, None)

    def _fail(self, job_id: str, slide_id: str, code: ErrorCode, message: str) -> None:
        """Mark a job failed; no retry (REQ-017)."""
        db.mark_job_failed(self._db_path, job_id, db.utc_now_iso(), code, message)
        logger.warning("Job %s failed for slide %s: %s", job_id, slide_id, code)
