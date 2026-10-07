"""Job endpoint, SSE, and heatmap tests (REQ-008 to REQ-010, REQ-014, REQ-017)."""

import json
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import db, jobs_api
from app.db import DB_FILENAME, JobStatus, SlideStatus
from app.errors import ErrorCode
from app.jobs import INFERENCE_FAILED_MESSAGE, JobQueue
from app.main import create_app
from app.pipeline import HEATMAP_FILENAME, PipelineResult, Stage, job_output_dir
from tests.fakes import PHI_NAME, fake_model_loader
from tests.helpers import GatedPipeline, add_ready_slide, job_status, wait_until

JOB_FIELDS = {
    "id",
    "slide_id",
    "status",
    "stage",
    "progress",
    "error",
    "created_at",
    "started_at",
    "finished_at",
    "models",
    "timings_s",
    "result",
}


@pytest.fixture
def pipeline() -> GatedPipeline:
    """The fake pipeline the app's job queue runs; closed until release()."""
    return GatedPipeline()


@pytest.fixture
def client(app, pipeline):
    """A TestClient whose job queue runs `pipeline` instead of the MIL pipeline."""
    # Replaced before the lifespan starts the worker.
    app.state.job_queue = JobQueue(app.state.db_path, pipeline)
    with TestClient(app) as c:
        yield c
        # Before the client exits, or shutdown waits for the gate to time out.
        pipeline.release()


@pytest.fixture
def db_path(app, client):
    """The running app's database (created by the lifespan in `client`)."""
    return app.state.db_path


