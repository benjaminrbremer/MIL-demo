"""Tissue segmentation on a slide thumbnail (D-039).

Same method as wsinfer-mil, with the threshold raised from 7 to 20:

    2048 px thumbnail -> HSV saturation -> median blur (7 px)
    -> saturation > 20 -> closing (6 x 6 px)
    -> drop objects < 200^2 um^2 -> fill holes < 190^2 um^2

Tissue is stained, so it is saturated; glass is grey-white, so it isn't.
At 7, the lavender-tinted background of the Philips CAMELYON16 scans
(saturation about 8) counted as tissue. Known limitation of 20: pale fat
(saturation 7-20) is dropped too, and the value is tuned to these scans.

wsinfer-mil uses scikit-image for the last three steps. This is the same
thing with OpenCV only (one library less of SOUP). Objects and holes use
4-connectivity (pixels touch by an edge, not a corner), which is
scikit-image's default for these functions.
"""

from dataclasses import dataclass

import cv2 as cv
import numpy as np

THUMBNAIL_SIZE = (2048, 2048)  # longest side; aspect ratio is kept
MEDIAN_BLUR_PX = 7
SATURATION_THRESHOLD = 20  # D-039; wsinfer-mil uses 7
CLOSING_KERNEL_PX = 6
MIN_OBJECT_UM2 = 200**2
MIN_HOLE_UM2 = 190**2


@dataclass(frozen=True)
class TissueMask:
    """A boolean tissue mask over the thumbnail, and its pixel size."""

    mask: np.ndarray  # (rows, cols) bool, True = tissue
    mpp: float  # microns per mask pixel (mean of x and y)


def segment_slide(slide, mpp: float) -> TissueMask:
    """Segment tissue on the slide's thumbnail; `mpp` is the level-0 average."""
    # openslide-python composites the thumbnail onto a white background
    # and returns RGB.
    thumb = np.asarray(slide.get_thumbnail(THUMBNAIL_SIZE).convert("RGB"))
    width, height = slide.dimensions
    # Thumbnail pixel size: level-0 size x downsample, averaged over x and y
    # (as wsinfer-mil does).
    thumb_mpp = float(
        np.mean(mpp * np.array([width / thumb.shape[1], height / thumb.shape[0]]))
    )
    return TissueMask(mask=tissue_mask(thumb, thumb_mpp), mpp=thumb_mpp)


def tissue_mask(
    rgb: np.ndarray, mpp: float, threshold: int = SATURATION_THRESHOLD
) -> np.ndarray:
    """Boolean tissue mask of an RGB uint8 image whose pixels are `mpp` microns."""
    saturation = cv.cvtColor(rgb, cv.COLOR_RGB2HSV)[:, :, 1]
    saturation = cv.medianBlur(saturation, MEDIAN_BLUR_PX)
    binary = (saturation > threshold).astype(np.uint8)
    binary = _closing(binary, CLOSING_KERNEL_PX)

    px_area = mpp**2
    mask = binary.astype(bool)
    mask = _remove_small_components(mask, round(MIN_OBJECT_UM2 / px_area))
    # A hole is a background component; filling small ones = removing small
    # components of the inverted mask.
    mask = ~_remove_small_components(~mask, round(MIN_HOLE_UM2 / px_area))
    return mask


def _closing(binary: np.ndarray, size: int) -> np.ndarray:
    """Morphological closing with a size x size square, matching scikit-image."""
    # Closing = dilate then erode: joins tissue fragments a few pixels apart
    # and fills tiny gaps, without growing the outline.
    #
    # A square with an even side has no centre pixel. scikit-image anchors
    # the dilation one pixel before the middle and the erosion one pixel
    # after it, so the two shifts cancel. OpenCV's morphologyEx uses the
    # same anchor for both, which shifts the result by a pixel (about 11,000
    # mask pixels differed on test_062). Explicit anchors reproduce
    # scikit-image exactly.
    kernel = np.ones((size, size), np.uint8)
    before, after = (size - 1) // 2, size // 2
    dilated = cv.dilate(binary, kernel, anchor=(before, before))
    return cv.erode(dilated, kernel, anchor=(after, after))


def _remove_small_components(mask: np.ndarray, min_px: int) -> np.ndarray:
    """Set 4-connected True components with fewer than `min_px` pixels to False."""
    _, labels, stats, _ = cv.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=4
    )
    # Label 0 is the background (False pixels); never keep it.
    keep = stats[:, cv.CC_STAT_AREA] >= min_px
    keep[0] = False
    return keep[labels]
