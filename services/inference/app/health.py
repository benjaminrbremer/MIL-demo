"""GET /v1/health: service status, GPU, model versions, queue depth (REQ-018).

This is the only endpoint that does not require the device token.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__, db
from app.gpu import gpu_info

API_VERSION = "v1"

router = APIRouter(prefix="/v1")


class GpuInfo(BaseModel):
    """GPU availability as reported by PyTorch."""

    available: bool
    name: str | None


class ModelInfo(BaseModel):
    """One loaded model's identity: role, name, version, and file hash."""

    role: str
    name: str
    version: str
    sha256: str


class QueueInfo(BaseModel):
    """Number of jobs currently running and waiting."""

    running: int
    queued: int


class HealthResponse(BaseModel):
    """Response body for GET /v1/health."""

    status: str
    service_version: str
    api_version: str
    gpu: GpuInfo
    models: list[ModelInfo]
    queue: QueueInfo


@router.get("/health")
def health(request: Request) -> HealthResponse:
    """Report service status, GPU, model versions, and queue depth."""
    # A plain `def` endpoint runs in a worker thread, so a slow GPU probe
    # never blocks the event loop.
    running, queued = db.count_active_jobs(request.app.state.db_path)
    return HealthResponse(
        status="ok",
        service_version=__version__,
        api_version=API_VERSION,
        gpu=GpuInfo(**gpu_info()),
        models=[],  # filled from models/manifest.json in roadmap item 6
        queue=QueueInfo(running=running, queued=queued),
    )
