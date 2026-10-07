"""Download the pinned model weights and check their hashes (D-041).

Run once per machine, from services/inference/:

    uv run python scripts/fetch_models.py

Standard library only, so it needs no huggingface_hub. Each file in
models/manifest.json is streamed from its pinned-revision URL into a
temporary file next to its destination, hashed while it is written, and
moved into place only if the SHA-256 matches. A mismatch deletes the
temporary file and exits non-zero. Files already present with the right
hash are skipped. The service itself never touches the network.
"""

import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
CHUNK_BYTES = 1 << 20  # 1 MiB


class FetchError(Exception):
    """A download that failed or did not match its pinned hash."""


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks so large weights don't fill memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(entry: dict, models_dir: Path) -> bool:
    """Make sure one manifest entry is on disk; return True if it was downloaded."""
    dest = models_dir / entry["local_path"]
    if dest.is_file() and sha256_of(dest) == entry["sha256"]:
        print(f"{entry['role']}: already present, hash OK")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as the destination, so os.replace is an atomic rename.
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".fetch-")
    tmp = Path(tmp_name)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(entry["url"]) as resp:
            while chunk := resp.read(CHUNK_BYTES):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != entry["sha256"]:
            raise FetchError(
                f"{entry['role']}: SHA-256 mismatch "
                f"(expected {entry['sha256']}, got {digest.hexdigest()})"
            )
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"{entry['role']}: downloaded, hash OK")
    return True


def main(models_dir: Path = MODELS_DIR) -> int:
    """Fetch every model in the manifest; return the process exit code."""
    manifest = json.loads((models_dir / "manifest.json").read_text())
    try:
        for entry in manifest["models"]:
            fetch(entry, models_dir)
    except (FetchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
