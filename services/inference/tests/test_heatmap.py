"""Heatmap rendering tests (REQ-014, REQ-006, D-053)."""

import struct

import cv2 as cv
import numpy as np
import pytest

from app.pipeline.heatmap import COLORMAP, normalize, render_heatmap

# A 1000 x 600 px slide with 100 px patches: a 10 x 6 grid. The output is
# 200 x 120 px, so each patch covers exactly 20 x 20 output pixels.
SLIDE_SIZE = (1000, 600)
PATCH_PX = 100
OUT_SHAPE = (120, 200)


def decode(png: bytes) -> np.ndarray:
    """PNG bytes -> BGRA array."""
    return cv.imdecode(np.frombuffer(png, np.uint8), cv.IMREAD_UNCHANGED)


def colour(level: int) -> np.ndarray:
    """The BGR colour the colour map gives a level 0..255."""
    return cv.applyColorMap(np.array([[level]], np.uint8), COLORMAP)[0, 0]


def test_req_014_heatmap_aligned_to_slide():
    """REQ-014: each patch colours exactly its own area; other pixels are transparent."""
    # Grid cells (col, row): (0, 0) low, (9, 5) high (bottom-right corner),
    # (4, 2) in the middle.
    coords = np.array([[0, 0], [900, 500], [400, 200]], dtype=np.int64)
    attention = np.array([0.0, 1.0, 0.5], dtype=np.float32)

    image = decode(render_heatmap(coords, attention, SLIDE_SIZE, PATCH_PX, OUT_SHAPE))

    assert image.shape == (*OUT_SHAPE, 4)
    normalized = normalize(attention)
    for (x, y), value in zip(coords, normalized, strict=True):
        # The patch's output block: 20 x 20 px starting at (x, y) / 5.
        block = image[y // 5 : y // 5 + 20, x // 5 : x // 5 + 20]
        assert (block[:, :, 3] == 255).all()
        assert (block[:, :, :3] == colour(round(value * 255))).all()
    # Exactly the three patches' pixels are opaque.
    assert (image[:, :, 3] == 255).sum() == 3 * 20 * 20
    assert set(np.unique(image[:, :, 3])) == {0, 255}


def test_req_014_heatmap_covers_whole_slide_when_grid_overhangs():
    """REQ-014: the PNG spans [0, W] x [0, H] even when the last patch overhangs."""
    # 1050 px wide: the 11th grid column (x 1000-1100) runs past the edge.
    coords = np.array([[1000, 0]], dtype=np.int64)
    image = decode(
        render_heatmap(coords, np.array([1.0]), (1050, 600), PATCH_PX, (120, 210))
    )

    # Output column c centres at level-0 x = (c + 0.5) * 5; x >= 1000 is c >= 200.
    assert (image[:20, 200:, 3] == 255).all()
    assert (image[:20, :200, 3] == 0).all()


def test_req_014_percentile_clip_resists_outlier():
    """REQ-014 / D-053: one extreme score doesn't squash the others together."""
    scores = np.concatenate([np.linspace(-6.0, -4.0, 200), [50.0]])

    normalized = normalize(scores)

    # Ordinary scores still spread over most of the range...
    assert normalized[:200].max() - normalized[:200].min() > 0.9
    # ...and the outlier saturates instead of stretching the scale.
    assert normalized[-1] == 1.0


def test_normalize_keeps_order_and_range():
    """Normalized values lie in [0, 1] and keep the ranking of the raw scores."""
    rng = np.random.default_rng(0)
    scores = rng.normal(-5, 1, 1000)

    normalized = normalize(scores)

    assert normalized.min() == 0.0 and normalized.max() == 1.0
    order = np.argsort(scores)
    assert (np.diff(normalized[order]) >= 0).all()


@pytest.mark.parametrize("n", [1, 20])
def test_equal_scores_do_not_divide_by_zero(n):
    """All-equal scores (or a single patch) render the lowest colour, no NaN."""
    normalized = normalize(np.full(n, -3.0))

    assert (normalized == 0.0).all()


def test_req_006_heatmap_png_has_no_text_chunks():
    """REQ-006: the PNG carries pixels only, no text or metadata chunks."""
    png = render_heatmap(
        np.array([[0, 0]]), np.array([1.0]), SLIDE_SIZE, PATCH_PX, OUT_SHAPE
    )

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    chunks, offset = [], 8
    while offset < len(png):
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        chunks.append(png[offset + 4 : offset + 8].decode("ascii"))
        offset += 12 + length  # length + type + data + CRC
    assert set(chunks) == {"IHDR", "IDAT", "IEND"}
