import sys
import types

from app import __version__


def test_req_018_health_reports_gpu_models_and_queue(client):
    """REQ-018: health reports status, versions, GPU, models, and queue."""
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service_version"] == __version__
    assert body["api_version"] == "v1"
    assert set(body["gpu"]) == {"available", "name"}
    assert isinstance(body["models"], list)
    assert body["queue"] == {"running": 0, "queued": 0}


def test_req_018_health_reports_no_gpu_without_torch(client, monkeypatch):
    """REQ-018: without torch installed, health reports no GPU."""
    # A None entry in sys.modules makes `import torch` raise ImportError.
    monkeypatch.setitem(sys.modules, "torch", None)

    body = client.get("/v1/health").json()

    assert body["gpu"] == {"available": False, "name": None}


def test_req_018_health_reports_gpu_name_when_cuda_available(client, monkeypatch):
    """REQ-018: with CUDA available, health reports the GPU name."""
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            get_device_name=lambda index: "NVIDIA GeForce RTX 3090",
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    body = client.get("/v1/health").json()

    assert body["gpu"] == {"available": True, "name": "NVIDIA GeForce RTX 3090"}


def test_req_018_health_reports_no_gpu_when_cuda_unavailable(client, monkeypatch):
    """REQ-018: with torch but no CUDA, health reports no GPU."""
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False)
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    body = client.get("/v1/health").json()

    assert body["gpu"] == {"available": False, "name": None}


def test_req_018_health_does_not_require_token(client):
    """REQ-018: health is reachable without the device token."""
    assert client.get("/v1/health").status_code == 200
