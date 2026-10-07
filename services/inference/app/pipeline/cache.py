"""Feature cache: skip patch reading and encoding for a slide seen before (D-046).

Feature extraction is about 99% of a run. Its output depends only on the
slide's pixels, the encoder, and which patches are taken, so those make
up the key:

    sha256("<slide SHA-256>:<encoder SHA-256>:<patch size um>:<threshold>")

The slide is identified by its content hash from registration (D-008),
never its filename. An entry is a folder with `coords.npy` and
`features.npy` under DATA_DIR/cache/<key>/. It is written to a temporary
folder and renamed into place, so a crash mid-write never leaves half an
entry that a later job would trust. No eviction in v0.1.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

import numpy as np

CACHE_DIRNAME = "cache"


def cache_key(
    slide_sha256: str, encoder_sha256: str, patch_size_um: float, threshold: int
) -> str:
    """The cache key for one slide, encoder, and patch setting."""
    raw = f"{slide_sha256}:{encoder_sha256}:{patch_size_um:g}:{threshold}"
    return hashlib.sha256(raw.encode()).hexdigest()


class FeatureCache:
    """Coordinates and features stored as .npy files, one folder per key."""

    def __init__(self, data_dir: Path) -> None:
        """Use DATA_DIR/cache/ (created on first write)."""
        self._root = data_dir / CACHE_DIRNAME

    def load(self, key: str) -> tuple[np.ndarray, np.ndarray] | None:
        """(coords, features) for a key, or None if not cached."""
        entry = self._root / key
        if not entry.is_dir():
            return None
        return np.load(entry / "coords.npy"), np.load(entry / "features.npy")

    def store(self, key: str, coords: np.ndarray, features: np.ndarray) -> None:
        """Save an entry atomically; an existing entry is left as it is."""
        entry = self._root / key
        if entry.exists():
            return
        self._root.mkdir(parents=True, exist_ok=True)
        # The temporary folder is in the same parent, so the rename is atomic.
        tmp = Path(tempfile.mkdtemp(dir=self._root, prefix=".tmp-"))
        try:
            np.save(tmp / "coords.npy", coords)
            np.save(tmp / "features.npy", features)
            tmp.rename(entry)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
