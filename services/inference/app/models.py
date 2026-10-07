"""Model manifest, startup hash check, and loading (D-040, D-041, REQ-016, REQ-020).

models/manifest.json names the exact weight files: Hugging Face repo,
pinned revision, SHA-256, licence, and (for the MIL model) its config.
At startup every file is hashed and compared with the manifest. A missing
file or a mismatch raises ModelError, and the service refuses to start.

Both models are TorchScript files. They are loaded once and put in
`.eval()` mode: the MIL file is saved in training mode, so without
`.eval()` its dropout layers stay on and every run gives a different
answer (spike: 0.164-0.167 on identical input).
"""

import hashlib
import json
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
CHUNK_BYTES = 1 << 20  # 1 MiB
SHORT_REVISION_LENGTH = 8  # the reported `version`, e.g. "507b473a" (D-040)
ROLES = ("encoder", "mil")


class ModelError(Exception):
    """The model files can't be trusted or loaded; the service must not start."""


@dataclass(frozen=True)
class LoadedModels:
    """Both models, ready for inference, plus what is reported about them."""

    encoder: object  # torch.nn.Module / ScriptModule, called on (B, 3, 224, 224)
    mil: object  # called on (N, 768) features, returns (logits, attention)
    device: str  # "cuda:0" or "cpu"
    class_names: tuple[str, ...]
    patch_size_um: float
    encoder_sha256: str
    # {role, name, version, sha256} per model: served by /v1/health and
    # stored on every completed job (REQ-015, REQ-018).
    infos: tuple[dict, ...]


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks so large weights don't fill memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(models_dir: Path) -> dict[str, dict]:
    """Read the manifest and return its entries keyed by role."""
    try:
        manifest = json.loads((models_dir / MANIFEST_FILENAME).read_text())
    except (OSError, ValueError) as exc:
        raise ModelError(f"model manifest unreadable ({type(exc).__name__})") from None
    entries = {entry["role"]: entry for entry in manifest.get("models", [])}
    missing = [role for role in ROLES if role not in entries]
    if missing:
        raise ModelError(f"model manifest has no entry for: {', '.join(missing)}")
    return entries


def verify_weights(models_dir: Path, entries: dict[str, dict]) -> None:
    """Hash every weight file; raise ModelError if one is missing or differs (REQ-016)."""
    for role in ROLES:
        entry = entries[role]
        path = models_dir / entry["local_path"]
        # Messages name the role only. The fix is the same either way:
        # run scripts/fetch_models.py.
        if not path.is_file():
            raise ModelError(
                f"{role} model weights missing; run scripts/fetch_models.py"
            )
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            raise ModelError(
                f"{role} model weights fail their SHA-256 check "
                f"(expected {entry['sha256'][:12]}..., got {actual[:12]}...)"
            )
        logger.info("Verified %s model %s (%s)", role, entry["name"], actual[:12])


def model_infos(entries: dict[str, dict]) -> tuple[dict, ...]:
    """The {role, name, version, sha256} records for both models."""
    return tuple(
        {
            "role": role,
            "name": entries[role]["name"],
            "version": entries[role]["revision"][:SHORT_REVISION_LENGTH],
            "sha256": entries[role]["sha256"],
        }
        for role in ROLES
    )


def _load_torchscript(path: Path, device: str):
    """Load one TorchScript file onto a device, in inference (eval) mode."""
    import torch

    # torch.jit.load is deprecated in PyTorch 2.14 but works (D-040). The
    # warning would print at every startup, so it is silenced for this call only.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        model = torch.jit.load(str(path), map_location=device)
    # .eval() switches dropout off for the whole module tree (REQ-020).
    return model.eval()


def default_device() -> str:
    """The first CUDA GPU if there is one, otherwise the CPU."""
    import torch

    return "cuda:0" if torch.cuda.is_available() else "cpu"


def load_models(models_dir: Path, device: str | None = None) -> LoadedModels:
    """Verify the weights against the manifest, then load both models."""
    entries = load_manifest(models_dir)
    verify_weights(models_dir, entries)
    device = device or default_device()
    encoder = _load_torchscript(models_dir / entries["encoder"]["local_path"], device)
    mil = _load_torchscript(models_dir / entries["mil"]["local_path"], device)
    config = entries["mil"]["config"]
    logger.info("Models loaded on %s", device)
    return LoadedModels(
        encoder=encoder,
        mil=mil,
        device=device,
        class_names=tuple(config["class_names"]),
        patch_size_um=float(config["patch_size_um"]),
        encoder_sha256=entries["encoder"]["sha256"],
        infos=model_infos(entries),
    )
