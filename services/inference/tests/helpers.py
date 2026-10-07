"""Shared helpers for the job queue and job API tests."""

import threading
import time
from collections.abc import Callable

from app import db
from app.pipeline import PipelineResult, Stage

METADATA = {
    "width": 2000,
    "height": 1000,
    "level_count": 3,
    "mpp_x": None,
    "mpp_y": None,
}


def add_ready_slide(db_path, name: str = "slide.tif") -> str:
    """Insert a ready slide row and return its ID."""
    slide_id = db.ensure_arriving(db_path, f"/acq/{name}", "2026-10-07T14:00:00Z")
    db.mark_ready(db_path, slide_id, "a" * 64, METADATA, "2026-10-07T14:00:08Z")
    return slide_id


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    """Poll a condition until it is true; fail the test after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


def job_status(db_path, job_id: str) -> str:
    """A job's status as stored in SQLite."""
    return db.get_job(db_path, job_id)["status"]


class GatedPipeline:
    """Fake pipeline: records each call, reports one stage, waits for release()."""

    def __init__(self) -> None:
        """Start with the gate closed."""
        self.calls: list[str] = []
        self.max_active = 0
        self._active = 0
        self._lock = threading.Lock()
        self._gate = threading.Event()

    def __call__(self, slide, report) -> PipelineResult:
        """Run one fake job; blocks until release() has been called."""
        with self._lock:
            self.calls.append(slide["id"])
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            report(Stage.SEGMENTING)
            if not self._gate.wait(5):
                raise TimeoutError("test never released the pipeline")
            return PipelineResult(result=None)
        finally:
            with self._lock:
                self._active -= 1

    def release(self) -> None:
        """Let the current and all later jobs finish."""
        self._gate.set()
