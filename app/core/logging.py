"""Structured logging with conservative PII redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

_HANDLER_MARKER = "_event_api_structured_handler"

_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "raw_token",
        "ticket_token",
        "access_token",
        "refresh_token",
        "email",
        "phone",
        "urn",
        "submission_id",
        "payload",
        "body",
        "database_url",
        "dsn",
        "connection_string",
    }
)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def __init__(self, *, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_RECORD_KEYS:
                continue
            if key.lower() in _SENSITIVE_KEYS:
                continue
            if key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            # Only include formatted tracebacks when explicitly requested by callers.
            # Exception messages can contain PII, so callers must not pass exc_info
            # for errors raised from user-supplied data.
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(settings: Settings) -> logging.Handler:
    """Configure root logging once per application instance."""
    root = logging.getLogger()

    for existing_handler in list(root.handlers):
        if getattr(existing_handler, _HANDLER_MARKER, False):
            root.removeHandler(existing_handler)
            existing_handler.close()

    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                service_name=settings.service_name,
                environment=settings.app_env,
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level))

    # Access logs record full request paths; disable them in favour of explicit,
    # redacted application events.
    logging.getLogger("uvicorn.access").disabled = True

    return handler


def get_logger(name: str) -> logging.Logger:
    """Return a module logger."""
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Log a structured event using LogRecord extra fields."""
    logger.log(level, message, extra=fields)
