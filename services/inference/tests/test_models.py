"""Model manifest, startup hash check, and inference mode (REQ-016, REQ-020)."""

import json
import warnings
from pathlib import Path

import pytest
import torch

from app.config import DEFAULT_MODELS_DIR
from app.main import create_app
from app.models import ModelError, load_manifest, load_models, sha256_of

REAL_WEIGHTS_PRESENT = all(
    (DEFAULT_MODELS_DIR / entry["local_path"]).is_file()
    for entry in json.loads((DEFAULT_MODELS_DIR / "manifest.json").read_text())[
        "models"
    ]
)


class DropoutModel(torch.nn.Module):
    """Like the MIL file: dropout that is only off in eval mode."""

    def __init__(self) -> None:
        """A linear layer behind heavy dropout."""
        super().__init__()
        self.dropout = torch.nn.Dropout(0.5)
        self.linear = torch.nn.Linear(8, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Dropout, then the linear layer."""
        return self.linear(self.dropout(x))


def write_models_dir(tmp_path: Path, *, corrupt: str | None = None) -> Path:
    """A models folder with two TorchScript files saved in training mode."""
    models_dir = tmp_path / "models"
    (models_dir / "weights").mkdir(parents=True)
    entries = []
    for role in ("encoder", "mil"):
        path = models_dir / "weights" / f"{role}.pt"
        with warnings.catch_warnings():
            # Deprecated in PyTorch 2.14, but it's how the real files were made.
            warnings.simplefilter("ignore", FutureWarning)
            model = torch.jit.script(DropoutModel())
        assert model.training  # saved in training mode, like the MIL file
        model.save(str(path))
        entry = {
            "role": role,
            "name": f"test/{role}",
            "revision": "0123456789abcdef",
            "local_path": f"weights/{role}.pt",
            "sha256": sha256_of(path),
        }
        if role == "mil":
            entry["config"] = {"patch_size_um": 128, "class_names": ["a", "b"]}
        entries.append(entry)
        if role == corrupt:
            with path.open("ab") as f:
                f.write(b"\0")
    (models_dir / "manifest.json").write_text(json.dumps({"models": entries}))
    return models_dir


def test_req_016_startup_refused_on_hash_mismatch(tmp_path):
    """REQ-016: a weight file that differs from the manifest stops loading."""
    models_dir = write_models_dir(tmp_path, corrupt="mil")

    with pytest.raises(ModelError, match="mil model weights fail their SHA-256"):
        load_models(models_dir, device="cpu")


def test_req_016_startup_refused_on_missing_weights(tmp_path):
    """REQ-016: a missing weight file stops loading, without naming the path."""
    models_dir = write_models_dir(tmp_path)
    (models_dir / "weights" / "encoder.pt").unlink()

    with pytest.raises(ModelError) as excinfo:
        load_models(models_dir, device="cpu")

    assert "encoder model weights missing" in str(excinfo.value)
    assert str(tmp_path) not in str(excinfo.value)


def test_req_016_create_app_refuses_to_start_on_hash_mismatch(settings, tmp_path):
    """REQ-016: the app itself can't be built with a bad weight file."""
    models_dir = write_models_dir(tmp_path, corrupt="encoder")

    with pytest.raises(ModelError):
        create_app(
            settings, model_loader=lambda _: load_models(models_dir, device="cpu")
        )


def test_req_016_manifest_must_name_both_models(tmp_path):
    """REQ-016: a manifest without both roles is rejected."""
    (tmp_path / "manifest.json").write_text(json.dumps({"models": []}))

    with pytest.raises(ModelError, match="encoder, mil"):
        load_manifest(tmp_path)


def test_req_016_committed_manifest_pins_both_models():
    """REQ-016: the committed manifest pins a full revision and hash per model."""
    entries = load_manifest(DEFAULT_MODELS_DIR)

    for entry in entries.values():
        assert len(entry["revision"]) == 40
        assert len(entry["sha256"]) == 64
        assert entry["revision"] in entry["url"]
    assert entries["mil"]["config"]["class_names"] == ["no-metastasis", "metastasis"]


def test_req_020_loader_puts_models_in_eval_mode(tmp_path):
    """REQ-020: models saved in training mode are loaded in eval mode, so runs repeat."""
    models = load_models(write_models_dir(tmp_path), device="cpu")
    x = torch.ones(4, 8)

    for model in (models.encoder, models.mil):
        assert not any(module.training for module in model.modules())
        with torch.inference_mode():
            assert torch.equal(model(x), model(x))


def test_load_models_reports_short_revision_and_hash(tmp_path):
    """Model infos carry repo name, short revision, and full hash (REQ-015)."""
    models = load_models(write_models_dir(tmp_path), device="cpu")

    assert [info["role"] for info in models.infos] == ["encoder", "mil"]
    assert models.infos[1]["name"] == "test/mil"
    assert models.infos[1]["version"] == "01234567"
    assert len(models.infos[1]["sha256"]) == 64
    assert models.class_names == ("a", "b")


def test_req_018_health_lists_loaded_models(client):
    """REQ-018: health reports the loaded models' names, versions, and hashes."""
    body = client.get("/v1/health").json()

    assert [m["role"] for m in body["models"]] == ["encoder", "mil"]
    assert body["models"][1] == {
        "role": "mil",
        "name": "fake/mil",
        "version": "bbbbbbbb",
        "sha256": "f" * 64,
    }


@pytest.mark.models
@pytest.mark.skipif(not REAL_WEIGHTS_PRESENT, reason="real weights not fetched")
def test_req_020_real_mil_model_repeat_run_identical():
    """REQ-020: the real MIL model gives identical output on identical input."""
    models = load_models(DEFAULT_MODELS_DIR)
    features = torch.randn(2000, 768, generator=torch.Generator().manual_seed(0))

    with torch.inference_mode():
        first = models.mil(features.to(models.device))
        second = models.mil(features.to(models.device))

    assert torch.equal(first[0], second[0])  # logits
    assert torch.equal(first[1], second[1])  # attention
