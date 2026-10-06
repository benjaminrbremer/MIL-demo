import logging

import pytest

from app import db
from app.registry import Registry
from tests.fakes import PHI_NAME, phi_opener

ALLOWLISTED_FIELDS = {
    "id",
    "status",
    "width",
    "height",
    "level_count",
    "mpp_x",
    "mpp_y",
    "detected_at",
    "registered_at",
    "error",
}
METADATA = {
    "width": 2000,
    "height": 1000,
    "level_count": 3,
    "mpp_x": 0.25,
    "mpp_y": None,
}


@pytest.fixture
def db_path(app, client):
    """The running app's database (created by the lifespan in `client`)."""
    return app.state.db_path


@pytest.fixture
def seeded(db_path) -> dict:
    """Insert one ready and one unreadable slide; return their IDs."""
    ready = db.ensure_arriving(db_path, "/acq/older.tif", "2026-10-07T14:00:00Z")
    db.mark_ready(db_path, ready, "a" * 64, METADATA, "2026-10-07T14:00:08Z")
    broken = db.ensure_arriving(db_path, "/acq/newer.tif", "2026-10-07T15:00:00Z")
    db.mark_unreadable(db_path, broken, "b" * 64, "SLIDE_UNREADABLE", "Cannot open")
    return {"ready": ready, "unreadable": broken}


def test_list_is_empty_on_a_fresh_device(client, auth_headers):
    """With no slides, the list is an empty JSON array."""
    response = client.get("/v1/slides", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_slides_newest_first(client, auth_headers, seeded):
    """The list holds every slide, most recently detected first."""
    body = client.get("/v1/slides", headers=auth_headers).json()

    assert [slide["id"] for slide in body] == [seeded["unreadable"], seeded["ready"]]


def test_get_ready_slide(client, auth_headers, seeded):
    """A ready slide is served with its metadata and no error."""
    response = client.get(f"/v1/slides/{seeded['ready']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": seeded["ready"],
        "status": "ready",
        "width": 2000,
        "height": 1000,
        "level_count": 3,
        "mpp_x": 0.25,
        "mpp_y": None,
        "detected_at": "2026-10-07T14:00:00Z",
        "registered_at": "2026-10-07T14:00:08Z",
        "error": None,
    }


def test_get_unreadable_slide_reports_error(client, auth_headers, seeded):
    """An unreadable slide carries its error code and message."""
    body = client.get(f"/v1/slides/{seeded['unreadable']}", headers=auth_headers).json()

    assert body["status"] == "unreadable"
    assert body["error"] == {"code": "SLIDE_UNREADABLE", "message": "Cannot open"}


def test_unknown_slide_is_404_not_found(client, auth_headers):
    """An unknown ID gets 404 NOT_FOUND in the contract error shape."""
    response = client.get("/v1/slides/no-such-slide", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", ["/v1/slides", "/v1/slides/anything"])
def test_req_019_slide_endpoints_require_token(client, path):
    """REQ-019: slide endpoints reject requests without the token."""
    assert client.get(path).status_code == 401


def test_req_005_slide_responses_have_only_allowlisted_fields(
    client, auth_headers, seeded
):
    """REQ-005: list and single responses contain exactly the allowlisted fields."""
    listed = client.get("/v1/slides", headers=auth_headers).json()
    single = client.get(f"/v1/slides/{seeded['ready']}", headers=auth_headers).json()

    for slide in [*listed, single]:
        assert set(slide) == ALLOWLISTED_FIELDS


def test_req_006_no_filename_or_path_in_api_or_logs(
    client, auth_headers, db_path, tmp_path, caplog
):
    """REQ-006: registered slides never expose their filename or path."""
    caplog.set_level(logging.DEBUG)
    # A separate folder, so the app's own poller thread doesn't race this one.
    acq = tmp_path / "other-acquisition"
    acq.mkdir()
    (acq / PHI_NAME).write_bytes(b"pixels")
    (acq / f"unreadable-{PHI_NAME}").write_text("not a slide")

    registry = Registry(acq, db_path, opener=phi_opener)
    registry.scan_once(now=0)
    registry.scan_once(now=5)

    listed = client.get("/v1/slides", headers=auth_headers)
    singles = [
        client.get(f"/v1/slides/{slide['id']}", headers=auth_headers)
        for slide in listed.json()
    ]
    assert {slide["status"] for slide in listed.json()} == {"ready", "unreadable"}
    for response in [listed, *singles]:
        assert "DOE-JOHN" not in response.text
        assert str(acq) not in response.text
    assert "DOE-JOHN" not in caplog.text
    assert str(acq) not in caplog.text
