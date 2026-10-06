"""Deep Zoom descriptor and tile serving for ready slides (REQ-007).

OpenSeadragon (the web viewer, roadmap item 9) asks for a `.dzi` XML
descriptor, then for JPEG tiles at
`{id}_files/{level}/{col}_{row}.jpeg`. openslide-python's
DeepZoomGenerator maps those Deep Zoom coordinates onto the slide's own
pyramid levels and reads the pixels.

Tile parameters (D-030): 254 px tiles with 1 px overlap, so a full interior
tile is 256 px. limit_bounds=False keeps the Deep Zoom image the same size
as level 0, so the attention heatmap (level-0 coordinates) lines up with no
offset.

Open slides are kept in a small LRU cache (D-031). See DeepZoomCache.

PHI: DeepZoomGenerator reads only pyramid levels, never associated images
(REQ-004). The descriptor holds only tile size, overlap, format, and
dimensions. Errors carry fixed messages and logs carry exception types
only, because OpenSlide's exception text contains the file path (REQ-006).
"""

import io
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable

import openslide
from fastapi import APIRouter, HTTPException, Request, Response
from openslide.deepzoom import DeepZoomGenerator

from app import db
from app.db import SlideStatus
from app.errors import ApiError, ErrorCode
from app.registry import UNREADABLE_MESSAGE

logger = logging.getLogger(__name__)

TILE_SIZE = 254
TILE_OVERLAP = 1
LIMIT_BOUNDS = False
TILE_FORMAT = "jpeg"
JPEG_QUALITY = 75
TILE_CACHE_SLIDES = 4
# "private": tiles sit behind the device token, so shared caches must not
# keep them. A ready slide's pixels don't change, so an hour is safe.
TILE_CACHE_CONTROL = "private, max-age=3600"
NOT_READY_MESSAGE = "Slide is not ready"

router = APIRouter(prefix="/v1")


class DeepZoomCache:
    """Thread-safe LRU cache of open slides and their DeepZoomGenerators."""

    # Why a cache: OpenSeadragon requests dozens of tiles at once. Opening
    # the file for each one would re-parse the TIFF headers every time.
    # OpenSlide handles are safe to read from several threads at once, so
    # request threads share one handle per slide.
    #
    # Eviction drops the entry without closing it: another request thread
    # may still be reading from that handle. openslide-python closes the
    # underlying handle when the last reference is garbage-collected.

    def __init__(
        self,
        opener: Callable = openslide.OpenSlide,
        capacity: int = TILE_CACHE_SLIDES,
    ) -> None:
        """Configure the cache; `opener` is a parameter so tests can pass a fake."""
        self._opener = opener
        self._capacity = capacity
        # OrderedDict keeps insertion order; move_to_end marks recent use,
        # so the first item is always the least recently used.
        self._entries: OrderedDict[
            str, tuple[openslide.AbstractSlide, DeepZoomGenerator]
        ] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, slide_id: str, file_path: str) -> DeepZoomGenerator:
        """Return the generator for a slide, opening the file on a cache miss."""
        with self._lock:
            entry = self._entries.get(slide_id)
            if entry is not None:
                self._entries.move_to_end(slide_id)
                return entry[1]

        # Open outside the lock so a slow open doesn't stall tile requests
        # for slides that are already cached.
        slide = self._opener(file_path)
        generator = DeepZoomGenerator(
            slide, tile_size=TILE_SIZE, overlap=TILE_OVERLAP, limit_bounds=LIMIT_BOUNDS
        )
        logger.info("Slide %s opened for tiles", slide_id)

        with self._lock:
            # Another thread may have opened the same slide meanwhile. Keep
            # the cached one; ours is garbage-collected.
            entry = self._entries.get(slide_id)
            if entry is not None:
                self._entries.move_to_end(slide_id)
                return entry[1]
            self._entries[slide_id] = (slide, generator)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return generator

    def evict(self, slide_id: str) -> None:
        """Forget a slide so the next request opens it again."""
        with self._lock:
            self._entries.pop(slide_id, None)

    def close_all(self) -> None:
        """Close every cached slide; called at shutdown when no requests are running."""
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for slide, _ in entries:
            slide.close()


def _generator(request: Request, slide_id: str) -> DeepZoomGenerator:
    """The generator for a ready slide, or an error response via exception."""
    row = db.get_slide(request.app.state.db_path, slide_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Slide not found")
    if row["status"] != SlideStatus.READY:
        raise ApiError(409, ErrorCode.SLIDE_NOT_READY, NOT_READY_MESSAGE)
    try:
        return request.app.state.tile_cache.get(slide_id, row["file_path"])
    except Exception as exc:  # noqa: BLE001 - any open failure means unusable
        # Typically the file was moved or deleted after registration
        # (D-029). The row stays `ready`; only this request fails.
        logger.warning(
            "Slide %s could not be opened for tiles: %s", slide_id, type(exc).__name__
        )
        # `from None` drops the original exception (and its path) from the
        # chain of the one we raise.
        raise ApiError(409, ErrorCode.SLIDE_UNREADABLE, UNREADABLE_MESSAGE) from None


# These routes must be registered before GET /v1/slides/{slide_id}; see
# app/main.py.
@router.get("/slides/{slide_id}.dzi")
def get_dzi(slide_id: str, request: Request) -> Response:
    """Deep Zoom descriptor (XML) for a ready slide."""
    # Plain `def`: opening a slide blocks, so FastAPI runs this in a thread.
    generator = _generator(request, slide_id)
    return Response(generator.get_dzi(TILE_FORMAT), media_type="application/xml")


# `:int` is a Starlette path converter: the segment must be digits, so
# negative or non-numeric values never reach this function (404 instead).
@router.get("/slides/{slide_id}_files/{level:int}/{col:int}_{row:int}.jpeg")
def get_tile(
    slide_id: str, level: int, col: int, row: int, request: Request
) -> Response:
    """One JPEG tile of a ready slide; 404 if the level or address is out of range."""
    generator = _generator(request, slide_id)
    # Check the range ourselves rather than relying on get_tile's ValueError,
    # so a ValueError from anywhere else isn't mistaken for a bad address.
    if level >= generator.level_count:
        raise HTTPException(status_code=404, detail="Tile not found")
    cols, rows = generator.level_tiles[level]
    if col >= cols or row >= rows:
        raise HTTPException(status_code=404, detail="Tile not found")

    try:
        tile = generator.get_tile(level, (col, row))
    except openslide.OpenSlideError as exc:
        # After a read error an OpenSlide handle stays in an error state, so
        # drop it; the next request reopens the file.
        request.app.state.tile_cache.evict(slide_id)
        logger.warning("Slide %s tile read failed: %s", slide_id, type(exc).__name__)
        raise ApiError(409, ErrorCode.SLIDE_UNREADABLE, UNREADABLE_MESSAGE) from None

    buffer = io.BytesIO()
    tile.save(buffer, TILE_FORMAT, quality=JPEG_QUALITY)
    return Response(
        buffer.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": TILE_CACHE_CONTROL},
    )
