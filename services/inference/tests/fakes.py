"""Test doubles for OpenSlide and the models, shared across the tests."""

from pathlib import Path
from typing import ClassVar, Self

import openslide
import torch
from PIL import Image

from app.models import LoadedModels

# A filename that looks like PHI, so a leak is easy to spot.
PHI_NAME = "DOE-JOHN-1970-01-01.tif"


class FakeSlide:
    """Stands in for openslide.OpenSlide; fails loudly if associated images are read."""

    dimensions = (2000, 1000)
    level_count = 3
    properties: ClassVar[dict[str, str]] = {
        openslide.PROPERTY_NAME_MPP_X: "0.243",
        openslide.PROPERTY_NAME_MPP_Y: "0.244",
        openslide.PROPERTY_NAME_BARCODE: "PATIENT-BARCODE",
    }
    associated_images_read = False

    def __init__(self, path: str) -> None:
        """Accept a path like OpenSlide does."""

    def __enter__(self) -> Self:
        """Support `with`."""
        return self

    def __exit__(self, *exc) -> None:
        """Nothing to close."""

    @property
    def associated_images(self) -> dict:
        """Record the access and raise; registration must never get here."""
        FakeSlide.associated_images_read = True
        raise AssertionError("associated images must never be read")


class FakeSlideNoMpp(FakeSlide):
    """A slide whose file has no microns-per-pixel properties."""

    properties: ClassVar[dict[str, str]] = {}


class FakeSlideBadMpp(FakeSlide):
    """A slide whose microns-per-pixel properties are not numbers."""

    properties: ClassVar[dict[str, str]] = {
        openslide.PROPERTY_NAME_MPP_X: "n/a",
        openslide.PROPERTY_NAME_MPP_Y: "",
    }


def phi_opener(path: str):
    """FakeSlide for the file named PHI_NAME; real OpenSlide (which fails) otherwise."""
    if Path(path).name == PHI_NAME:
        return FakeSlide(path)
    return openslide.OpenSlide(path)


# Width and height of the in-memory slide used by the tile tests.
IMAGE_SLIDE_SIZE = (1000, 600)


class FakeImageSlide(openslide.ImageSlide):
    """A real in-memory slide for Deep Zoom; fails loudly if associated images are read."""

    def __init__(self, path: str) -> None:
        """Ignore the path and wrap a solid-colour Pillow image."""
        super().__init__(Image.new("RGB", IMAGE_SLIDE_SIZE, (200, 120, 160)))

    @property
    def associated_images(self) -> dict:
        """Raise; tile serving must never read associated images."""
        raise AssertionError("associated images must never be read")


class FakeBrokenImageSlide(FakeImageSlide):
    """A slide that opens but fails every pixel read, with a path in the error."""

    def read_region(self, location, level, size):
        """Fail like OpenSlide does on a corrupt region, path included."""
        raise openslide.OpenSlideError(f"Read error in /acq/{PHI_NAME}")


# Stand-ins for the two models: small, deterministic, CPU-only, and with
# the same input and output shapes as CTransPath and the ABMIL model.
FEATURE_DIM = 768
CLASS_NAMES = ("no-metastasis", "metastasis")
FAKE_ENCODER_SHA256 = "e" * 64


class FakeEncoder(torch.nn.Module):
    """(B, 3, 224, 224) -> (B, 768): mean colour per channel, tiled. Counts calls."""

    def __init__(self) -> None:
        """No weights, so no randomness."""
        super().__init__()
        self.calls = 0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode a batch."""
        self.calls += 1
        return x.mean(dim=(2, 3)).repeat(1, FEATURE_DIM // 3)


class FakeMil(torch.nn.Module):
    """(N, 768) -> (logits (1, 2), attention (N, 1)), like the ABMIL model."""

    def forward(self, h: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Score each patch by its mean feature; logits from the mean score."""
        attention = h.mean(dim=1, keepdim=True)
        score = attention.mean()
        return torch.stack([-score, score]).view(1, 2), attention


def fake_models() -> LoadedModels:
    """LoadedModels with the fake encoder and MIL model, on the CPU."""
    return LoadedModels(
        encoder=FakeEncoder(),
        mil=FakeMil(),
        device="cpu",
        class_names=CLASS_NAMES,
        patch_size_um=128.0,
        encoder_sha256=FAKE_ENCODER_SHA256,
        infos=(
            {
                "role": "encoder",
                "name": "fake/encoder",
                "version": "aaaaaaaa",
                "sha256": FAKE_ENCODER_SHA256,
            },
            {
                "role": "mil",
                "name": "fake/mil",
                "version": "bbbbbbbb",
                "sha256": "f" * 64,
            },
        ),
    )


def fake_model_loader(models_dir: Path) -> LoadedModels:
    """A create_app() model_loader that ignores the folder and returns fakes."""
    return fake_models()
