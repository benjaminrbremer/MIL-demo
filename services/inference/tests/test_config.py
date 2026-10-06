import pytest

from app.config import MIN_TOKEN_LENGTH, ConfigError, Settings

VALID_TOKEN = "x" * MIN_TOKEN_LENGTH


@pytest.fixture(autouse=True)
def valid_dirs(monkeypatch, tmp_path):
    """Point ACQUISITION_DIR and DATA_DIR at valid temporary paths."""
    monkeypatch.setenv("ACQUISITION_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


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


@pytest.mark.parametrize("name", ["ACQUISITION_DIR", "DATA_DIR"])
def test_missing_dir_variable_fails_fast(monkeypatch, name):
    """An unset ACQUISITION_DIR or DATA_DIR stops startup."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.delenv(name)

    with pytest.raises(ConfigError, match=f"{name} is not set"):
        Settings.from_env()


def test_nonexistent_acquisition_dir_fails_fast(monkeypatch, tmp_path):
    """An ACQUISITION_DIR that does not exist stops startup."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("ACQUISITION_DIR", str(tmp_path / "missing"))

    with pytest.raises(ConfigError, match="ACQUISITION_DIR"):
        Settings.from_env()


def test_data_dir_that_is_a_file_fails_fast(monkeypatch, tmp_path):
    """A DATA_DIR that points at a file stops startup."""
    a_file = tmp_path / "not-a-dir"
    a_file.write_text("")
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("DATA_DIR", str(a_file))

    with pytest.raises(ConfigError, match="DATA_DIR"):
        Settings.from_env()


def test_dirs_load_as_paths(monkeypatch, tmp_path):
    """Valid directories load as Path objects; DATA_DIR need not exist yet."""
    monkeypatch.setenv("DEVICE_TOKEN", VALID_TOKEN)

    settings = Settings.from_env()

    assert settings.acquisition_dir == tmp_path
    assert settings.data_dir == tmp_path / "data"
