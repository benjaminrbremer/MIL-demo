"""Uncertainty flag and sample-quality metrics for a completed job (D-011).

All of these come from things the pipeline already has, so they cost
nothing extra to compute:

- uncertain (REQ-012): the predicted class's probability lies within
  [0.3, 0.7], bounds included. A borderline result is never shown as a
  definitive answer (RISK-001).
- tissue_area_mm2, tissue_fraction, patch_count (REQ-013): from the tissue
  mask and the patch list.
- segmentation_suspect (REQ-021): tissue fraction above 0.6. At threshold
  20 the staged slides have 0.10-0.28; the failed segmentations at
  threshold 7 were 0.96-1.00, where the background counted as tissue
  (D-039, RISK-003).
"""

import numpy as np

UNCERTAINTY_BAND = (0.3, 0.7)  # REQ-012, D-011
SEGMENTATION_SUSPECT_FRACTION = 0.6  # REQ-021


def is_uncertain(probabilities: np.ndarray) -> bool:
    """True when the predicted (highest) class probability is within the band."""
    low, high = UNCERTAINTY_BAND
    return bool(low <= float(np.max(probabilities)) <= high)


def quality_metrics(mask: np.ndarray, mask_mpp: float, patch_count: int) -> dict:
    """Quality metrics in the contract's `result.quality` shape."""
    # The mask covers the whole slide (glass included), so its mean is the
    # fraction of the slide that is tissue.
    fraction = float(mask.mean())
    area_mm2 = float(mask.sum()) * mask_mpp**2 / 1e6  # um^2 -> mm^2
    return {
        "tissue_area_mm2": round(area_mm2, 2),
        "tissue_fraction": round(fraction, 4),
        "patch_count": int(patch_count),
        "blur_fraction": None,  # stretch goal (D-011)
        # The unrounded fraction, so 0.60004 doesn't round down to 0.6.
        "segmentation_suspect": fraction > SEGMENTATION_SUSPECT_FRACTION,
    }
