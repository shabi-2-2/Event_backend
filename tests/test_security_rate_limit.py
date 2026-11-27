"""Shared PostgreSQL rate-limiting tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.security.rate_limit import (
    PostgresRateLimiter,
    RateLimitScope,
    build_subject,
    enforce_rate_limit,
    rate_limit_counters,
)

pytestmark = pytest.mark.postgres

_NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
def limiter_harness(
    postgres_session_factory: sessionmaker[Session],
) -> Iterator[tuple[PostgresRateLimiter, sessionmaker[Session]]]:
    def reset() -> None:
        with postgres_session_factory() as session:
            session.execute(delete(rate_limit_counters))
            session.commit()

    reset()
    yield PostgresRateLimiter(postgres_session_factory), postgres_session_factory
    reset()


def test_requests_within_and_over_limit(
    limiter_harness: tuple[PostgresRateLimiter, sessionmaker[Session]],
) -> None:
    limiter, _ = limiter_harness
    subject = build_subject("webhook", "v1")

    first = limiter.check("webhook", subject, limit=2, window_seconds=60, now=_NOW)
    second = limiter.check("webhook", subject, limit=2, window_seconds=60, now=_NOW)
    third = limiter.check("webhook", subject, limit=2, window_seconds=60, now=_NOW)

    assert first.allowed and second.allowed
    assert not third.allowed
    assert first.remaining == 1
    assert second.remaining == 0
    assert third.remaining == 0
    assert third.reset_at == datetime(2026, 11, 27, 12, 1, tzinfo=UTC)


def test_scopes_and_subjects_are_isolated(
    limiter_harness: tuple[PostgresRateLimiter, sessionmaker[Session]],
) -> None:
    limiter, _ = limiter_harness
    subject = build_subject("user", "event")

    webhook = limiter.check(
        RateLimitScope.WEBHOOK.value, subject, limit=1, window_seconds=60, now=_NOW
    )
    checkin = limiter.check(
        RateLimitScope.CHECKIN_VERIFY.value,
        subject,
        limit=1,
        window_seconds=60,
        now=_NOW,
    )
    other_subject = limiter.check(
        RateLimitScope.WEBHOOK.value,
        build_subject("user", "other-event"),
        limit=1,
        window_seconds=60,
        now=_NOW,
    )

    assert webhook.allowed
    assert checkin.allowed
    assert other_subject.allowed

    repeated_webhook = limiter.check(
        RateLimitScope.WEBHOOK.value, subject, limit=1, window_seconds=60, now=_NOW
    )
    assert not repeated_webhook.allowed


def test_distributed_instances_share_counters(
    limiter_harness: tuple[PostgresRateLimiter, sessionmaker[Session]],
) -> None:
    _, factory = limiter_harness
    instance_a = PostgresRateLimiter(factory)
    instance_b = PostgresRateLimiter(factory)
    subject = build_subject("checkin", "event-1", "user-1")

    assert instance_a.check(
        RateLimitScope.CHECKIN_CONFIRM.value, subject, limit=2, window_seconds=60, now=_NOW
    ).allowed
    assert instance_b.check(
        RateLimitScope.CHECKIN_CONFIRM.value, subject, limit=2, window_seconds=60, now=_NOW
    ).allowed
    assert not instance_b.check(
        RateLimitScope.CHECKIN_CONFIRM.value, subject, limit=2, window_seconds=60, now=_NOW
    ).allowed


def test_new_window_resets_counter(
    limiter_harness: tuple[PostgresRateLimiter, sessionmaker[Session]],
) -> None:
    limiter, _ = limiter_harness
    subject = build_subject("export", "event-1")

    first = limiter.check(
        RateLimitScope.ADMIN_EXPORT.value, subject, limit=1, window_seconds=60, now=_NOW
    )
    next_window = limiter.check(
        RateLimitScope.ADMIN_EXPORT.value,
        subject,
        limit=1,
        window_seconds=60,
        now=datetime(2026, 11, 27, 12, 1, tzinfo=UTC),
    )

    assert first.allowed
    assert next_window.allowed


def test_subject_builder_rejects_unsafe_values() -> None:
    assert build_subject("event", "user") == "event:user"

    with pytest.raises(ValueError):
        build_subject("")

    with pytest.raises(ValueError):
        build_subject("line\nbreak")


def test_enforce_rate_limit_returns_standard_429(
    limiter_harness: tuple[PostgresRateLimiter, sessionmaker[Session]],
    postgres_engine_settings: Settings,
) -> None:
    settings = postgres_engine_settings.model_copy(
        update={"webhook_rate_limit": 1, "rate_limit_window_seconds": 60}
    )
    app = create_app(settings)

    @app.get("/_test/rate-limited")
    async def endpoint(request: Request) -> dict[str, bool]:
        result = enforce_rate_limit(request, RateLimitScope.WEBHOOK, build_subject("webhook", "v1"))
        return {"allowed": result.allowed}

    with TestClient(app) as client:
        first = client.get("/_test/rate-limited")
        second = client.get("/_test/rate-limited")

    assert first.status_code == 200
    assert first.json() == {"allowed": True}
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "TOO_MANY_REQUESTS"
