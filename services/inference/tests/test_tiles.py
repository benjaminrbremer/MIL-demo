import io
import logging
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from app import db
from app.db import SlideStatus
from app.tiles import DeepZoomCache
from tests.fakes import (
    IMAGE_SLIDE_SIZE,
    PHI_NAME,
    FakeBrokenImageSlide,
    FakeImageSlide,
)

METADATA = {
    "width": IMAGE_SLIDE_SIZE[0],
    "height": IMAGE_SLIDE_SIZE[1],
    "level_count": 1,
    "mpp_x": None,
    "mpp_y": None,
}
# A 1000 x 600 image has Deep Zoom levels 0 (1 x 1 px) to 10 (full size).
TOP_LEVEL = 10
TOP_LEVEL_TILES = (4, 3)  # ceil(1000 / 254), ceil(600 / 254)
DZI_NS = "{http://schemas.microsoft.com/deepzoom/2008}"


class CountingOpener:
    """Opener that records each path it opens and returns a given slide class."""

    def __init__(self, slide_class=FakeImageSlide) -> None:
        """Remember the slide class to construct."""
        self.slide_class = slide_class
        self.opened: list[str] = []

    def __call__(self, path: str):
        """Record the path and open a fake slide."""
        self.opened.append(path)
        return self.slide_class(path)


@pytest.fixture
def opener(app) -> CountingOpener:
    """Install a tile cache backed by in-memory fake slides; return its opener."""
    opener = CountingOpener()
    app.state.tile_cache = DeepZoomCache(opener=opener)
    return opener


@pytest.fixture
def db_path(app, client):
    """The running app's database (created by the lifespan in `client`)."""
    return app.state.db_path


def add_ready_slide(db_path, file_path: str = "/acq/slide.tif") -> str:
    """Insert a ready slide row and return its ID."""
    slide_id = db.ensure_arriving(db_path, file_path, "2026-10-07T14:00:00Z")
    db.mark_ready(db_path, slide_id, "a" * 64, METADATA, "2026-10-07T14:00:08Z")
    return slide_id


def tile_url(slide_id: str, level: int = TOP_LEVEL, col: int = 0, row: int = 0) -> str:
    """URL of one Deep Zoom tile."""
    return f"/v1/slides/{slide_id}_files/{level}/{col}_{row}.jpeg"


def test_req_007_dzi_descriptor_for_ready_slide(client, auth_headers, db_path, opener):
    """REQ-007: a ready slide's .dzi descriptor gives size, tile size, overlap, format."""
    slide_id = add_ready_slide(db_path)

    response = client.get(f"/v1/slides/{slide_id}.dzi", headers=auth_headers)

    # Also proves the route isn't shadowed by GET /v1/slides/{slide_id}.
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    image = ET.fromstring(response.text)
    assert image.attrib == {"Format": "jpeg", "Overlap": "1", "TileSize": "254"}
    size = image.find(f"{DZI_NS}Size")
    assert size.attrib == {"Width": "1000", "Height": "600"}


