import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import fake_model_loader

TEST_TOKEN = "test-token-0123456789abcdefghijklmnop"


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Settings with a valid test token and empty temporary directories."""
    acquisition_dir = tmp_path / "acquisition"
    acquisition_dir.mkdir()
    return Settings(
        device_token=TEST_TOKEN,
        acquisition_dir=acquisition_dir,
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def app(settings):
    """A fresh app built from the test settings, with fake models."""
    return create_app(settings, model_loader=fake_model_loader)


@pytest.fixture
def client(app):
    """A TestClient that runs the app's lifespan."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict:
    """Headers carrying the valid test token."""
    return {"X-Device-Token": TEST_TOKEN}
