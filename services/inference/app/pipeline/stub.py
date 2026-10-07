"""Stand-in pipeline until the MIL model lands (roadmap item 6 removes it).

It sleeps through each stage and reports progress, so the queue, the SSE
stream, and the web app can be built and tested without a GPU. It returns
no result: a made-up probability could be mistaken for a real one.
"""

import sqlite3
import time

from app.pipeline import PipelineResult, Report, Stage

STAGE_SECONDS = 1.0
FAKE_PATCH_COUNT = 1000
PATCH_STEPS = 20


def stub_pipeline(
    slide: sqlite3.Row,
    report: Report,
    *,
    stage_seconds: float = STAGE_SECONDS,
) -> PipelineResult:
    """Report every stage in order, with patch counts during feature extraction."""
    for stage in Stage:
        if stage is Stage.EXTRACTING_FEATURES:
            step = FAKE_PATCH_COUNT // PATCH_STEPS
            for done in range(0, FAKE_PATCH_COUNT + 1, step):
                report(stage, done, FAKE_PATCH_COUNT)
                time.sleep(stage_seconds / PATCH_STEPS)
        else:
            report(stage)
            time.sleep(stage_seconds)
    return PipelineResult(result=None)
