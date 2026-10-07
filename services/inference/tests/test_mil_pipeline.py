"""The MIL pipeline end to end, on a synthetic slide with fake models.

The real models only run on the desktop GPU (D-048). These tests check the
pipeline's own logic everywhere: stages and progress, result shape, error
codes, the feature cache, and the saved outputs. The opt-in tests at the
end run the real models on a real slide.
"""

import json
import os
from pathlib import Path

import numpy as np
import openslide
import pytest
from PIL import Image

from app import db
from app.config import DEFAULT_MODELS_DIR
from app.db import JobStatus
from app.errors import ErrorCode
from app.jobs import JobQueue
from app.pipeline import PipelineError, Stage
from app.pipeline.features import BATCH_SIZE, PatchDataset, extract_features
from app.pipeline.mil_pipeline import MIN_PATCHES, MilPipeline
from tests.fakes import PHI_NAME, fake_models
from tests.helpers import wait_until

# 4000 x 3000 px at 1 um/px: 128 um patches are 128 px. The tissue block
# covers x 1000-3000 and y 800-2200, so about 15 x 11 patches.
SLIDE_SIZE = (4000, 3000)
TISSUE_BOX = (1000, 800, 3000, 2200)
MPP = 1.0


def tissue_opener(path: str) -> openslide.ImageSlide:
    """An in-memory slide: white glass with one pink block of tissue."""
    image = Image.new("RGB", SLIDE_SIZE, (255, 255, 255))
    image.paste((200, 120, 160), TISSUE_BOX)
    return openslide.ImageSlide(image)


def blank_opener(path: str) -> openslide.ImageSlide:
    """An in-memory slide with no tissue at all."""
    return openslide.ImageSlide(Image.new("RGB", SLIDE_SIZE, (255, 255, 255)))


def broken_opener(path: str):
    """Fails like OpenSlide on an unreadable file, path in the message."""
    raise openslide.OpenSlideUnsupportedFormatError(f"Unsupported format: {path}")


def slide_row(**changes) -> dict:
    """The slide-row fields the pipeline reads."""
    row = {
        "id": "slide-1",
        "file_path": f"/acq/{PHI_NAME}",
        "sha256": "a" * 64,
        "mpp_x": MPP,
        "mpp_y": MPP,
    }
    row.update(changes)
    return row


class Recorder:
    """A report() callback that keeps every call."""

    def __init__(self) -> None:
        """Start empty."""
        self.calls: list[tuple] = []

    def __call__(self, stage, done=None, total=None) -> None:
        """Record one progress update."""
        self.calls.append((stage, done, total))

    def stages(self) -> list:
        """Stages in the order first reported."""
        return list(dict.fromkeys(call[0] for call in self.calls))

    def counts(self) -> list[tuple]:
        """(done, total) pairs reported during feature extraction."""
        return [c[1:] for c in self.calls if c[0] is Stage.EXTRACTING_FEATURES]


@pytest.fixture
def models():
    """Fresh fake models (the encoder counts its calls)."""
    return fake_models()


@pytest.fixture
def make_pipeline(tmp_path, models):
    """Build a MilPipeline on the fake models, writing under tmp_path/data."""

    def make(opener=tissue_opener) -> MilPipeline:
        return MilPipeline(models, tmp_path / "data", feature_workers=0, opener=opener)

    return make


def test_req_010_reports_stages_in_order_with_patch_counts(make_pipeline):
    """REQ-010: stages in order; patch counts go 0, 64, 128, ... up to the total."""
    report = Recorder()

    make_pipeline()(slide_row(), report, job_id="job-1")

    assert report.stages() == [
        Stage.SEGMENTING,
        Stage.PATCHING,
        Stage.EXTRACTING_FEATURES,
        Stage.AGGREGATING,
    ]
    counts = report.counts()
    total = counts[0][1]
    assert total > BATCH_SIZE * 2  # several batches
    assert counts[0] == (0, total)
    assert [done for done, _ in counts[1:-1]] == list(
        range(BATCH_SIZE, total, BATCH_SIZE)
    )
    assert counts[-1] == (total, total)


def test_req_011_result_has_probabilities_and_predicted_class(make_pipeline):
    """REQ-011: probabilities per class name sum to 1; predicted class is the max."""
    outcome = make_pipeline()(slide_row(), Recorder(), job_id="job-1")

    probabilities = outcome.result["probabilities"]
    assert list(probabilities) == ["no-metastasis", "metastasis"]
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert outcome.result["predicted_class"] == max(
        probabilities, key=probabilities.get
    )
    # Filled by item 7 (D-047).
    assert outcome.result["uncertain"] is None
    assert outcome.result["quality"] is None


