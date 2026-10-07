"""scripts/fetch_models.py: download, hash check, atomic install (D-041, REQ-016)."""

import hashlib
import io
import json

import pytest

from scripts import fetch_models

CONTENT = b"pretend model weights"


@pytest.fixture
def models_dir(tmp_path):
    """A models folder whose manifest pins CONTENT's hash."""
    manifest = {
        "models": [
            {
                "role": "mil",
                "url": "https://example.invalid/model.pt",
                "local_path": "weights/mil.pt",
                "sha256": hashlib.sha256(CONTENT).hexdigest(),
            }
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def serve(monkeypatch, body: bytes) -> list[str]:
    """Make urlopen return `body`; return the list of requested URLs."""
    requested = []

    def fake_urlopen(url):
        requested.append(url)
        return io.BytesIO(body)

    monkeypatch.setattr(fetch_models.urllib.request, "urlopen", fake_urlopen)
    return requested


def test_req_016_fetch_installs_file_with_matching_hash(models_dir, monkeypatch):
    """REQ-016: a download with the pinned hash is moved into place."""
    serve(monkeypatch, CONTENT)

    assert fetch_models.main(models_dir) == 0

    assert (models_dir / "weights" / "mil.pt").read_bytes() == CONTENT


def test_req_016_fetch_rejects_hash_mismatch(models_dir, monkeypatch, capsys):
    """REQ-016: a download with the wrong hash fails and leaves nothing behind."""
    serve(monkeypatch, b"tampered weights")

    assert fetch_models.main(models_dir) == 1

    assert list((models_dir / "weights").iterdir()) == []
    assert "SHA-256 mismatch" in capsys.readouterr().err


def test_fetch_skips_file_already_present(models_dir, monkeypatch):
    """A file already present with the right hash is not downloaded again."""
    (models_dir / "weights").mkdir()
    (models_dir / "weights" / "mil.pt").write_bytes(CONTENT)
    requested = serve(monkeypatch, CONTENT)

    assert fetch_models.main(models_dir) == 0

    assert requested == []
