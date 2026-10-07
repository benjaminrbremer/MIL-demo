"""Patch coordinates on a global grid over the tissue mask (D-039).

The slide is cut into non-overlapping square patches of `patch_size_um`
(128 um for this model, about 566 px at 0.226 um/px), on a grid that
starts at the slide origin. A patch is kept when the mask pixel under its
centre is tissue.

wsinfer-mil traces the mask into polygons with shapely and tests each
centre against them. Looking up the mask pixel gives nearly the same set
(differences only at the outline) with no extra library.
"""

import numpy as np


def patch_size_px(patch_size_um: float, mpp: float) -> int:
    """Patch side length in level-0 pixels."""
    return round(patch_size_um / mpp)


def tissue_patches(
    mask: np.ndarray, slide_size: tuple[int, int], patch_px: int
) -> np.ndarray:
    """Top-left (x, y) level-0 coordinates of patches centred on tissue, shape (N, 2)."""
    width, height = slide_size
    half = round(patch_px / 2)
    centres_x = np.arange(half, width, patch_px)
    centres_y = np.arange(half, height, patch_px)
    # Same order as wsinfer-mil: x ascending, and y changing fastest.
    cx, cy = np.meshgrid(centres_x, centres_y, indexing="ij")
    cx, cy = cx.ravel(), cy.ravel()

    # Level-0 pixel -> mask pixel. The mask has the slide's aspect ratio,
    # so each axis has its own scale.
    rows, cols = mask.shape
    mask_row = np.minimum(cy * rows // height, rows - 1)
    mask_col = np.minimum(cx * cols // width, cols - 1)
    keep = mask[mask_row, mask_col]

    return np.stack([cx[keep] - half, cy[keep] - half], axis=1).astype(np.int64)