def post_job(client, auth_headers, slide_id):
    """POST /v1/jobs for a slide."""
    return client.post("/v1/jobs", json={"slide_id": slide_id}, headers=auth_headers)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Split an SSE body into (event, data) pairs; comments are skipped."""
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if not line.startswith(":")
        )
        if fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_post_job_returns_202_with_queued_job(client, auth_headers, db_path):
    """POST /v1/jobs queues a job for a ready slide and returns it."""
    slide_id = add_ready_slide(db_path)

    response = post_job(client, auth_headers, slide_id)

    assert response.status_code == 202
    body = response.json()
    assert set(body) == JOB_FIELDS
    assert body["slide_id"] == slide_id
    assert body["status"] == "queued"
    assert body["progress"] == {"done": None, "total": None}
    assert body["error"] is None
    assert body["result"] is None
    assert body["models"] == []
    assert body["timings_s"] == {}


def test_post_job_unknown_slide_is_404(client, auth_headers):
    """An unknown slide ID gets 404 NOT_FOUND."""
    response = post_job(client, auth_headers, "no-such-slide")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "status", [SlideStatus.ARRIVING, SlideStatus.REGISTERING, SlideStatus.UNREADABLE]
)
def test_post_job_slide_not_ready_is_409(client, auth_headers, db_path, status):
    """A slide that isn't ready gets 409 SLIDE_NOT_READY and no job."""
    slide_id = db.ensure_arriving(db_path, "/acq/slide.tif", "2026-10-07T14:00:00Z")
    db.set_status(db_path, slide_id, status)

    response = post_job(client, auth_headers, slide_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLIDE_NOT_READY"
    assert db.list_jobs(db_path) == []


def test_post_job_while_slide_has_active_job_is_409(
    client, auth_headers, db_path, pipeline
):
    """A second job for a slide with a queued or running job gets 409 JOB_ALREADY_ACTIVE."""
    slide_id = add_ready_slide(db_path)
    first = post_job(client, auth_headers, slide_id).json()["id"]

    response = post_job(client, auth_headers, slide_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ALREADY_ACTIVE"
    # Once the first job has finished, the slide can be analysed again.
    pipeline.release()
    wait_until(lambda: job_status(db_path, first) == JobStatus.COMPLETED)
    assert post_job(client, auth_headers, slide_id).status_code == 202


def test_post_job_without_slide_id_is_422(client, auth_headers):
    """A body without slide_id gets 422 VALIDATION_ERROR."""
    response = client.post("/v1/jobs", json={}, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/jobs"),
        ("GET", "/v1/jobs"),
        ("GET", "/v1/jobs/some-id"),
        ("GET", "/v1/jobs/some-id/events"),
        ("GET", "/v1/jobs/some-id/heatmap.png"),
    ],
)
def test_job_endpoints_require_token(client, method, path):
    """Every job endpoint gets 401 UNAUTHORIZED without the device token."""
    response = client.request(method, path, json={"slide_id": "x"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_list_jobs_newest_first_and_filtered_by_slide(
    client, auth_headers, db_path, pipeline
):
    """GET /v1/jobs lists jobs newest first; ?slide_id= keeps one slide's jobs."""
    pipeline.release()
    a, b = add_ready_slide(db_path, "a.tif"), add_ready_slide(db_path, "b.tif")
    job_a = post_job(client, auth_headers, a).json()["id"]
    job_b = post_job(client, auth_headers, b).json()["id"]

    all_jobs = client.get("/v1/jobs", headers=auth_headers).json()
    only_a = client.get(f"/v1/jobs?slide_id={a}", headers=auth_headers).json()
    unknown = client.get("/v1/jobs?slide_id=nope", headers=auth_headers).json()

    assert [job["id"] for job in all_jobs] == [job_b, job_a]
    assert [job["id"] for job in only_a] == [job_a]
    assert unknown == []


def test_get_job(client, auth_headers, db_path):
    """GET /v1/jobs/{id} returns one job."""
    job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]

    response = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == job_id


@pytest.mark.parametrize("suffix", ["", "/events", "/heatmap.png"])
def test_unknown_job_is_404(client, auth_headers, suffix):
    """An unknown job ID gets a JSON 404 NOT_FOUND, also from the SSE endpoint."""
    response = client.get(f"/v1/jobs/no-such-job{suffix}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_req_010_events_stream_reports_stage_and_patch_progress(
    app, auth_headers, monkeypatch
):
    """REQ-010: the SSE stream sends a snapshot, stage and patch progress, then completed."""
    gate = threading.Event()

    def paced(slide, report, *, job_id):
        """Wait for the test, then report with gaps much longer than the SSE poll."""
        gate.wait(5)
        for args in [
            (Stage.SEGMENTING,),
            (Stage.EXTRACTING_FEATURES, 0, 4),
            (Stage.EXTRACTING_FEATURES, 2, 4),
            (Stage.EXTRACTING_FEATURES, 4, 4),
        ]:
            report(*args)
            time.sleep(0.1)
        return PipelineResult(result=None)

    # TestClient returns the body only once the stream has closed, so the
    # pipeline runs on its own clock: 0.1 s between reports, 0.01 s poll.
    monkeypatch.setattr(jobs_api, "SSE_POLL_S", 0.01)
    app.state.job_queue = JobQueue(app.state.db_path, paced)
    with TestClient(app) as client:
        db_path = app.state.db_path
        job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]
        wait_until(lambda: job_status(db_path, job_id) == JobStatus.RUNNING)

        # Opens the gate shortly after the stream has sent its snapshot.
        threading.Timer(0.3, gate.set).start()
        response = client.get(f"/v1/jobs/{job_id}/events", headers=auth_headers)

    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == [
        "snapshot",
        "progress",
        "progress",
        "progress",
        "progress",
        "completed",
    ]
    assert events[0][1]["status"] == "running"
    progress = [
        (d["stage"], d["progress"]["done"], d["progress"]["total"])
        for _, d in events[1:5]
    ]
    assert progress == [
        ("segmenting", None, None),
        ("extracting_features", 0, 4),
        ("extracting_features", 2, 4),
        ("extracting_features", 4, 4),
    ]
    assert all(d["status"] == "running" for _, d in events[1:5])
    assert events[-1][1]["status"] == "completed"
    assert set(events[-1][1]) == JOB_FIELDS


def test_events_for_finished_job_send_snapshot_and_final_event(
    client, auth_headers, db_path, pipeline
):
    """Connecting after a job has finished gives its snapshot, then the final event."""
    pipeline.release()
    job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]
    wait_until(lambda: job_status(db_path, job_id) == JobStatus.COMPLETED)

    response = client.get(f"/v1/jobs/{job_id}/events", headers=auth_headers)

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["snapshot", "completed"]
    assert events[0][1] == events[1][1]


def test_req_017_failed_job_reports_code_without_exception_text(
    app, auth_headers, caplog
):
    """REQ-017: an unexpected pipeline error is INFERENCE_FAILED with a fixed message."""

    def broken(slide, report, *, job_id):
        """Fail with a file path in the exception text."""
        raise OSError(f"cannot open /acq/{PHI_NAME}")

    caplog.set_level(logging.INFO)
    app.state.job_queue = JobQueue(app.state.db_path, broken)
    with TestClient(app) as client:
        db_path = app.state.db_path
        job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]
        wait_until(lambda: job_status(db_path, job_id) == JobStatus.FAILED)
        body = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()

    assert body["status"] == "failed"
    assert body["error"] == {
        "code": "INFERENCE_FAILED",
        "message": INFERENCE_FAILED_MESSAGE,
    }
    assert body["finished_at"] is not None
    assert PHI_NAME not in json.dumps(body)
    assert PHI_NAME not in caplog.text


