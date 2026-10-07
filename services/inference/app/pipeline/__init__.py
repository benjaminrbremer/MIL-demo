"""The analysis pipeline interface that the job worker calls (D-036).

A pipeline is any callable with the signature

    pipeline(slide: sqlite3.Row, report: Report) -> PipelineResult

It runs on the job worker thread, so it may block (read slides, use the
GPU). It publishes progress by calling `report(stage, done, total)`, and
fails with a defined error code by raising PipelineError (REQ-017). Any
other exception is reported as INFERENCE_FAILED.

Until roadmap item 6, the worker runs `app.pipeline.stub.stub_pipeline`.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.errors import ErrorCode


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


Pipeline = Callable[[sqlite3.Row, Report], PipelineResult]
