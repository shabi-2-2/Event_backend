"""Domain errors and global HTTP exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, log_event
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = get_logger(__name__)

_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("BAD_REQUEST", "The request could not be understood."),
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have access to this resource."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "This method is not allowed for the resource."),
    409: ("CONFLICT", "The request conflicts with the current state."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
    429: ("TOO_MANY_REQUESTS", "Too many requests. Please retry later."),
}


class AppError(Exception):
    """Application-level error with a stable machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def _correlation_id(request: Request) -> str | None:
    value = getattr(request.state, "correlation_id", None)
    return str(value) if value else None


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    correlation_id: str | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details)).model_dump(
        mode="json", exclude_none=True
    )
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle expected application errors."""
    correlation_id = _correlation_id(request)
    log_event(
        logger,
        logging.WARNING,
        "application_error",
        code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
        correlation_id=correlation_id,
    )
    return _error_response(
        exc.status_code,
        exc.code,
        exc.message,
        exc.details,
        correlation_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalise framework HTTP errors without echoing caller input."""
    correlation_id = _correlation_id(request)
    code, message = _HTTP_ERRORS.get(
        exc.status_code, ("HTTP_ERROR", "The request could not be completed.")
    )
    log_event(
        logger,
        logging.INFO,
        "http_error",
        code=code,
        status_code=exc.status_code,
        path=request.url.path,
        correlation_id=correlation_id,
    )
    return _error_response(exc.status_code, code, message, None, correlation_id)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return validation details without reflecting submitted values."""
    correlation_id = _correlation_id(request)
    details = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "Invalid value.")),
            "type": str(error.get("type", "value_error")),
        }
        for error in exc.errors()
    ]
    log_event(
        logger,
        logging.INFO,
        "validation_error",
        error_count=len(details),
        path=request.url.path,
        correlation_id=correlation_id,
    )
    return _error_response(
        422, "VALIDATION_ERROR", "Request validation failed.", details, correlation_id
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 response and log only non-sensitive metadata."""
    correlation_id = _correlation_id(request)
    log_event(
        logger,
        logging.ERROR,
        "unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        correlation_id=correlation_id,
    )
    return _error_response(
        500,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
        None,
        correlation_id,
    )