def test_health_reports_queue_depth(client, auth_headers, db_path, pipeline):
    """GET /v1/health counts running and queued jobs."""
    first = post_job(client, auth_headers, add_ready_slide(db_path, "a.tif")).json()
    wait_until(lambda: job_status(db_path, first["id"]) == JobStatus.RUNNING)
    post_job(client, auth_headers, add_ready_slide(db_path, "b.tif"))

    queue = client.get("/v1/health").json()["queue"]

    assert queue == {"running": 1, "queued": 1}


def test_req_009_startup_marks_queued_and_running_jobs_interrupted(
    settings, auth_headers
):
    """REQ-009: jobs left queued or running by a previous run start out failed INTERRUPTED."""
    db_path = settings.data_dir / DB_FILENAME
    db.init_db(db_path)
    queued = db.insert_job(
        db_path, add_ready_slide(db_path, "a.tif"), "2026-10-07T14:00:00Z"
    )
    running = db.insert_job(
        db_path, add_ready_slide(db_path, "b.tif"), "2026-10-07T14:00:01Z"
    )
    db.mark_job_running(db_path, running, "2026-10-07T14:00:02Z")

    with TestClient(create_app(settings, model_loader=fake_model_loader)) as client:
        jobs = client.get("/v1/jobs", headers=auth_headers).json()

    assert {job["id"] for job in jobs} == {queued, running}
    for job in jobs:
        assert job["status"] == "failed"
        assert job["error"]["code"] == "INTERRUPTED"
        assert job["finished_at"] is not None


def test_req_009_job_state_persists_across_restart(settings, auth_headers):
    """REQ-009: a finished job is still there, unchanged, after the service restarts."""
    app = create_app(settings, model_loader=fake_model_loader)
    app.state.job_queue = JobQueue(
        app.state.db_path, lambda slide, report, *, job_id: PipelineResult(result=None)
    )
    with TestClient(app) as client:
        job_id = post_job(
            client, auth_headers, add_ready_slide(app.state.db_path)
        ).json()["id"]
        wait_until(lambda: job_status(app.state.db_path, job_id) == JobStatus.COMPLETED)
        before = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()

    with TestClient(create_app(settings, model_loader=fake_model_loader)) as client:
        after = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()

    assert after == before
    assert after["status"] == "completed"


def heatmap_url(job_id: str) -> str:
    """The heatmap endpoint for a job."""
    return f"/v1/jobs/{job_id}/heatmap.png"


def test_req_014_completed_job_serves_heatmap_png(
    app, client, auth_headers, db_path, pipeline
):
    """REQ-014: a completed job's heatmap is served as a private, cacheable PNG."""
    pipeline.release()
    job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]
    wait_until(lambda: job_status(db_path, job_id) == JobStatus.COMPLETED)
    # The fake pipeline renders nothing; put a file where the real one would.
    out = job_output_dir(app.state.settings.data_dir, job_id)
    out.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\nfake"
    (out / HEATMAP_FILENAME).write_bytes(png)

    response = client.get(heatmap_url(job_id), headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.content == png
    # No filename (REQ-006): FileResponse adds Content-Disposition only if asked.
    assert "content-disposition" not in response.headers


def test_completed_job_without_heatmap_is_404(client, auth_headers, db_path, pipeline):
    """A job completed before heatmaps existed (item 6) gets 404 NOT_FOUND."""
    pipeline.release()
    job_id = post_job(client, auth_headers, add_ready_slide(db_path)).json()["id"]
    wait_until(lambda: job_status(db_path, job_id) == JobStatus.COMPLETED)

    response = client.get(heatmap_url(job_id), headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_heatmap_of_running_or_queued_job_is_409(client, auth_headers, db_path):
    """A job that hasn't finished gets 409 JOB_NOT_COMPLETED."""
    running = post_job(client, auth_headers, add_ready_slide(db_path, "a.tif"))
    queued = post_job(client, auth_headers, add_ready_slide(db_path, "b.tif"))
    running_id, queued_id = running.json()["id"], queued.json()["id"]
    wait_until(lambda: job_status(db_path, running_id) == JobStatus.RUNNING)

    for job_id in (running_id, queued_id):
        response = client.get(heatmap_url(job_id), headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "JOB_NOT_COMPLETED"


def test_heatmap_of_failed_job_is_409(client, auth_headers, db_path):
    """A failed job has no heatmap: 409 JOB_NOT_COMPLETED."""
    job_id = db.insert_job(db_path, add_ready_slide(db_path), db.utc_now_iso())
    db.mark_job_failed(
        db_path, job_id, db.utc_now_iso(), ErrorCode.NO_TISSUE, "No tissue"
    )

    response = client.get(heatmap_url(job_id), headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_COMPLETED"
