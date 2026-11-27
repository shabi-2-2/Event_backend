"""Shared, database-backed rate limiting primitives.

Counters are stored in PostgreSQL so every backend instance observes the same
state. No Redis service is required.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from fastapi import Request
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Table,
    func,
    select,
    text,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.db.base import Base

logger = get_logger(__name__)

rate_limit_counters = Table(
    "rate_limit_counters",
    Base.metadata,
    Column("scope", String(64), primary_key=True),
    Column("subject", String(255), primary_key=True),
    Column("window_start", DateTime(timezone=True), primary_key=True),
    Column("count", Integer, nullable=False, server_default=text("0")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_rate_limit_counters_scope_subject_window", "scope", "subject", "window_start"),
)


class RateLimitScope(StrEnum):
    WEBHOOK = "webhook"
    CHECKIN_VERIFY = "checkin_verify"
    CHECKIN_CONFIRM = "checkin_confirm"
    ADMIN_EXPORT = "admin_export"


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime


class RateLimiter(Protocol):
    def check(
        self,
        scope: str,
        subject: str,
        *,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> RateLimitResult: ...


def build_subject(*parts: str | UUID) -> str:
    """Build a compact, opaque scope key from event/user identifiers.

    Callers must hash any directly identifying value (for example an IP address)
    before passing it here.
    """
    normalized = [str(part).strip() for part in parts if str(part).strip()]
    subject = ":".join(normalized)
    if not subject or len(subject) > 255 or any(char in subject for char in "\r\n\t"):
        raise ValueError("rate-limit subject must be 1-255 safe characters")
    return subject


def limit_for(settings: Settings, scope: RateLimitScope) -> int:
    """Resolve the configured limit for a scope."""
    limits = {
        RateLimitScope.WEBHOOK: settings.webhook_rate_limit,
        RateLimitScope.CHECKIN_VERIFY: settings.checkin_verify_rate_limit,
        RateLimitScope.CHECKIN_CONFIRM: settings.checkin_confirm_rate_limit,
        RateLimitScope.ADMIN_EXPORT: settings.admin_export_rate_limit,
    }
    return limits[scope]


def _window_start(now: datetime, window_seconds: int) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware UTC")
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


def _validate_component(value: str, *, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"rate-limit {field} must be 1-{max_length} characters")
    if any(char in normalized for char in "\r\n\t"):
        raise ValueError(f"rate-limit {field} must not contain control characters")
    return normalized


class PostgresRateLimiter:
    """Fixed-window limiter using an atomic upsert in the shared database."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def check(
        self,
        scope: str,
        subject: str,
        *,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> RateLimitResult:
        if limit < 1:
            raise ValueError("rate-limit limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("rate-limit window must be at least 1 second")

        normalized_scope = _validate_component(scope, field="scope", max_length=64)
        normalized_subject = _validate_component(subject, field="subject", max_length=255)
        current = now or datetime.now(UTC)
        window_start = _window_start(current, window_seconds)

        with self._session_factory() as session:
            bind = session.get_bind()
            insert_fn: Callable[[Any], Any]
            if bind.dialect.name == "postgresql":
                insert_fn = postgresql.insert
            elif bind.dialect.name == "sqlite":
                insert_fn = sqlite.insert
            else:
                raise ValueError("rate limiter requires PostgreSQL or SQLite")

            upsert = (
                insert_fn(rate_limit_counters)
                .values(
                    scope=normalized_scope,
                    subject=normalized_subject,
                    window_start=window_start,
                    count=1,
                )
                .on_conflict_do_update(
                    index_elements=[
                        rate_limit_counters.c.scope,
                        rate_limit_counters.c.subject,
                        rate_limit_counters.c.window_start,
                    ],
                    set_={
                        "count": rate_limit_counters.c.count + 1,
                        "updated_at": func.now(),
                    },
                )
            )
            with session.begin():
                session.execute(upsert)
                count = int(
                    session.execute(
                        select(rate_limit_counters.c.count).where(
                            rate_limit_counters.c.scope == normalized_scope,
                            rate_limit_counters.c.subject == normalized_subject,
                            rate_limit_counters.c.window_start == window_start,
                        )
                    ).scalar_one()
                )

        return RateLimitResult(
            allowed=count <= limit,
            limit=limit,
            remaining=max(limit - count, 0),
            reset_at=window_start + timedelta(seconds=window_seconds),
        )


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return a limiter cached on the application instance."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        factory: sessionmaker[Session] = request.app.state.session_factory
        limiter = PostgresRateLimiter(factory)
        request.app.state.rate_limiter = limiter
    return limiter


def enforce_rate_limit(request: Request, scope: RateLimitScope, subject: str) -> RateLimitResult:
    """Check a scoped limit and raise the standard 429 error when exceeded."""
    settings: Settings = request.app.state.settings
    result = get_rate_limiter(request).check(
        scope.value,
        subject,
        limit=limit_for(settings, scope),
        window_seconds=settings.rate_limit_window_seconds,
    )
    if not result.allowed:
        retry_after = max(1, int((result.reset_at - datetime.now(UTC)).total_seconds()))
        log_event(logger, logging.WARNING, "rate_limit_exceeded", scope=scope.value)
        raise AppError(
            status_code=429,
            code="TOO_MANY_REQUESTS",
            message="Too many requests. Please retry later.",
            details=[{"retry_after_seconds": retry_after}],
        )
    return result
