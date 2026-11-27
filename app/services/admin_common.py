"""Shared helpers for administrative services."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.db.models import AuditLog

logger = get_logger(__name__)

_CONTEXT_ALLOWED_KEYS = frozenset(
    {
        "action",
        "outcome",
        "station",
        "from_status",
        "to_status",
        "role",
        "previous_role",
        "fields",
        "sequence",
        "resend_sequence",
        "format",
        "purpose",
        "previous_status",
        "status",
        "ticket_revoked",
    }
)
_CONTEXT_FORBIDDEN_KEYS = frozenset(
    {"token", "token_hash", "raw_token", "email", "phone", "name", "urn", "password"}
)


@contextmanager
def mutation_transaction(session: Session) -> Iterator[None]:
    """Commit a mutation inside the request session's existing transaction.

    RBAC dependencies have usually already opened a read transaction. A
    savepoint isolates the mutation, and the outer commit releases every lock
    before the HTTP response is produced.
    """

    savepoint = session.begin_nested()
    try:
        yield
        savepoint.commit()
        session.commit()
    except Exception:
        if savepoint.is_active:
            savepoint.rollback()
        if session.in_transaction():
            session.rollback()
        raise


def add_audit(
    session: Session,
    *,
    event_id: Any,
    actor_user_id: Any,
    action: str,
    target_type: str,
    target_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    """Add a redacted audit record to the current transaction."""

    safe_context: dict[str, Any] = {}
    for key, value in (context or {}).items():
        if key.lower() in _CONTEXT_FORBIDDEN_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe_context[key] = value
        elif isinstance(value, (list, tuple, set)):
            safe_context[key] = sorted(str(item) for item in value)
    entry = AuditLog(
        event_id=event_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        context=safe_context,
    )
    session.add(entry)
    return entry


def redact_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return only operationally safe audit metadata."""

    if not context:
        return {}
    return {
        key: value
        for key, value in context.items()
        if key in _CONTEXT_ALLOWED_KEYS and isinstance(value, (str, int, float, bool))
    }


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC for consistent API output."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def require_aware(value: datetime | None, *, field: str) -> None:
    """Raise a validation error when a supplied datetime has no timezone."""

    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise AppError(
            status_code=422,
            code="VALIDATION_ERROR",
            message=f"{field} must include a timezone offset.",
        )


def normalize_reference(value: str, *, field: str) -> str:
    """Normalize a public reference without mutating its meaning."""

    normalized = value.strip()
    if not normalized:
        raise AppError(status_code=422, code="VALIDATION_ERROR", message=f"{field} is required.")
    return normalized


def like_term(value: str) -> str:
    """Escape LIKE wildcard characters in a caller-supplied search term."""

    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def paginate(
    session: Session,
    statement: Select[Any],
    *,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    """Return one stable page of rows and the total matching count."""

    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="page must be >= 1 and page_size must be between 1 and 100.",
        )
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = int(session.scalar(count_statement) or 0)
    rows = list(session.execute(statement.limit(page_size).offset((page - 1) * page_size)).all())
    return rows, total


def with_row_lock(statement: Select[Any], session: Session, entity: Any) -> Select[Any]:
    """Add a PostgreSQL row lock; SQLite tests run without row locks."""

    if session.get_bind().dialect.name == "postgresql":
        return statement.with_for_update(of=entity)
    return statement


def not_found(message: str = "The requested resource was not found.") -> AppError:
    """Build a non-disclosing 404 error."""

    return AppError(status_code=404, code="NOT_FOUND", message=message)


def conflict(message: str, *, code: str = "CONFLICT") -> AppError:
    """Build a controlled state-conflict error."""

    return AppError(status_code=409, code=code, message=message)


def log_admin_action(action: str, *, event_id: Any, actor_user_id: Any) -> None:
    """Log non-sensitive administrative-action metadata."""

    log_event(
        logger,
        logging.INFO,
        "admin_action",
        action=action,
        event_id=str(event_id),
        actor_user_id=str(actor_user_id),
    )