def test_req_007_tile_is_jpeg(client, auth_headers, db_path, opener):
    """REQ-007: a tile is a JPEG of tile size plus overlap, cacheable privately."""
    slide_id = add_ready_slide(db_path)

    response = client.get(tile_url(slide_id), headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=3600"
    tile = Image.open(io.BytesIO(response.content))
    assert tile.format == "JPEG"
    # Top-left tile: 254 px plus 1 px overlap on the right and bottom only.
    assert tile.size == (255, 255)


def test_req_007_edge_tile_is_clipped(client, auth_headers, db_path, opener):
    """REQ-007: the bottom-right tile covers only what is left of the image."""
    slide_id = add_ready_slide(db_path)
    last_col, last_row = TOP_LEVEL_TILES[0] - 1, TOP_LEVEL_TILES[1] - 1

    response = client.get(
        tile_url(slide_id, col=last_col, row=last_row), headers=auth_headers
    )

    tile = Image.open(io.BytesIO(response.content))
    # 1000 - 3 * 254 = 238 and 600 - 2 * 254 = 92, plus 1 px left/top overlap.
    assert tile.size == (239, 93)


def test_unknown_slide_is_404_not_found(client, auth_headers, opener):
    """An unknown slide ID gets 404 NOT_FOUND from both tile endpoints."""
    for path in ["/v1/slides/no-such-slide.dzi", tile_url("no-such-slide")]:
        response = client.get(path, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    assert opener.opened == []


@pytest.mark.parametrize(
    "status", [SlideStatus.ARRIVING, SlideStatus.REGISTERING, SlideStatus.UNREADABLE]
)
def test_slide_not_ready_is_409(client, auth_headers, db_path, opener, status):
    """A slide that isn't ready gets 409 SLIDE_NOT_READY and is never opened."""
    slide_id = db.ensure_arriving(db_path, "/acq/slide.tif", "2026-10-07T14:00:00Z")
    db.set_status(db_path, slide_id, status)

    for path in [f"/v1/slides/{slide_id}.dzi", tile_url(slide_id)]:
        response = client.get(path, headers=auth_headers)

        assert response.status_code == 409
        assert response.json() == {
            "error": {"code": "SLIDE_NOT_READY", "message": "Slide is not ready"}
        }
    assert opener.opened == []


@pytest.mark.parametrize(
    ("level", "col", "row"),
    [
        (TOP_LEVEL + 1, 0, 0),  # level past the top
        (TOP_LEVEL, TOP_LEVEL_TILES[0], 0),  # column past the edge
        (TOP_LEVEL, 0, TOP_LEVEL_TILES[1]),  # row past the edge
        (0, 1, 0),  # level 0 is a single 1 x 1 px tile
    ],
)
def test_tile_out_of_range_is_404(
    client, auth_headers, db_path, opener, level, col, row
):
    """A level or tile address outside the pyramid gets 404 NOT_FOUND."""
    slide_id = add_ready_slide(db_path)

    response = client.get(tile_url(slide_id, level, col, row), headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("segment", ["x/0_0", "-1/0_0", "10/a_0", "10/0_-1"])
def test_non_numeric_tile_path_is_404(client, auth_headers, db_path, opener, segment):
    """Non-digit level, column, or row segments match no route: 404 NOT_FOUND."""
    slide_id = add_ready_slide(db_path)

    response = client.get(
        f"/v1/slides/{slide_id}_files/{segment}.jpeg", headers=auth_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", ["/v1/slides/anything.dzi", tile_url("anything")])
def test_req_019_tile_endpoints_require_token(client, path):
    """REQ-019: tile endpoints reject requests without the token."""
    assert client.get(path).status_code == 401


def test_req_004_tiles_never_read_associated_images(
    client, auth_headers, db_path, opener
):
    """REQ-004: serving a descriptor and tiles never touches associated images."""
    # FakeImageSlide.associated_images raises; any access would fail the request.
    slide_id = add_ready_slide(db_path)

    responses = [
        client.get(f"/v1/slides/{slide_id}.dzi", headers=auth_headers),
        *(
            client.get(tile_url(slide_id, level), headers=auth_headers)
            for level in range(TOP_LEVEL + 1)
        ),
    ]

    assert all(response.status_code == 200 for response in responses)


def test_req_006_missing_file_error_has_no_path(
    app, client, auth_headers, db_path, tmp_path, caplog
):
    """REQ-006: a ready slide whose file is gone gives 409 without its path or name."""
    caplog.set_level(logging.DEBUG)
    # Real OpenSlide, opening a file that no longer exists (D-029).
    app.state.tile_cache = DeepZoomCache()
    missing = tmp_path / "gone" / PHI_NAME
    slide_id = add_ready_slide(db_path, str(missing))

    for path in [f"/v1/slides/{slide_id}.dzi", tile_url(slide_id)]:
        response = client.get(path, headers=auth_headers)

        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "SLIDE_UNREADABLE",
                "message": "The slide file could not be opened",
            }
        }
        assert "DOE-JOHN" not in response.text
    assert "DOE-JOHN" not in caplog.text
    assert str(missing.parent) not in caplog.text
    # The row is left as it was (D-029).
    assert db.get_slide(db_path, slide_id)["status"] == "ready"


def test_req_006_tile_read_error_has_no_path_and_evicts(
    client, auth_headers, db_path, opener, caplog
):
    """REQ-006: a tile read error gives 409 without the path, and the slide is reopened."""
    caplog.set_level(logging.DEBUG)
    opener.slide_class = FakeBrokenImageSlide
    slide_id = add_ready_slide(db_path)

    first = client.get(tile_url(slide_id), headers=auth_headers)
    second = client.get(tile_url(slide_id), headers=auth_headers)

    assert first.status_code == 409
    assert first.json()["error"]["code"] == "SLIDE_UNREADABLE"
    assert "DOE-JOHN" not in first.text
    assert "DOE-JOHN" not in caplog.text
    # The failed handle was evicted, so the second request opened the file again.
    assert second.status_code == 409
    assert len(opener.opened) == 2


def test_slide_is_opened_once_for_many_tiles(client, auth_headers, db_path, opener):
    """The descriptor and many tiles of one slide share a single open handle."""
    slide_id = add_ready_slide(db_path)

    client.get(f"/v1/slides/{slide_id}.dzi", headers=auth_headers)
    for col in range(TOP_LEVEL_TILES[0]):
        client.get(tile_url(slide_id, col=col), headers=auth_headers)

    assert opener.opened == ["/acq/slide.tif"]


def test_cache_evicts_least_recently_used():
    """Past capacity, the least recently used slide is dropped and reopened later."""
    opener = CountingOpener()
    cache = DeepZoomCache(opener=opener, capacity=2)

    cache.get("a", "/a")
    cache.get("b", "/b")
    cache.get("a", "/a")  # "a" is now more recent than "b"
    cache.get("c", "/c")  # evicts "b"
    cache.get("a", "/a")
    cache.get("b", "/b")

    assert opener.opened == ["/a", "/b", "/c", "/b"]


def test_cache_does_not_keep_failed_opens():
    """A failed open isn't cached, so the next request tries the file again."""
    calls = []

    def flaky_opener(path):
        """Fail the first open, succeed after that."""
        calls.append(path)
        if len(calls) == 1:
            raise FileNotFoundError(path)
        return FakeImageSlide(path)

    cache = DeepZoomCache(opener=flaky_opener)

    with pytest.raises(FileNotFoundError):
        cache.get("a", "/a")
    cache.get("a", "/a")
    cache.get("a", "/a")

    assert calls == ["/a", "/a"]


def test_close_all_closes_cached_slides():
    """close_all closes every cached slide and empties the cache."""
    slides = []

    def recording_opener(path):
        """Open a fake slide and keep a reference to it."""
        slides.append(FakeImageSlide(path))
        return slides[-1]

    cache = DeepZoomCache(opener=recording_opener)
    cache.get("a", "/a")
    cache.get("b", "/b")

    cache.close_all()

    for slide in slides:
        with pytest.raises(ValueError, match="closed"):
            slide.read_region((0, 0), 0, (1, 1))
    cache.get("a", "/a")
    assert len(slides) == 3


@pytest.mark.skipif(
    not os.environ.get("TEST_SLIDE_PATH"), reason="set TEST_SLIDE_PATH to a real WSI"
)
def test_req_007_real_slide_serves_tiles(app, client, auth_headers, db_path):
    """REQ-007: a real WSI serves a descriptor and JPEG tiles at low and full zoom."""
    source = Path(os.environ["TEST_SLIDE_PATH"]).expanduser()
    app.state.tile_cache = DeepZoomCache()  # real OpenSlide
    slide_id = add_ready_slide(db_path, str(source))

    dzi = client.get(f"/v1/slides/{slide_id}.dzi", headers=auth_headers)
    size = ET.fromstring(dzi.text).find(f"{DZI_NS}Size").attrib
    top_level = math.ceil(math.log2(max(int(size["Width"]), int(size["Height"]))))
    lowest = client.get(tile_url(slide_id, level=0), headers=auth_headers)
    full = client.get(tile_url(slide_id, level=top_level), headers=auth_headers)

    assert dzi.status_code == 200
    for response in (lowest, full):
        assert response.status_code == 200
        assert Image.open(io.BytesIO(response.content)).format == "JPEG"
