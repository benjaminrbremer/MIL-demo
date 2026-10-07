"""The analysis pipeline interface that the job worker calls (D-036).

A pipeline is any callable with the signature

    pipeline(slide: sqlite3.Row, report: Report, *, job_id: str) -> PipelineResult

It runs on the job worker thread, so it may block (read slides, use the
GPU). It publishes progress by calling `report(stage, done, total)`, and
fails with a defined error code by raising PipelineError (REQ-017). Any
other exception is reported as INFERENCE_FAILED. `job_id` names the
folder for the job's saved outputs (D-050).

The service runs `app.pipeline.mil_pipeline.MilPipeline`; tests pass
fakes.
"""

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.errors import ErrorCode

JOBS_DIRNAME = "jobs"
HEATMAP_FILENAME = "heatmap.png"


def job_output_dir(data_dir: Path, job_id: str) -> Path:
    """Folder for one job's saved outputs: DATA_DIR/jobs/<job_id>/ (D-050)."""
    # Lives here, not in mil_pipeline.py, so the API can find the heatmap
    # without importing torch.
    return data_dir / JOBS_DIRNAME / job_id


class Stage(StrEnum):
    """Pipeline stages, in the order they run (see docs/api-contract.md)."""

    SEGMENTING = "segmenting"
    PATCHING = "patching"
    EXTRACTING_FEATURES = "extracting_features"
    AGGREGATING = "aggregating"
    RENDERING = "rendering"


class PipelineError(Exception):
    """A pipeline failure with one of the contract's job error codes."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        """Store the code and a client-safe message (no paths, no exception text)."""
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PipelineResult:
    """What a successful pipeline run returns, stored on the job."""

    result: dict | None
    models: list[dict] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)


class Report(Protocol):
    """The progress callback handed to a pipeline."""

    def __call__(
        self, stage: Stage, done: int | None = None, total: int | None = None
    ) -> None:
        """Publish the current stage and, if known, items done of total."""


class Pipeline(Protocol):
    """What the job worker calls to analyse one slide."""

    def __call__(
        self, slide: sqlite3.Row, report: Report, *, job_id: str
    ) -> PipelineResult:
        """Analyse the slide, reporting progress; raise PipelineError on a known failure."""
