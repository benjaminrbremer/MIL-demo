import pytest

# Stands in for any protected endpoint.
PROTECTED_PATH = "/v1/slides"


def assert_error(response, status_code, code):
    """Assert a response has the given status and contract error code."""
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert isinstance(response.json()["error"]["message"], str)


def test_req_019_missing_token_rejected(client):
    """REQ-019: a request with no token gets 401."""
    assert_error(client.get(PROTECTED_PATH), 401, "UNAUTHORIZED")


@pytest.mark.parametrize(
    "token",
    [
        "wrong",
        "test-token-0123456789abcdefghijklmnoX",  # differs in the last byte
        "",
    ],
)
def test_req_019_wrong_token_rejected(client, token):
    """REQ-019: a request with a wrong or empty token gets 401."""
    response = client.get(PROTECTED_PATH, headers={"X-Device-Token": token})

    assert_error(response, 401, "UNAUTHORIZED")


def test_req_019_valid_token_passes(client, auth_headers):
    """REQ-019: a request with the right token reaches the route."""
    response = client.get(PROTECTED_PATH, headers=auth_headers)

    assert response.status_code == 200


def test_req_019_rejection_does_not_echo_or_log_token(client, caplog):
    """REQ-019: a rejected token appears in neither the response nor the logs."""
    secret = "attacker-supplied-token-value-xyz"

    response = client.get(PROTECTED_PATH, headers={"X-Device-Token": secret})

    assert secret not in response.text
    assert secret not in caplog.text


def test_req_019_unknown_path_without_token_is_401_not_404(client):
    """REQ-019: unauthenticated callers can't probe which paths exist."""
    assert_error(client.get("/no/such/path"), 401, "UNAUTHORIZED")


def test_req_019_openapi_requires_token(client, auth_headers):
    """REQ-019: the OpenAPI schema is served only with the token."""
    assert_error(client.get("/openapi.json"), 401, "UNAUTHORIZED")
    assert client.get("/openapi.json", headers=auth_headers).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_interactive_docs_not_served(client, auth_headers, path):
    """Swagger UI and ReDoc are disabled."""
    assert_error(client.get(path, headers=auth_headers), 404, "NOT_FOUND")
