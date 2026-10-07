"""Job endpoints: create, list, get, and the SSE progress stream.

POST /v1/jobs            start analysis of a ready slide (202, job queued)
GET  /v1/jobs            jobs, newest first; ?slide_id= filters to one slide
GET  /v1/jobs/{id}       one job
GET  /v1/jobs/{id}/events  Server-Sent Events: snapshot, progress, then
                         completed or failed (D-013, D-034)
GET  /v1/jobs/{id}/heatmap.png  attention heatmap of a completed job
                         (REQ-014, D-053)

The SSE stream uses FastAPI's built-in EventSourceResponse (D-035), which
also sends a `: ping` comment every 15 s so idle connections stay open.
"""

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app import db
from app.db import JobStatus, SlideStatus
from app.errors import ApiError, ErrorCode
from app.health import ModelInfo
from app.jobs import JobState
from app.pipeline import HEATMAP_FILENAME, job_output_dir
from app.tiles import NOT_READY_MESSAGE

router = APIRouter(prefix="/v1")

SSE_POLL_S = 0.25
ALREADY_ACTIVE_MESSAGE = "Slide already has a queued or running job"
NOT_COMPLETED_MESSAGE = "Job has not completed"
NO_HEATMAP_MESSAGE = "Heatmap not available"
# A completed job's heatmap never changes. "private": it sits behind the
# device token, so shared caches must not keep it (as for tiles).
HEATMAP_CACHE_CONTROL = "private, max-age=3600"
_FINISHED = (JobStatus.COMPLETED, JobStatus.FAILED)


class JobRequest(BaseModel):
    """Request body for POST /v1/jobs."""

    slide_id: str


class JobProgress(BaseModel):
    """Items done of total in the current stage; null when the stage has no count."""

    done: int | None
    total: int | None


class JobError(BaseModel):
    """Why a job failed: a contract error code and a client-safe message."""

    code: str
    message: str


class Job(BaseModel):
    """A job as served by the API (see docs/api-contract.md)."""

    id: str
    slide_id: str
    status: str
    stage: str | None
    progress: JobProgress
    error: JobError | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    models: list[ModelInfo]
    timings_s: dict[str, float]
    result: dict | None


class JobProgressEvent(BaseModel):
    """Data of an SSE `progress` event."""

    status: str
    stage: str | None
    progress: JobProgress


def _to_job(row: sqlite3.Row, state: JobState | None) -> Job:
    """Map a job row to the API model, overlaid with fresher in-memory progress."""
    status, stage = row["status"], row["stage"]
    done, total = row["progress_done"], row["progress_total"]
    # SQLite progress can be up to a second behind the in-memory state. Once
    # the row is finished it is final, so the state is ignored.
    if state is not None and status not in _FINISHED:
        status, stage, done, total = state.status, state.stage, state.done, state.total
    error = None
    if row["error_code"] is not None:
        error = JobError(code=row["error_code"], message=row["error_message"])
    return Job(
        id=row["id"],
        slide_id=row["slide_id"],
        status=status,
        stage=stage,
        progress=JobProgress(done=done, total=total),
        error=error,
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        models=json.loads(row["models_json"] or "[]"),
        timings_s=json.loads(row["timings_json"] or "{}"),
        result=json.loads(row["result_json"]) if row["result_json"] else None,
    )


