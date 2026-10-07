"""Attention heatmap: per-patch attention scores -> a transparent PNG (D-010, D-053).

    raw scores ──> clip to the slide's p1..p99, rescale to 0..1
               ──> one value per 128 um grid cell (NaN = no patch)
               ──> sample onto the thumbnail grid (nearest cell)
               ──> TURBO colour map, alpha 0 where no patch ──> PNG

Why clip: the raw scores are skewed, with a few very high ones. A plain
min-max rescale would let one outlier squash every other patch into the
bottom of the colour map. Clipping to the 1st and 99th percentiles keeps
the spacing between ordinary scores visible and saturates only the top 1%.
The colours show attention *relative to this slide*: a negative slide has
red areas too. The heatmap shows where the model looked, not a probability.

Geometry: the PNG has the tissue mask's shape (the 2048 px thumbnail grid)
and covers exactly the level-0 rectangle [0, W] x [0, H]. The web viewer
overlays it at (0, 0, W, H) with no offset, as the Deep Zoom tiles cover
the same rectangle (D-030).

OpenCV does the colour map and the PNG encoding (already a dependency).
Its PNGs hold only image chunks, no text or metadata (REQ-006).
"""

import cv2 as cv
import numpy as np

CLIP_PERCENTILES = (1, 99)
COLORMAP = cv.COLORMAP_TURBO  # blue = low, red = high


def normalize(attention: np.ndarray) -> np.ndarray:
    """Scores clipped to their 1st..99th percentiles and rescaled to [0, 1]."""
    scores = np.asarray(attention, dtype=np.float64)
    lo, hi = np.percentile(scores, CLIP_PERCENTILES)
    if hi <= lo:
        # All scores (nearly) equal: nothing to rank. Avoid dividing by zero.
        return np.zeros_like(scores)
    return np.clip((scores - lo) / (hi - lo), 0.0, 1.0)


def render_heatmap(
    coords: np.ndarray,
    attention: np.ndarray,
    slide_size: tuple[int, int],
    patch_px: int,
    out_shape: tuple[int, int],
) -> bytes:
    """PNG bytes of the attention heatmap; `out_shape` is (rows, cols)."""
    width, height = slide_size
    rows, cols = out_shape

    # Patches lie on a grid from the slide origin, so a patch's top-left
    # corner divided by the patch size is its grid cell.
    grid = np.full(
        (-(-height // patch_px), -(-width // patch_px)), np.nan, dtype=np.float64
    )
    cells = np.asarray(coords) // patch_px
    grid[cells[:, 1], cells[:, 0]] = normalize(attention)

    # Each output pixel takes the grid cell under its centre (level-0 px).
    centre_x = (np.arange(cols) + 0.5) * width / cols
    centre_y = (np.arange(rows) + 0.5) * height / rows
    cell_col = np.minimum((centre_x // patch_px).astype(np.int64), grid.shape[1] - 1)
    cell_row = np.minimum((centre_y // patch_px).astype(np.int64), grid.shape[0] - 1)
    values = grid[cell_row[:, None], cell_col[None, :]]  # (rows, cols)

    analysed = ~np.isnan(values)
    levels = np.round(np.nan_to_num(values) * 255).astype(np.uint8)
    bgr = cv.applyColorMap(levels, COLORMAP)  # OpenCV images are BGR
    alpha = np.where(analysed, 255, 0).astype(np.uint8)
    bgra = np.dstack([bgr, alpha])

    ok, png = cv.imencode(".png", bgra)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return png.tobytes()
