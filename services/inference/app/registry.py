"""Acquisition-folder polling and slide registration (REQ-001 to REQ-006).

A background thread scans the folder every 2 s (D-006). Each slide file
moves through:

    arriving     seen; waiting until size and mtime are unchanged for 5 s,
                 because a file appears before copying has finished (REQ-002)
    registering  hashing (SHA-256, REQ-003) and reading metadata
    ready        or
    unreadable   OpenSlide could not open it (SLIDE_UNREADABLE)

PHI rules (D-009):
- Metadata comes from an explicit allowlist: dimensions, level count, and
  microns per pixel (REQ-005). Nothing else is read from the properties.
- Associated images (label, macro) are never accessed (REQ-004). The label
  image of a real slide can show a patient name or barcode.
- File paths and names never appear in logs (REQ-006); log lines use the
  slide ID. Exception text is not logged either, because OpenSlide's error
  messages include the file path.
"""

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import openslide

from app import db
from app.db import SlideStatus
from app.errors import ErrorCode

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 2.0
STABLE_SECONDS = 5.0
HASH_CHUNK_BYTES = 1024 * 1024
# Single-file formats OpenSlide reads. .mrxs is left out: it is an index
# file plus a directory of data files, which the size check can't cover.
SLIDE_EXTENSIONS = frozenset({".tif", ".tiff", ".svs", ".ndpi", ".scn", ".bif"})
UNREADABLE_MESSAGE = "The slide file could not be opened"
_DONE_STATUSES = (SlideStatus.READY, SlideStatus.UNREADABLE)


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file, read in chunks so memory use stays flat."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _float_or_none(value: str | None) -> float | None:
    """Parse a property value as float; None if absent or not a number."""
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def read_metadata(path: Path, opener: Callable = openslide.OpenSlide) -> dict:
    """Open a slide and return only the allowlisted metadata (REQ-005)."""
    # `opener` is a parameter so tests can pass a fake slide class.
    with opener(str(path)) as slide:
        width, height = slide.dimensions
        properties = slide.properties
        return {
            "width": width,
            "height": height,
            "level_count": slide.level_count,
            # Optional in the file; CAMELYON16 TIFFs may lack it (spike).
            "mpp_x": _float_or_none(properties.get(openslide.PROPERTY_NAME_MPP_X)),
            "mpp_y": _float_or_none(properties.get(openslide.PROPERTY_NAME_MPP_Y)),
        }


@dataclass
class _Pending:
    """In-memory stability tracking for one file that is not yet registered."""

    slide_id: str
    size: int
    mtime_ns: int
    unchanged_since: float  # clock time when size/mtime last changed


class Registry:
    """Polls the acquisition folder and registers slide files into SQLite."""

    def __init__(
        self,
        acquisition_dir: Path,
        db_path: Path,
        *,
        opener: Callable = openslide.OpenSlide,
        stable_seconds: float = STABLE_SECONDS,
        poll_interval: float = POLL_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Configure the registry; nothing runs until start() or scan_once()."""
        self._dir = acquisition_dir
        self._db_path = db_path
        self._opener = opener
        self._stable_seconds = stable_seconds
        self._poll_interval = poll_interval
        # Monotonic clock: unaffected by system clock changes. Tests pass
        # explicit times to scan_once() instead.
        self._clock = clock
        self._pending: dict[str, _Pending] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the polling thread."""
        # daemon=True: a stuck thread can't keep the process alive on exit.
        self._thread = threading.Thread(
            target=self._run, name="slide-registry", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the polling thread to finish and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        """Thread body: scan, then sleep until the next poll or a stop request."""
        logger.info("Slide registry polling every %.0f s", self._poll_interval)
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:  # noqa: BLE001 - keep polling whatever happens
                logger.error("Registry scan failed: %s", type(exc).__name__)
            # wait() returns early when stop() is called, so shutdown is fast.
            self._stop.wait(self._poll_interval)

    def scan_once(self, now: float | None = None) -> None:
        """Run one polling pass over the folder."""
        now = self._clock() if now is None else now
        done = db.paths_with_status(self._db_path, _DONE_STATUSES)
        seen = set()
        for path in self._candidates():
            key = str(path)
            if key in done:
                continue
            seen.add(key)
            try:
                self._advance(path, now)
            except FileNotFoundError:
                # Deleted between listing and reading; forget it.
                self._pending.pop(key, None)
            except Exception as exc:  # noqa: BLE001 - one bad file can't stop the scan
                pending = self._pending.get(key)
                logger.error(
                    "Registry error for slide %s: %s",
                    pending.slide_id if pending else "(new)",
                    type(exc).__name__,
                )
        # Stop tracking files that disappeared while arriving. Their row is
        # left as-is (known limitation, v0.1).
        for key in self._pending.keys() - seen:
            del self._pending[key]

    def _candidates(self) -> Iterator[Path]:
        """Slide files at the top level of the folder; hidden files skipped."""
        with os.scandir(self._dir) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if Path(entry.name).suffix.lower() not in SLIDE_EXTENSIONS:
                    continue
                # is_file() follows symlinks, so a link to a slide counts.
                if entry.is_file():
                    yield Path(entry.path)

    def _advance(self, path: Path, now: float) -> None:
        """Move one not-yet-registered file one step through its lifecycle."""
        key = str(path)
        stat = path.stat()
        pending = self._pending.get(key)

        if pending is None:
            slide_id = db.ensure_arriving(self._db_path, key, db.utc_now_iso())
            self._pending[key] = _Pending(slide_id, stat.st_size, stat.st_mtime_ns, now)
            logger.info("Slide %s detected", slide_id)
            return

        if (stat.st_size, stat.st_mtime_ns) != (pending.size, pending.mtime_ns):
            # Still being written: restart the stability window.
            pending.size, pending.mtime_ns = stat.st_size, stat.st_mtime_ns
            pending.unchanged_since = now
            return

        if now - pending.unchanged_since >= self._stable_seconds:
            self._register(path, pending, now)

    def _register(self, path: Path, pending: _Pending, now: float) -> None:
        """Hash a stable file, read its metadata, and store the outcome."""
        key = str(path)
        slide_id = pending.slide_id
        db.set_status(self._db_path, slide_id, SlideStatus.REGISTERING)
        logger.info("Slide %s registering", slide_id)

        digest = sha256_file(path)

        # A copy that paused for over 5 s and then resumed would change the
        # file under us. Check again after hashing, before trusting the hash.
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (pending.size, pending.mtime_ns):
            db.set_status(self._db_path, slide_id, SlideStatus.ARRIVING)
            pending.size, pending.mtime_ns = stat.st_size, stat.st_mtime_ns
            pending.unchanged_since = now
            logger.info("Slide %s changed while hashing; waiting again", slide_id)
            return

        try:
            metadata = read_metadata(path, self._opener)
        except Exception as exc:  # noqa: BLE001 - see comment below
            # Any failure to open or read means the file is unusable. Store a
            # fixed message: exception text from OpenSlide contains the path.
            db.mark_unreadable(
                self._db_path,
                slide_id,
                digest,
                ErrorCode.SLIDE_UNREADABLE,
                UNREADABLE_MESSAGE,
            )
            logger.warning("Slide %s unreadable: %s", slide_id, type(exc).__name__)
        else:
            db.mark_ready(self._db_path, slide_id, digest, metadata, db.utc_now_iso())
            logger.info("Slide %s ready", slide_id)
        del self._pending[key]