def test_req_015_result_records_models_and_stage_timings(make_pipeline, models):
    """REQ-015: the result names the models and times every stage."""
    outcome = make_pipeline()(slide_row(), Recorder(), job_id="job-1")

    assert outcome.models == [dict(info) for info in models.infos]
    assert set(outcome.timings_s) == {
        "segmenting",
        "patching",
        "extracting_features",
        "aggregating",
    }
    assert all(t >= 0 for t in outcome.timings_s.values())


def test_req_015_completed_job_row_stores_result_models_and_timings(
    tmp_path, make_pipeline
):
    """REQ-015: through the job queue, the completed row stores all three."""
    db_path = tmp_path / "data" / "device.sqlite3"
    db.init_db(db_path)
    slide_id = db.ensure_arriving(db_path, f"/acq/{PHI_NAME}", "2026-10-07T14:00:00Z")
    metadata = {
        "width": 4000,
        "height": 3000,
        "level_count": 1,
        "mpp_x": MPP,
        "mpp_y": MPP,
    }
    db.mark_ready(db_path, slide_id, "a" * 64, metadata, "2026-10-07T14:00:08Z")
    jobs = JobQueue(db_path, make_pipeline())
    jobs.start()
    try:
        job_id = jobs.submit(slide_id)["id"]
        wait_until(lambda: db.get_job(db_path, job_id)["status"] == JobStatus.COMPLETED)
    finally:
        jobs.stop()

    row = db.get_job(db_path, job_id)
    assert json.loads(row["result_json"])["predicted_class"] in (
        "no-metastasis",
        "metastasis",
    )
    assert [m["role"] for m in json.loads(row["models_json"])] == ["encoder", "mil"]
    assert "extracting_features" in json.loads(row["timings_json"])


def test_saves_coords_attention_and_mask_for_the_heatmap(tmp_path, make_pipeline):
    """D-047: coordinates, attention, and mask are saved under jobs/<job_id>/."""
    make_pipeline()(slide_row(), Recorder(), job_id="job-1")

    out = tmp_path / "data" / "jobs" / "job-1"
    coords = np.load(out / "coords.npy")
    attention = np.load(out / "attention.npy")
    mask = np.load(out / "mask.npy")
    assert coords.shape == (len(attention), 2)
    assert attention.dtype == np.float32
    assert mask.dtype == bool and mask.any()
    # Every patch lies on the tissue block.
    x0, y0, x1, y1 = TISSUE_BOX
    assert (coords[:, 0] >= x0 - 128).all() and (coords[:, 0] < x1).all()
    assert (coords[:, 1] >= y0 - 128).all() and (coords[:, 1] < y1).all()


def test_second_run_uses_feature_cache(make_pipeline, models):
    """D-046: a repeat run skips the encoder, jumps progress to total, same result."""
    pipeline = make_pipeline()
    first = pipeline(slide_row(), Recorder(), job_id="job-1")
    encoder_calls = models.encoder.calls

    report = Recorder()
    second = pipeline(slide_row(), report, job_id="job-2")

    assert models.encoder.calls == encoder_calls
    total = report.counts()[0][1]
    assert report.counts() == [(total, total)]
    assert second.result == first.result


def test_cache_is_keyed_by_slide_content(make_pipeline, models):
    """D-046: a slide with a different SHA-256 is encoded again."""
    pipeline = make_pipeline()
    pipeline(slide_row(), Recorder(), job_id="job-1")
    encoder_calls = models.encoder.calls

    pipeline(slide_row(sha256="b" * 64), Recorder(), job_id="job-2")

    assert models.encoder.calls > encoder_calls


@pytest.mark.parametrize("missing", ["mpp_x", "mpp_y"])
def test_req_017_no_resolution_without_mpp(make_pipeline, missing):
    """REQ-017 / D-044: a slide without microns per pixel fails NO_RESOLUTION."""
    with pytest.raises(PipelineError) as excinfo:
        make_pipeline()(slide_row(**{missing: None}), Recorder(), job_id="job-1")

    assert excinfo.value.code == ErrorCode.NO_RESOLUTION


def test_req_017_no_tissue_on_blank_slide(make_pipeline, models):
    """REQ-017 / D-043: fewer than 16 tissue patches fails NO_TISSUE, before encoding."""
    with pytest.raises(PipelineError) as excinfo:
        make_pipeline(blank_opener)(slide_row(), Recorder(), job_id="job-1")

    assert excinfo.value.code == ErrorCode.NO_TISSUE
    assert models.encoder.calls == 0


