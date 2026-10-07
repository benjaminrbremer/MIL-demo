"""Settings loaded from environment variables.

The `.env` file is loaded by `uv run --env-file .env`, so this module only
reads `os.environ` and needs no dotenv library (D-022).
"""

import os
from dataclasses import dataclass
from pathlib import Path

MIN_TOKEN_LENGTH = 32
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
# services/inference/models: manifest.json (committed) and weights/ (fetched).
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
DEFAULT_FEATURE_WORKERS = 8  # D-045: about 93% of peak throughput in the spike


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Validated service configuration."""

    device_token: str
    acquisition_dir: Path
    data_dir: Path
    log_level: str = "INFO"
    models_dir: Path = DEFAULT_MODELS_DIR
    feature_workers: int = DEFAULT_FEATURE_WORKERS

    def __post_init__(self) -> None:
        """Validate fields; raise ConfigError so the service refuses to start."""
        if len(self.device_token) < MIN_TOKEN_LENGTH:
            raise ConfigError(
                f"DEVICE_TOKEN must be at least {MIN_TOKEN_LENGTH} characters"
            )
        if self.log_level not in LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
        if not self.acquisition_dir.is_dir():
            raise ConfigError("ACQUISITION_DIR must be an existing directory")
        # DATA_DIR is created at startup if missing, but must not be a file.
        if self.data_dir.exists() and not self.data_dir.is_dir():
            raise ConfigError("DATA_DIR exists but is not a directory")
        if self.feature_workers < 0:
            raise ConfigError("FEATURE_WORKERS must be 0 or more")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from environment variables."""
        token = os.environ.get("DEVICE_TOKEN", "").strip()
        if not token:
            raise ConfigError("DEVICE_TOKEN is not set (see .env.example)")
        return cls(
            device_token=token,
            acquisition_dir=_required_path("ACQUISITION_DIR"),
            data_dir=_required_path("DATA_DIR"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            models_dir=_optional_path("MODELS_DIR", DEFAULT_MODELS_DIR),
            feature_workers=_optional_int("FEATURE_WORKERS", DEFAULT_FEATURE_WORKERS),
        )


def _required_path(name: str) -> Path:
    """Read a required path variable; `~` is expanded."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set (see .env.example)")
    return Path(value).expanduser()


def _optional_path(name: str, default: Path) -> Path:
    """Read an optional path variable; `~` is expanded."""
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def _optional_int(name: str, default: int) -> int:
    """Read an optional integer variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
