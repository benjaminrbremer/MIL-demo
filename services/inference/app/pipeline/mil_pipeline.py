"""The MIL analysis pipeline the job worker runs (D-036, D-038).

    slide row ──> segmenting ──> patching ──> extracting_features ──> aggregating
                  thumbnail      128 um grid   CTransPath, batches     ABMIL
                  tissue mask    on tissue     of 64 (or cache hit)    probabilities
                                                                       + attention
              ──> rendering
                  heatmap PNG, uncertainty flag, quality metrics (D-054)

Each stage is our own code on OpenSlide, OpenCV, and PyTorch. Progress is
reported at every stage change and after every feature batch (REQ-010).
Known failures raise PipelineError with a contract error code (REQ-017):

- NO_RESOLUTION: the slide has no microns per pixel, so 128 um patches
  can't be sized (D-044). Checked before the file is even opened.
- SLIDE_UNREADABLE: OpenSlide can't open or read the file.
- NO_TISSUE: fewer than 16 patches of tissue (D-043).

Anything else (including GPU out-of-memory) becomes INFERENCE_FAILED in
the worker. The slide's file path is used to open it but never logged
or put in a message (REQ-006).
"""

import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import openslide

from app.errors import ErrorCode
from app.models import LoadedModels
from app.pipeline import (
    HEATMAP_FILENAME,
    PipelineError,
    PipelineResult,
    Report,
    Stage,
    job_output_dir,
)
from app.pipeline.cache import FeatureCache, cache_key
from app.pipeline.features import PatchDataset, extract_features
from app.pipeline.heatmap import render_heatmap
from app.pipeline.mil import aggregate
from app.pipeline.patch import patch_size_px, tissue_patches
from app.pipeline.quality import UNCERTAINTY_BAND, is_uncertain, quality_metrics
from app.pipeline.segment import SATURATION_THRESHOLD, segment_slide

logger = logging.getLogger(__name__)

MIN_PATCHES = 16  # D-043

NO_RESOLUTION_MESSAGE = (
    "The slide has no microns-per-pixel value, so patches can't be sized"
)
UNREADABLE_MESSAGE = "The slide file could not be read"
NO_TISSUE_MESSAGE = "Too little tissue was found on the slide to analyse"


class MilPipeline:
    """Callable pipeline: (slide row, report, job_id) -> PipelineResult."""

    def __init__(
        self,
        models: LoadedModels,
        data_dir: Path,
        feature_workers: int,
        opener: Callable = openslide.OpenSlide,
    ) -> None:
        """Hold the loaded models and settings; `opener` is swapped in tests."""
        self._models = models
        self._data_dir = data_dir
        self._feature_workers = feature_workers
        self._opener = opener
        self._cache = FeatureCache(data_dir)

    def __call__(
        self, slide: sqlite3.Row, report: Report, *, job_id: str
    ) -> PipelineResult:
        """Analyse one slide; see the module docstring for the stages."""
        models = self._models
        slide_id = slide["id"]
        if slide["mpp_x"] is None or slide["mpp_y"] is None:
            raise PipelineError(ErrorCode.NO_RESOLUTION, NO_RESOLUTION_MESSAGE)
        mpp = (slide["mpp_x"] + slide["mpp_y"]) / 2
        timings: dict[str, float] = {}

        try:
            handle = self._opener(slide["file_path"])
        except (openslide.OpenSlideError, OSError):
            raise PipelineError(
                ErrorCode.SLIDE_UNREADABLE, UNREADABLE_MESSAGE
            ) from None

        with handle:
            try:
                report(Stage.SEGMENTING)
                slide_size = handle.dimensions  # level 0, for the heatmap
                started = time.perf_counter()
                tissue = segment_slide(handle, mpp)
                timings[Stage.SEGMENTING] = _since(started)

                report(Stage.PATCHING)
                started = time.perf_counter()
                key = cache_key(
                    slide["sha256"],
                    models.encoder_sha256,
                    models.patch_size_um,
                    SATURATION_THRESHOLD,
                )
                cached = self._cache.load(key)
                patch_px = patch_size_px(models.patch_size_um, mpp)
                if cached is not None:
                    coords, features = cached
                else:
                    coords = tissue_patches(tissue.mask, handle.dimensions, patch_px)
                timings[Stage.PATCHING] = _since(started)
                if len(coords) < MIN_PATCHES:
                    raise PipelineError(ErrorCode.NO_TISSUE, NO_TISSUE_MESSAGE)

                started = time.perf_counter()
                if cached is not None:
                    # Nothing to encode: progress jumps straight to the end (D-046).
                    report(Stage.EXTRACTING_FEATURES, len(coords), len(coords))
                    logger.info(
                        "Job %s slide %s: feature cache hit (%d patches)",
                        job_id,
                        slide_id,
                        len(coords),
                    )
                else:
                    dataset = PatchDataset(
                        slide["file_path"], coords, patch_px, self._opener
                    )
                    features = extract_features(
                        dataset,
                        models.encoder,
                        models.device,
                        report,
                        self._feature_workers,
                    )
                    self._cache.store(key, coords, features)
                timings[Stage.EXTRACTING_FEATURES] = _since(started)
            except openslide.OpenSlideError:
                # A read failure part-way, e.g. a corrupt tile or a removed file.
                raise PipelineError(
                    ErrorCode.SLIDE_UNREADABLE, UNREADABLE_MESSAGE
                ) from None

        report(Stage.AGGREGATING)
        started = time.perf_counter()
        probabilities, attention = aggregate(models.mil, features, models.device)
        timings[Stage.AGGREGATING] = _since(started)

        report(Stage.RENDERING)
        started = time.perf_counter()
        heatmap = render_heatmap(
            coords, attention, slide_size, patch_px, tissue.mask.shape
        )
        quality = quality_metrics(tissue.mask, tissue.mpp, len(coords))
        self._save_outputs(job_id, coords, attention, tissue.mask, heatmap)
        timings[Stage.RENDERING] = _since(started)

        predicted = int(np.argmax(probabilities))
        logger.info(
            "Job %s slide %s: %d patches, predicted %s (p=%.3f)",
            job_id,
            slide_id,
            len(coords),
            models.class_names[predicted],
            probabilities[predicted],
        )
        return PipelineResult(
            result={
                "probabilities": {
                    name: float(p)
                    for name, p in zip(models.class_names, probabilities, strict=True)
                },
                "predicted_class": models.class_names[predicted],
                "uncertain": is_uncertain(probabilities),
                "uncertainty_band": list(UNCERTAINTY_BAND),
                "quality": quality,
            },
            models=[dict(info) for info in models.infos],
            timings_s={str(stage): t for stage, t in timings.items()},
        )

    def _save_outputs(
        self,
        job_id: str,
        coords: np.ndarray,
        attention: np.ndarray,
        mask: np.ndarray,
        heatmap: bytes,
    ) -> None:
        """Save the job's outputs (D-050) and its heatmap PNG (D-054)."""
        # The .npy files are internal and never served: patch coordinates and
        # attention line up row for row; the mask is on the thumbnail grid.
        # heatmap.png is served by GET /v1/jobs/{id}/heatmap.png. It is
        # written before the job is marked completed, so the endpoint never
        # sees a half-written file.
        out = job_output_dir(self._data_dir, job_id)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "coords.npy", coords)
        np.save(out / "attention.npy", attention)
        np.save(out / "mask.npy", mask)
        (out / HEATMAP_FILENAME).write_bytes(heatmap)


def _since(started: float) -> float:
    """Seconds since `started`, to the millisecond."""
    return round(time.perf_counter() - started, 3)