def test_req_017_no_tissue_threshold_is_16_patches(tmp_path, models):
    """D-043: 15 patches fail; 16 pass."""

    def opener_with_patches(n: int):
        def opener(path):
            # A single row of n patch-sized blocks, far enough apart from the
            # rest that each counts on its own but large enough to survive.
            image = Image.new("RGB", SLIDE_SIZE, (255, 255, 255))
            image.paste((200, 120, 160), (0, 1024, 128 * n, 1024 + 128))
            return openslide.ImageSlide(image)

        return opener

    for n, fails in ((MIN_PATCHES - 1, True), (MIN_PATCHES, False)):
        pipeline = MilPipeline(
            models, tmp_path / f"data{n}", 0, opener=opener_with_patches(n)
        )
        report = Recorder()
        if fails:
            with pytest.raises(PipelineError):
                pipeline(slide_row(sha256=str(n) * 64), report, job_id="j")
        else:
            pipeline(slide_row(sha256=str(n) * 64), report, job_id="j")
            assert report.counts()[-1] == (n, n)


def test_req_017_unreadable_slide_without_path_in_message(make_pipeline):
    """REQ-017 / REQ-006: an unopenable file fails SLIDE_UNREADABLE; no path leaks."""
    with pytest.raises(PipelineError) as excinfo:
        make_pipeline(broken_opener)(slide_row(), Recorder(), job_id="job-1")

    assert excinfo.value.code == ErrorCode.SLIDE_UNREADABLE
    assert PHI_NAME not in excinfo.value.message
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_req_017_read_failure_mid_extraction_is_slide_unreadable(make_pipeline):
    """REQ-017: a pixel read that fails part-way also fails SLIDE_UNREADABLE."""

    class FailingSlide(openslide.ImageSlide):
        def read_region(self, location, level, size):
            raise openslide.OpenSlideError(f"Read error in /acq/{PHI_NAME}")

    def opener(path):
        slide = tissue_opener(path)
        slide.__class__ = FailingSlide
        return slide

    with pytest.raises(PipelineError) as excinfo:
        make_pipeline(opener)(slide_row(), Recorder(), job_id="job-1")

    assert excinfo.value.code == ErrorCode.SLIDE_UNREADABLE


def test_worker_processes_give_same_features_as_in_thread(models):
    """D-045: forkserver workers (which ignore Ctrl+C) match in-thread loading."""
    coords = np.array([[x, y] for x in range(1000, 3000, 128) for y in (800, 1500)])
    dataset = PatchDataset("unused", coords, 128, tissue_opener)

    in_thread = extract_features(dataset, models.encoder, "cpu", Recorder(), 0)
    with_workers = extract_features(dataset, models.encoder, "cpu", Recorder(), 2)

    assert np.array_equal(in_thread, with_workers)


# --- Opt-in: real models on a real slide (desktop GPU) -----------------------

REAL_SLIDE = os.environ.get("MIL_TEST_SLIDE")
# Our patch count for test_062 at threshold 20. wsinfer-mil's polygon test
# gives 2,226; our mask is identical to its mask, and the centre-pixel test
# also keeps 55 patches on the tissue outline (spike findings).
TEST_062_PATCHES = 2281


def real_slide_row(path: Path) -> dict:
    """A slide row for a real file, with mpp read from the file."""
    with openslide.OpenSlide(path) as slide:
        mpp_x = float(slide.properties[openslide.PROPERTY_NAME_MPP_X])
        mpp_y = float(slide.properties[openslide.PROPERTY_NAME_MPP_Y])
    return {
        "id": "real",
        "file_path": str(path),
        "sha256": "r" * 64,
        "mpp_x": mpp_x,
        "mpp_y": mpp_y,
    }


@pytest.mark.slide
@pytest.mark.skipif(not REAL_SLIDE, reason="MIL_TEST_SLIDE not set")
def test_req_020_real_slide_repeat_run_identical(tmp_path):
    """REQ-020: two full runs (no cache) give identical probabilities and attention."""
    from app.models import load_models

    path = Path(REAL_SLIDE).expanduser()
    models = load_models(DEFAULT_MODELS_DIR)
    row = real_slide_row(path)
    runs = []
    for run in ("a", "b"):
        pipeline = MilPipeline(models, tmp_path / run, feature_workers=8)
        outcome = pipeline(row, Recorder(), job_id=run)
        attention = np.load(tmp_path / run / "jobs" / run / "attention.npy")
        coords = np.load(tmp_path / run / "jobs" / run / "coords.npy")
        runs.append((outcome, attention, coords))
        print(f"run {run}: {outcome.timings_s} {outcome.result['probabilities']}")

    (first, att_a, coords_a), (second, att_b, _) = runs
    assert first.result == second.result
    assert np.array_equal(att_a, att_b)
    if path.stem == "test_062":
        assert len(coords_a) == TEST_062_PATCHES
