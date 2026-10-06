"""FastAPI application factory.

Run with:
    uv run --env-file .env uvicorn app.main:create_app --factory --port 8000

`--factory` tells uvicorn to call create_app() instead of importing a
module-level `app`, so importing this module never reads the environment.
Tests call create_app(Settings(...)) directly.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.auth import DeviceTokenMiddleware
from app.config import Settings
from app.db import DB_FILENAME, init_db
from app.errors import register_exception_handlers
from app.health import router as health_router
from app.registry import Registry
from app.slides import router as slides_router

logger = logging.getLogger(__name__)

_LOG_HANDLER_NAME = "mil-inference"


class ExceptionTextFilter(logging.Filter):
    """Replace a record's traceback and exception text with the exception type."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite records that carry exception info; never drop a record."""
        if record.exc_info and record.exc_info[1] is not None:
            exc_type = type(record.exc_info[1]).__name__
            record.msg = f"{record.getMessage().rstrip()} ({exc_type})"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging(level: str) -> None:
    """Send log records to stderr with ISO 8601 UTC timestamps, once per process."""
    root = logging.getLogger()
    root.setLevel(level)
    if any(h.name == _LOG_HANDLER_NAME for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.name = _LOG_HANDLER_NAME
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime  # UTC timestamps
    handler.setFormatter(formatter)
    root.addHandler(handler)
    # After an unhandled exception, Starlette re-raises it to uvicorn, which
    # logs the full traceback on "uvicorn.error". Exception text can contain
    # file paths (REQ-006), so that logger keeps only the exception type.
    logging.getLogger("uvicorn.error").addFilter(ExceptionTextFilter())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup work before serving requests and shutdown work after."""
    # Later items start the job worker (5) and load and verify models (6)
    # here.
    logger.info("Inference service %s starting", __version__)
    settings: Settings = app.state.settings
    init_db(app.state.db_path)
    registry = Registry(settings.acquisition_dir, app.state.db_path)
    registry.start()
    yield
    registry.stop()
    logger.info("Inference service stopping")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app with token middleware, error handlers, and routes."""
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="MIL inference service",
        version=__version__,
        # Swagger UI and ReDoc are off: browsers can't send the token header
        # and both pages load scripts from a CDN. /openapi.json stays,
        # behind the token.
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db_path = settings.data_dir / DB_FILENAME
    app.add_middleware(DeviceTokenMiddleware, token=settings.device_token)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(slides_router)
    return app
