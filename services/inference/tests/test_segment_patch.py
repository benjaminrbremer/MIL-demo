"""Tissue segmentation and patch coordinates on synthetic images (D-039)."""

import numpy as np

from app.pipeline.patch import patch_size_px, tissue_patches
from app.pipeline.segment import _remove_small_components, tissue_mask

WHITE = (255, 255, 255)
PINK = (200, 120, 160)  # saturation about 102, well above 20
LAVENDER = (232, 228, 240)  # saturation about 13: tinted glass, not tissue

# At 10 um per pixel, the minimum object (200^2 um^2) is 400 px and the
# largest hole filled (190^2 um^2) is 361 px.
MPP = 10.0


def canvas(rows: int = 200, cols: int = 300, colour=WHITE) -> np.ndarray:
    """A plain RGB uint8 image."""
    image = np.empty((rows, cols, 3), np.uint8)
    image[:] = colour
    return image


def test_blank_glass_has_no_tissue():
    """White and lavender-tinted glass are both background at threshold 20."""
    assert not tissue_mask(canvas(), MPP).any()
    assert not tissue_mask(canvas(colour=LAVENDER), MPP).any()


def test_stained_region_is_tissue():
    """A saturated block is kept; nothing outside it is marked."""
    image = canvas()
    image[50:150, 100:200] = PINK

    mask = tissue_mask(image, MPP)

    # The 7 px median blur rounds off the corners, so check the inside.
    assert mask[55:145, 105:195].all()
    outside = np.ones_like(mask)
    outside[50:150, 100:200] = False
    assert not mask[outside].any()


def test_small_specks_are_removed():
    """An object smaller than 200^2 um^2 (here 400 px) is dropped."""
    image = canvas()
    image[20:35, 20:35] = PINK  # 225 px: too small
    image[100:130, 150:180] = PINK  # 900 px: kept

    mask = tissue_mask(image, MPP)

    assert not mask[20:35, 20:35].any()
    assert mask[105:125, 155:175].all()


def test_small_holes_are_filled_and_large_ones_kept():
    """A hole under 190^2 um^2 (361 px) becomes tissue; a bigger one doesn't."""
    image = canvas()
    image[20:180, 20:280] = PINK
    image[40:55, 40:55] = WHITE  # 225 px hole: filled
    image[80:140, 150:210] = WHITE  # 3,600 px hole: kept

    mask = tissue_mask(image, MPP)

    assert mask[40:55, 40:55].all()
    assert not mask[90:130, 160:200].any()


def test_objects_touching_only_at_a_corner_are_separate():
    """4-connectivity: two blocks meeting at one corner are two objects."""
    # Each block is 16 x 16 = 256 px (< 400); together 512 px (>= 400). With
    # 8-connectivity they'd count as one object and be kept. Tested on the
    # small-object step alone, because closing would bridge the corner.
    mask = np.zeros((60, 60), bool)
    mask[10:26, 10:26] = True
    mask[26:42, 26:42] = True

    assert not _remove_small_components(mask, 400).any()


def test_patch_size_is_rounded_to_whole_pixels():
    """128 um at 0.2263 um/px is 566 px, as in the spike."""
    assert patch_size_px(128, 0.2263) == 566


def test_patches_on_a_global_grid_in_x_major_order():
    """Patches whose centre is on tissue are kept, ordered by x, then y."""
    # Slide 1000 x 600 px, mask 10 x 6 (one mask pixel = 100 px), patch 200 px.
    # Patch centres at x = 100, 300, 500, 700, 900 and y = 100, 300, 500.
    mask = np.zeros((6, 10), bool)
    mask[0:4, 2:8] = True  # level-0 x 200-800, y 0-400

    coords = tissue_patches(mask, (1000, 600), 200)

    assert coords.tolist() == [
        [200, 0],
        [200, 200],
        [400, 0],
        [400, 200],
        [600, 0],
        [600, 200],
    ]
    assert coords.dtype == np.int64


def test_no_tissue_gives_no_patches():
    """An empty mask gives an empty (0, 2) array."""
    coords = tissue_patches(np.zeros((6, 10), bool), (1000, 600), 200)

    assert coords.shape == (0, 2)
