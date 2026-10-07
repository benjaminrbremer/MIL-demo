"""JobQueue and worker tests, without HTTP (REQ-008, REQ-009, REQ-010, REQ-017)."""

import logging

import pytest

from app import db
from app.db import JobStatus
from app.errors import ErrorCode
from app.jobs import INFERENCE_FAILED_MESSAGE, JobQueue
from app.pipeline import PipelineError, PipelineResult, Stage
from app.pipeline.stub import FAKE_PATCH_COUNT, stub_pipeline
from tests.fakes import PHI_NAME
from tests.helpers import GatedPipeline, add_ready_slide, job_status, wait_until


@pytest.fixture
def db_path(tmp_path):
    """A fresh database with the full schema."""
    path = tmp_path / "data" / db.DB_FILENAME
    db.init_db(path)
    return path


@pytest.fixture
def make_queue(db_path):
    """Factory for started JobQueues; every queue is stopped after the test."""
    queues = []

    def make(pipeline, **kwargs) -> JobQueue:
        """Start a queue that runs `pipeline`."""
        jobs = JobQueue(db_path, pipeline, **kwargs)
        jobs.start()
        queues.append(jobs)
        return jobs

    yield make
    for jobs in queues:
        jobs.stop()


def finished(db_path, *job_ids) -> bool:
    """True when every given job is completed or failed."""
    return all(
        job_status(db_path, job_id) in (JobStatus.COMPLETED, JobStatus.FAILED)
        for job_id in job_ids
    )


def test_req_008_jobs_run_one_at_a_time_in_fifo_order(db_path, make_queue):
    """REQ-008: jobs run in submission order, never more than one at once."""
    pipeline = GatedPipeline()
    jobs = make_queue(pipeline)
    slides = [add_ready_slide(db_path, f"s{i}.tif") for i in range(3)]

    first = jobs.submit(slides[0])["id"]
    wait_until(lambda: job_status(db_path, first) == JobStatus.RUNNING)
    # Queued while the first job holds the worker.
    rest = [jobs.submit(slide_id)["id"] for slide_id in slides[1:]]
    assert [job_status(db_path, job_id) for job_id in rest] == ["queued", "queued"]
    pipeline.release()
    wait_until(lambda: finished(db_path, first, *rest))

    assert pipeline.calls == slides
    assert pipeline.max_active == 1


def test_req_009_stop_during_job_marks_it_interrupted(db_path, make_queue):
    """REQ-009: a job running when the service stops ends failed with INTERRUPTED."""

    def until_stopped(slide, report):
        """Report progress forever; report() raises once stop() is called."""
        while True:
            report(Stage.SEGMENTING)

    jobs = make_queue(until_stopped)
    job_id = jobs.submit(add_ready_slide(db_path))["id"]
    wait_until(lambda: job_status(db_path, job_id) == JobStatus.RUNNING)

    jobs.stop()

    row = db.get_job(db_path, job_id)
    assert row["status"] == JobStatus.FAILED
    assert row["error_code"] == ErrorCode.INTERRUPTED
    assert row["finished_at"] is not None
    assert jobs.snapshot(job_id) is None


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now


def test_req_010_progress_db_writes_are_throttled(db_path, make_queue):
    """REQ-010: memory gets every update; SQLite gets stage changes and 1/s updates."""
    clock = FakeClock()
    seen = {}

    def pipeline(slide, report):
        """Report at chosen fake times and record what SQLite holds after each."""

        def stored_done() -> int | None:
            """progress_done of the only job, as currently stored in SQLite."""
            return db.list_jobs(db_path)[0]["progress_done"]

        for t, done in [(0.0, 0), (0.5, 10), (1.2, 20), (1.3, 30)]:
            clock.now = t
            report(Stage.EXTRACTING_FEATURES, done, 100)
            seen[done] = stored_done()
        return PipelineResult(result=None)

    jobs = make_queue(pipeline, clock=clock)
    job_id = jobs.submit(add_ready_slide(db_path))["id"]
    wait_until(lambda: finished(db_path, job_id))

    # 0: stage change, written. 10: 0.5 s later, skipped. 20: 1.2 s after
    # the last write, written. 30: 0.1 s later, skipped.
    assert seen == {0: 0, 10: 0, 20: 20, 30: 20}
    # The skipped final update is written when the job ends.
    row = db.get_job(db_path, job_id)
    assert (row["stage"], row["progress_done"], row["progress_total"]) == (
        "extracting_features",
        30,
        100,
    )


