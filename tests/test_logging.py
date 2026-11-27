"""Structured logging and redaction tests."""

from __future__ import annotations

import json
import logging

from app.core.config import Settings
from app.core.logging import JsonFormatter, configure_logging


def test_json_formatter_redacts_sensitive_fields() -> None:
    formatter = JsonFormatter(service_name="event-management-api", environment="test")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="test_event",
        args=(),
        exc_info=None,
    )
    record.email = "pii@example.com"
    record.ticket_token = "super-secret-token"
    record.safe_id = "registration-123"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "test_event"
    assert payload["service"] == "event-management-api"
    assert payload["environment"] == "test"
    assert payload["safe_id"] == "registration-123"
    assert "email" not in payload
    assert "ticket_token" not in payload
    assert "args" not in payload


def test_configure_logging_is_idempotent(settings: Settings) -> None:
    first = configure_logging(settings)
    second = configure_logging(settings)
    root = logging.getLogger()

    assert first is not second
    assert (
        sum(
            1
            for handler in root.handlers
            if getattr(handler, "_event_api_structured_handler", False)
        )
        == 1
    )
