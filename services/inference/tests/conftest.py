import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TEST_TOKEN = "test-token-0123456789abcdefghijklmnop"


@pytest.fixture
def settings() -> Settings:
    """Settings with a valid test token."""
    return Settings(device_token=TEST_TOKEN)


@pytest.fixture
def app(settings):
    """A fresh app built from the test settings."""
    return create_app(settings)


@pytest.fixture
def client(app):
    """A TestClient that runs the app's lifespan."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict:
    """Headers carrying the valid test token."""
    return {"X-Device-Token": TEST_TOKEN}
