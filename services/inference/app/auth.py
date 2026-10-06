"""Shared-token check for every request except the health endpoint (REQ-019).

Written as plain ASGI middleware rather than Starlette's BaseHTTPMiddleware:
BaseHTTPMiddleware wraps the response body in its own stream, which has a
history of problems with long-lived streaming responses such as the SSE
progress endpoint (roadmap item 5). Plain ASGI just decides whether to call
the app at all and never touches the response.
"""

import hmac
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from app.errors import ErrorCode, error_response

logger = logging.getLogger(__name__)

TOKEN_HEADER = "x-device-token"
PUBLIC_PATHS = frozenset({"/v1/health"})


class DeviceTokenMiddleware:
    """Reject requests without a valid X-Device-Token, except public paths."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Wrap the next ASGI app and store the expected token as bytes."""
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Forward public or correctly tokened requests; answer the rest with 401."""
        # "lifespan" events (startup/shutdown) also pass through middleware.
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # ASGI headers are a list of (lowercase name, value) byte pairs.
        presented = dict(scope["headers"]).get(TOKEN_HEADER.encode(), b"")
        # compare_digest takes the same time whether the first or last byte
        # differs, so response timing reveals nothing about the token.
        if hmac.compare_digest(presented, self._token):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        logger.warning(
            "Rejected %s %s from %s: %s token",
            scope["method"],
            scope["path"],
            client[0] if client else "unknown",
            "invalid" if presented else "missing",
        )
        response = error_response(
            401, ErrorCode.UNAUTHORIZED, "Missing or invalid X-Device-Token header"
        )
        await response(scope, receive, send)
