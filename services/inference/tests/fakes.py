"""Test doubles for OpenSlide, shared by the registry and slide API tests."""

from pathlib import Path
from typing import ClassVar, Self

import openslide

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
