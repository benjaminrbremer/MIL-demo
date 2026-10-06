import pytest

from app.config import MIN_TOKEN_LENGTH, ConfigError, Settings

VALID_TOKEN = "x" * MIN_TOKEN_LENGTH


def test_missing_token_fails_fast(monkeypatch):
    """An unset DEVICE_TOKEN stops startup."""
    monkeypatch.delenv("DEVICE_TOKEN", raising=False)

    with pytest.raises(ConfigError, match="DEVICE_TOKEN is not set"):
        Settings.from_env()


def test_blank_token_fails_fast(monkeypatch):
    """A whitespace-only DEVICE_TOKEN counts as unset."""
    monkeypatch.setenv("DEVICE_TOKEN", "   ")

    with pytest.raises(ConfigError, match="DEVICE_TOKEN is not set"):
        Settings.from_env()


def test_short_token_fails_fast(monkeypatch):
    """A DEVICE_TOKEN below the minimum length stops startup."""
    monkeypatch.setenv("DEVICE_TOKEN", "x" * (MIN_TOKEN_LENGTH - 1))

    with pytest.raises(ConfigError, match="at least"):
        Settings.from_env()


def test_valid_env_loads_with_default_log_level(monkeypatch):
    """A valid token loads, and LOG_LEVEL defaults to INFO."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = Settings.from_env()

    assert settings.device_token == VALID_TOKEN
    assert settings.log_level == "INFO"


def test_log_level_is_case_insensitive(monkeypatch):
    """LOG_LEVEL accepts lowercase names."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert Settings.from_env().log_level == "DEBUG"


def test_invalid_log_level_fails_fast(monkeypatch):
    """An unknown LOG_LEVEL stops startup."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.from_env()
