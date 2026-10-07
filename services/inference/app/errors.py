"""Error codes and the contract error shape: {"error": {"code", "message"}}.

See docs/api-contract.md for what each code means.
"""

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """Error codes returned in the `code` field of every error response."""

    # Slide and job failures
    SLIDE_UNREADABLE = "SLIDE_UNREADABLE"
    NO_TISSUE = "NO_TISSUE"
    NO_RESOLUTION = "NO_RESOLUTION"
    INTERRUPTED = "INTERRUPTED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    # HTTP-level failures
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SLIDE_NOT_READY = "SLIDE_NOT_READY"
    JOB_ALREADY_ACTIVE = "JOB_ALREADY_ACTIVE"
    JOB_NOT_COMPLETED = "JOB_NOT_COMPLETED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_STATUS_CODES = {
    401: ErrorCode.UNAUTHORIZED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}

INTERNAL_ERROR_MESSAGE = "Internal server error"


class ApiError(Exception):
    """A request failure with its own status code and error code."""

    # HTTPException carries only a status, which _STATUS_CODES maps to one
    # code. Raise this when the code isn't implied by the status, e.g. a 409
    # that must say SLIDE_NOT_READY rather than fall back to BAD_REQUEST.

    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        """Store the status, code, and client-safe message."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: ErrorCode, message: str) -> dict:
    """Build the contract error body for a code and message."""
    return {"error": {"code": code.value, "message": message}}


def error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    """Build a JSON error response in the contract shape."""
    return JSONResponse(status_code=status_code, content=error_body(code, message))


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Convert Starlette HTTP exceptions (404, 405, ...) to the contract shape."""
    # Routing errors (unknown path, wrong method) arrive here.
    if exc.status_code >= 500:
        code, message = ErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE
    else:
        code = _STATUS_CODES.get(exc.status_code, ErrorCode.BAD_REQUEST)
        message = str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message),
        headers=exc.headers,
    )


async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Convert an ApiError to its status and contract-shaped body."""
    return error_response(exc.status_code, exc.code, exc.message)


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert request validation failures to a 422 VALIDATION_ERROR."""
    # Report where and why, but never echo the submitted input back.
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    message = (
        f"{loc}: {first.get('msg', 'invalid request')}" if loc else "invalid request"
    )
    return error_response(422, ErrorCode.VALIDATION_ERROR, message)


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Convert any uncaught exception to a 500 INTERNAL_ERROR."""
    # Exception text can contain file paths (REQ-006), so the client gets a
    # fixed message and our log line gets only the exception type.
    logger.error(
        "Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path
    )
    return error_response(500, ErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE)


def register_exception_handlers(app: FastAPI) -> None:
    """Install the contract-shaped exception handlers on the app."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