def test_req_017_pipeline_error_code_is_kept(db_path, make_queue):
    """REQ-017: a PipelineError fails the job with its own code and message."""

    def no_tissue(slide, report):
        """Fail the way segmentation does on a blank slide."""
        raise PipelineError(ErrorCode.NO_TISSUE, "No tissue found")

    jobs = make_queue(no_tissue)
    job_id = jobs.submit(add_ready_slide(db_path))["id"]
    wait_until(lambda: finished(db_path, job_id))

    row = db.get_job(db_path, job_id)
    assert row["status"] == JobStatus.FAILED
    assert (row["error_code"], row["error_message"]) == ("NO_TISSUE", "No tissue found")


def test_req_017_unexpected_error_is_inference_failed_and_not_retried(
    db_path, make_queue, caplog
):
    """REQ-017: any other exception is INFERENCE_FAILED, logged without its text, run once."""
    calls = []

    def flaky(slide, report):
        """Fail the first job with a path in the message; complete later ones."""
        calls.append(slide["id"])
        if len(calls) == 1:
            raise RuntimeError(f"cannot read /acq/{PHI_NAME}")
        return PipelineResult(result=None)

    caplog.set_level(logging.INFO)
    jobs = make_queue(flaky)
    failing, later = (
        add_ready_slide(db_path, "a.tif"),
        add_ready_slide(db_path, "b.tif"),
    )
    failed_id = jobs.submit(failing)["id"]
    later_id = jobs.submit(later)["id"]
    wait_until(lambda: finished(db_path, failed_id, later_id))

    row = db.get_job(db_path, failed_id)
    assert row["error_code"] == ErrorCode.INFERENCE_FAILED
    assert row["error_message"] == INFERENCE_FAILED_MESSAGE
    # One worker, FIFO: a retry would have run before the later job.
    assert calls == [failing, later]
    assert job_status(db_path, later_id) == JobStatus.COMPLETED
    assert "RuntimeError" in caplog.text
    assert PHI_NAME not in caplog.text


def test_completed_job_stores_result_models_and_timings(db_path, make_queue):
    """A completed job keeps what the pipeline returned."""
    outcome = PipelineResult(
        result={"predicted_class": "tumor"},
        models=[{"role": "mil", "name": "m", "version": "1", "sha256": "c" * 64}],
        timings_s={"segmenting": 1.5},
    )
    jobs = make_queue(lambda slide, report: outcome)
    job_id = jobs.submit(add_ready_slide(db_path))["id"]
    wait_until(lambda: finished(db_path, job_id))

    row = db.get_job(db_path, job_id)
    assert row["status"] == JobStatus.COMPLETED
    assert row["started_at"] is not None and row["finished_at"] is not None
    assert row["result_json"] == '{"predicted_class": "tumor"}'
    assert row["timings_json"] == '{"segmenting": 1.5}'


def test_stub_pipeline_reports_every_stage_in_order():
    """The stub walks the five stages in order, with patch counts while extracting."""
    reports = []

    outcome = stub_pipeline(None, lambda *args: reports.append(args), stage_seconds=0)

    stages = list(dict.fromkeys(report[0] for report in reports))
    assert stages == list(Stage)
    counts = [r[1:] for r in reports if r[0] is Stage.EXTRACTING_FEATURES]
    assert counts[0] == (0, FAKE_PATCH_COUNT)
    assert counts[-1] == (FAKE_PATCH_COUNT, FAKE_PATCH_COUNT)
    assert outcome.result is None
