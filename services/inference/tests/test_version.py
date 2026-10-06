import tomllib
from pathlib import Path

from app import __version__

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject():
    """app.__version__ matches the version in pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        assert __version__ == tomllib.load(f)["project"]["version"]
