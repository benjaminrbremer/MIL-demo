"""Settings loaded from environment variables.

The `.env` file is loaded by `uv run --env-file .env`, so this module only
reads `os.environ` and needs no dotenv library (D-022).
"""

import os
from dataclasses import dataclass

MIN_TOKEN_LENGTH = 32
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Validated service configuration."""

    device_token: str
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate fields; raise ConfigError so the service refuses to start."""
        if len(self.device_token) < MIN_TOKEN_LENGTH:
            raise ConfigError(
                f"DEVICE_TOKEN must be at least {MIN_TOKEN_LENGTH} characters"
            )
        if self.log_level not in LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from environment variables."""
        token = os.environ.get("DEVICE_TOKEN", "").strip()
        if not token:
            raise ConfigError("DEVICE_TOKEN is not set (see .env.example)")
        return cls(
            device_token=token,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
        )
