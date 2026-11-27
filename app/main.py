"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as root_health_router
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger, log_event
from app.db.session import create_db_engine, create_session_factory

logger = get_logger(__name__)
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _resolve_correlation_id(request: Request) -> str:
    """Accept a safe inbound correlation ID or generate one."""
    supplied = request.headers.get("X-Correlation-ID")
    if supplied and _CORRELATION_ID_PATTERN.fullmatch(supplied):
        return supplied
    return uuid4().hex


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=bool(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = _resolve_correlation_id(request)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def _register_exception_handlers(app: FastAPI) -> None:
    # Starlette's handler type is broad; each handler narrows its exception type
    # safely via registration key.
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup and release them on shutdown."""
    settings: Settings = app.state.settings

    engine = create_db_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.started_at = datetime.now(UTC)

    log_event(
        logger,
        logging.INFO,
        "application_startup",
        service=settings.service_name,
        environment=settings.app_env,
        version=settings.app_version,
        api_prefix=settings.api_prefix,
    )

    try:
        yield
    finally:
        app.state.shutdown_at = datetime.now(UTC)
        engine.dispose()
        log_event(
            logger,
            logging.INFO,
            "application_shutdown",
            service=settings.service_name,
            environment=settings.app_env,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.service_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.started_at = None
    app.state.shutdown_at = None

    _register_middleware(app, settings)
    _register_exception_handlers(app)

    app.include_router(root_health_router)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