def _job_row(job_id: str, request: Request) -> sqlite3.Row:
    """Dependency: the job's row, or 404 NOT_FOUND."""
    # As a dependency this runs before the endpoint. For the SSE route that
    # matters: once a stream has started, its status can no longer be 404.
    row = db.get_job(request.app.state.db_path, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@router.post("/jobs", status_code=202)
def create_job(body: JobRequest, request: Request) -> Job:
    """Queue analysis of a ready slide; 404, 409 SLIDE_NOT_READY, 409 JOB_ALREADY_ACTIVE."""
    slide = db.get_slide(request.app.state.db_path, body.slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail="Slide not found")
    if slide["status"] != SlideStatus.READY:
        raise ApiError(409, ErrorCode.SLIDE_NOT_READY, NOT_READY_MESSAGE)
    try:
        row = request.app.state.job_queue.submit(body.slide_id)
    except sqlite3.IntegrityError:
        # The partial unique index allows one active job per slide (D-033).
        raise ApiError(
            409, ErrorCode.JOB_ALREADY_ACTIVE, ALREADY_ACTIVE_MESSAGE
        ) from None
    return _to_job(row, None)


@router.get("/jobs")
def list_jobs(request: Request, slide_id: str | None = None) -> list[Job]:
    """Jobs, newest first; only one slide's jobs if `slide_id` is given."""
    jobs = request.app.state.job_queue
    rows = db.list_jobs(request.app.state.db_path, slide_id)
    return [_to_job(row, jobs.snapshot(row["id"])) for row in rows]


@router.get("/jobs/{job_id}")
def get_job(request: Request, row: Annotated[sqlite3.Row, Depends(_job_row)]) -> Job:
    """One job by ID; 404 NOT_FOUND if unknown."""
    return _to_job(row, request.app.state.job_queue.snapshot(row["id"]))


@router.get("/jobs/{job_id}/events", response_class=EventSourceResponse)
async def job_events(
    request: Request, row: Annotated[sqlite3.Row, Depends(_job_row)]
) -> AsyncIterator[ServerSentEvent]:
    """Stream a job's progress: snapshot, progress events, then completed or failed."""
    job_id = row["id"]
    jobs = request.app.state.job_queue

    state = jobs.snapshot(job_id)
    job = _to_job(row, state)
    yield ServerSentEvent(event="snapshot", data=job)
    if job.status in _FINISHED:
        # Already finished: send the final event too, so clients handle a
        # finished job the same way whenever they connect.
        yield ServerSentEvent(event=job.status, data=job)
        return

    version = state.version if state is not None else None
    while True:
        # Polling the in-memory state merges fast updates into one event and
        # keeps a slow client from piling up a backlog (D-034).
        await asyncio.sleep(SSE_POLL_S)
        state = jobs.snapshot(job_id)
        if state is None:
            # The worker writes the final row before dropping the state, so
            # the row is final here. to_thread keeps the blocking sqlite3
            # call off the event loop.
            row = await asyncio.to_thread(db.get_job, request.app.state.db_path, job_id)
            if row["status"] in _FINISHED:
                job = _to_job(row, None)
                yield ServerSentEvent(event=job.status, data=job)
                return
            continue
        if state.version != version:
            version = state.version
            yield ServerSentEvent(
                event="progress",
                data=JobProgressEvent(
                    status=state.status,
                    stage=state.stage,
                    progress=JobProgress(done=state.done, total=state.total),
                ),
            )


@router.get("/jobs/{job_id}/heatmap.png", response_class=FileResponse)
def job_heatmap(
    request: Request, row: Annotated[sqlite3.Row, Depends(_job_row)]
) -> FileResponse:
    """The attention heatmap PNG of a completed job (REQ-014, D-053, D-054).

    404 NOT_FOUND for an unknown job, or a completed job with no heatmap
    (finished before heatmaps existed). 409 JOB_NOT_COMPLETED otherwise.
    """
    # The path is built from the ID of a row that exists, never from raw
    # request text, so a crafted ID can't reach outside DATA_DIR/jobs/.
    if row["status"] != JobStatus.COMPLETED:
        raise ApiError(409, ErrorCode.JOB_NOT_COMPLETED, NOT_COMPLETED_MESSAGE)
    path = job_output_dir(request.app.state.settings.data_dir, row["id"])
    path = path / HEATMAP_FILENAME
    if not path.is_file():
        raise HTTPException(status_code=404, detail=NO_HEATMAP_MESSAGE)
    # A plain `def` endpoint runs in FastAPI's thread pool, and FileResponse
    # streams the file, so the event loop is never blocked on disk.
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": HEATMAP_CACHE_CONTROL},
    )
