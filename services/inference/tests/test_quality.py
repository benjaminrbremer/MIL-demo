"""Uncertainty flag and quality metric tests (REQ-012, REQ-013, REQ-021)."""

import numpy as np
import pytest

from app.pipeline.quality import is_uncertain, quality_metrics


@pytest.mark.parametrize(
    ("p_metastasis", "uncertain"),
    [
        (0.3, True),  # predicted class "no-metastasis" at 0.7: bound included
        (0.5, True),
        (0.7, True),  # bound included
        (0.29, False),
        (0.71, False),
        (0.05, False),
        (0.95, False),
    ],
)
def test_req_012_uncertain_within_band_inclusive(p_metastasis, uncertain):
    """REQ-012: flagged when the predicted-class probability is within [0.3, 0.7]."""
    probabilities = np.array([1 - p_metastasis, p_metastasis])

    assert is_uncertain(probabilities) is uncertain


def test_req_013_tissue_area_fraction_and_patch_count():
    """REQ-013: area in mm^2 from mask pixels and their size; fraction of the slide."""
    mask = np.zeros((100, 200), bool)
    mask[:50, :80] = True  # 4000 of 20000 pixels

    quality = quality_metrics(mask, mask_mpp=50.0, patch_count=123)

    # 4000 px x (50 um)^2 = 10,000,000 um^2 = 10 mm^2
    assert quality["tissue_area_mm2"] == 10.0
    assert quality["tissue_fraction"] == 0.2
    assert quality["patch_count"] == 123
    assert quality["blur_fraction"] is None
    assert quality["segmentation_suspect"] is False


@pytest.mark.parametrize(
    ("tissue_px", "suspect"),
    [(600, False), (601, True), (1000, True)],
)
def test_req_021_segmentation_suspect_above_0_6(tissue_px, suspect):
    """REQ-021: suspect when the tissue fraction is above 0.6 (0.6 itself is not)."""
    mask = np.zeros(1000, bool)
    mask[:tissue_px] = True

    quality = quality_metrics(mask.reshape(20, 50), mask_mpp=1.0, patch_count=16)

    assert quality["segmentation_suspect"] is suspect
