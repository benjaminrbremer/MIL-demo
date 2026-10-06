import logging

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import ErrorCode

FAKE_PATH = "/data/acquisition/PATIENT_SMITH_JOHN.svs"


class Body(BaseModel):
    """Request body for the test-only validation route."""

    slide_id: str


def test_req_006_internal_error_hides_exception_text(app, auth_headers, caplog):
    """REQ-006: a 500 exposes no exception text in the response or logs."""

    @app.get("/v1/test-boom")
    def boom():
        """Test-only route that fails with a path in the exception message."""
        raise FileNotFoundError(f"No such file: {FAKE_PATH}")

    # The server re-raises after sending the 500; tell the client not to.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/test-boom", headers=auth_headers)

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    }
    assert FAKE_PATH not in caplog.text


def test_validation_error_uses_contract_shape(app, auth_headers):
    """A bad request body gives 422 VALIDATION_ERROR without echoing input."""

    @app.post("/v1/test-validate")
    def validate(body: Body):
        """Test-only route that requires a Body."""
        return {}

    with TestClient(app) as client:
        response = client.post(
            "/v1/test-validate", json={"wrong": FAKE_PATH}, headers=auth_headers
        )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "slide_id" in error["message"]
    assert FAKE_PATH not in response.text


def test_method_not_allowed_uses_contract_shape(client, auth_headers):
    """A wrong HTTP method gives 405 METHOD_NOT_ALLOWED."""
    response = client.post("/v1/health", headers=auth_headers)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_error_codes_match_contract():
    """The pipeline error codes match docs/api-contract.md exactly."""
    # Pipeline codes from docs/api-contract.md must exist verbatim.
    for code in ("SLIDE_UNREADABLE", "NO_TISSUE", "INTERRUPTED", "INFERENCE_FAILED"):
        assert ErrorCode(code).value == code


def test_req_006_uvicorn_error_log_has_no_exception_text(client, caplog):
    """REQ-006: uvicorn's unhandled-exception log keeps the type, not the text."""
    secret_path = FAKE_PATH
    try:
        raise ValueError(f"cannot open {secret_path}")
    except ValueError as exc:
        # This is the call uvicorn makes after Starlette re-raises an error.
        logging.getLogger("uvicorn.error").error(
            "Exception in ASGI application\n", exc_info=exc
        )

    assert secret_path not in caplog.text
    assert "Traceback" not in caplog.text
    assert "Exception in ASGI application (ValueError)" in caplog.text
