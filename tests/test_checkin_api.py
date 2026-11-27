"""PostgreSQL-backed QR verification and atomic check-in tests."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Attendee, AuditLog, Checkin, Event, Registration, StaffMembership, Ticket
from app.db.models.common import (
    CheckinSource,
    EventStatus,
    RegistrationStatus,
    StaffRole,
    TicketStatus,
)
from app.db.session import get_session
from app.main import create_app
from app.security.jwt import AuthenticatedUser, get_current_user
from app.security.ticket_tokens import (
    generate_ticket_reference,
    generate_ticket_token,
    hash_ticket_token,
)

pytestmark = pytest.mark.postgres

_VERIFY = "/api/v1/events/{event_slug}/checkins/verify"
_CONFIRM = "/api/v1/events/{event_slug}/checkins/confirm"
_SQLITE_URL = "sqlite+pysqlite:///:memory:"
_JWT_SECRET = "checkin-jwt-test-secret-at-least-32-characters"
_JWT_ISSUER = "https://project.example.supabase.co/auth/v1"

_CLEANUP_TABLES = (
    "checkins",
    "tickets",
    "email_deliveries",
    "registrations",
    "webhook_events",
    "audit_logs",
    "staff_memberships",
    "attendees",
    "events",
    "rate_limit_counters",
)


@dataclass(frozen=True)
class TicketFixture:
    token: str
    token_hash: str
    ticket_id: UUID
    registration_id: UUID
    attendee_id: UUID
    event_id: UUID
    event_slug: str
    attendee_name: str
    urn: str
    email: str
    phone: str


@dataclass(frozen=True)
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    app: FastAPI
    engine: Engine
    user_id: UUID


def _truncate(engine: Engine) -> None:
    tables = ", ".join(_CLEANUP_TABLES)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@contextmanager
def _harness(
    migrated_postgres: Engine,
    base_settings: Settings,
    *,
    raise_server_exceptions: bool = True,
    **overrides: object,
) -> Iterator[Harness]:
    _truncate(migrated_postgres)
    values: dict[str, object] = {
        "checkin_verify_rate_limit": 1000,
        "checkin_confirm_rate_limit": 1000,
    }
    values.update(overrides)
    settings = base_settings.model_copy(update=values)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    app = create_app(settings)
    user_id = uuid4()

    def fake_current_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=user_id)

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app, raise_server_exceptions=raise_server_exceptions) as client:
            yield Harness(
                client=client,
                factory=factory,
                app=app,
                engine=migrated_postgres,
                user_id=user_id,
            )
    finally:
        app.dependency_overrides.clear()
        _truncate(migrated_postgres)


@pytest.fixture
def harness(migrated_postgres: Engine, postgres_engine_settings: Settings) -> Iterator[Harness]:
    with _harness(migrated_postgres, postgres_engine_settings) as built:
        yield built


def _settings(**overrides: object) -> Settings:
    base = Settings(
        _env_file=None,
        app_env="test",
        database_url=_SQLITE_URL,
        cors_origins=["http://testserver"],
    )
    values: dict[str, object] = {
        "supabase_jwt_strategy": "hs256",
        "supabase_jwt_secret": SecretStr(_JWT_SECRET),
        "jwt_issuer": _JWT_ISSUER,
        "jwt_audience": "authenticated",
    }
    values.update(overrides)
    return base.model_copy(update=values)


def _signed_token(
    *,
    secret: str = _JWT_SECRET,
    user_id: UUID | None = None,
    lifetime_seconds: int = 300,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": str(user_id or uuid4()),
        "exp": now + lifetime_seconds,
        "iat": now,
        "iss": _JWT_ISSUER,
        "aud": "authenticated",
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, secret, algorithm="HS256")


def _create_event(
    factory: sessionmaker[Session],
    *,
    slug: str | None = None,
    status: EventStatus = EventStatus.PUBLISHED,
) -> Event:
    now = datetime.now(UTC)
    event = Event(
        slug=slug or f"event-{uuid4().hex[:12]}",
        name="Check-in Test Event",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
        timezone="UTC",
        status=status,
    )
    with factory() as session:
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def _create_ticket(
    factory: sessionmaker[Session],
    event: Event,
    *,
    token: str | None = None,
    status: TicketStatus = TicketStatus.ACTIVE,
    registration_status: RegistrationStatus = RegistrationStatus.REGISTERED,
    expires_at: datetime | None = None,
    name: str = "Ada Lovelace",
    urn: str | None = None,
    email: str | None = None,
    phone: str | None = "+1-555-0199",
) -> TicketFixture:
    suffix = uuid4().hex[:10]
    raw_token = token or generate_ticket_token()
    attendee_urn = urn or f"URN-{suffix}"
    attendee_email = email or f"attendee-{suffix}@example.com"

    attendee = Attendee(
        full_name=name,
        email=attendee_email,
        phone=phone,
        urn=attendee_urn,
    )
    registration = Registration(
        event_id=event.id,
        attendee=attendee,
        source_submission_id=f"sub-{suffix}",
        status=registration_status,
    )
    ticket = Ticket(
        registration=registration,
        token_hash=hash_ticket_token(raw_token),
        ticket_code=generate_ticket_reference(),
        status=status,
        expires_at=expires_at,
    )
    with factory() as session:
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        session.refresh(registration)
        session.refresh(attendee)
    return TicketFixture(
        token=raw_token,
        token_hash=ticket.token_hash,
        ticket_id=ticket.id,
        registration_id=registration.id,
        attendee_id=attendee.id,
        event_id=event.id,
        event_slug=event.slug,
        attendee_name=name,
        urn=attendee.urn or "",
        email=attendee.email,
        phone=phone or "",
    )


def _add_membership(
    factory: sessionmaker[Session], event_id: UUID, role: StaffRole, user_id: UUID
) -> None:
    with factory() as session:
        session.add(StaffMembership(user_id=user_id, event_id=event_id, role=role))
        session.commit()


def _post(
    client: TestClient,
    path: str,
    event_slug: str,
    token: str,
    *,
    station: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    payload: dict[str, Any] = {"ticket_token": token}
    if station is not None:
        payload["station"] = station
    return client.post(
        path.format(event_slug=event_slug),
        json=payload,
        headers=headers or {},
    )


def _count(factory: sessionmaker[Session], model: Any) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _confirmed_audit_count(factory: sessionmaker[Session], event_id: UUID) -> int:
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.event_id == event_id,
                    AuditLog.action == "checkin.confirmed",
                )
            )
            or 0
        )


def _snapshot(factory: sessionmaker[Session], ticket_id: UUID) -> dict[str, Any]:
    with factory() as session:
        ticket = session.get(Ticket, ticket_id)
        assert ticket is not None
        registration = session.get(Registration, ticket.registration_id)
        assert registration is not None
        checkin = session.scalar(select(Checkin).where(Checkin.ticket_id == ticket_id))
        return {
            "ticket_status": ticket.status,
            "ticket_used_at": ticket.used_at,
            "registration_status": registration.status,
            "registration_checked_in_at": registration.checked_in_at,
            "checkin_count": int(
                session.scalar(
                    select(func.count()).select_from(Checkin).where(Checkin.ticket_id == ticket_id)
                )
                or 0
            ),
            "checkin_at": checkin.checked_in_at if checkin else None,
            "confirmed_audits": _confirmed_audit_count(factory, ticket.registration.event_id),
        }


def _mark_previously_checked_in(
    factory: sessionmaker[Session], ticket_fixture: TicketFixture
) -> None:
    now = datetime.now(UTC)
    with factory() as session:
        session.add(
            Checkin(
                ticket_id=ticket_fixture.ticket_id,
                registration_id=ticket_fixture.registration_id,
                event_id=ticket_fixture.event_id,
                checked_in_at=now,
                scanned_by=uuid4(),
                source=CheckinSource.MOBILE,
                metadata_={},
            )
        )
        ticket = session.get(Ticket, ticket_fixture.ticket_id)
        registration = session.get(Registration, ticket_fixture.registration_id)
        assert ticket is not None and registration is not None
        ticket.status = TicketStatus.USED
        ticket.used_at = now
        registration.status = RegistrationStatus.CHECKED_IN
        registration.checked_in_at = now
        session.commit()


def _assert_no_checkin_side_effects(harness: Harness, ticket_fixture: TicketFixture) -> None:
    assert _count(harness.factory, Checkin) == 0
    assert _count(harness.factory, AuditLog) == 0
    with harness.factory() as session:
        ticket = session.get(Ticket, ticket_fixture.ticket_id)
        assert ticket is not None
        assert ticket.status == TicketStatus.ACTIVE
        assert ticket.used_at is None
        registration = session.get(Registration, ticket_fixture.registration_id)
        assert registration is not None
        assert registration.status == RegistrationStatus.REGISTERED
        assert registration.checked_in_at is None


# --- Authentication and authorization -------------------------------------------------


def test_missing_jwt_is_rejected() -> None:
    with TestClient(create_app(_settings())) as client:
        response = _post(client, _VERIFY, "any-event", generate_ticket_token())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_and_expired_jwt_are_rejected() -> None:
    wrong_secret = _signed_token(secret="another-jwt-test-secret-at-least-32-characters")
    expired = _signed_token(lifetime_seconds=-30)

    with TestClient(create_app(_settings())) as client:
        responses = [
            _post(
                client,
                _VERIFY,
                "any-event",
                generate_ticket_token(),
                headers={"Authorization": f"Bearer {token}"},
            )
            for token in (wrong_secret, expired)
        ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_jwt_role_claim_does_not_grant_checkin_access(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    _truncate(migrated_postgres)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    event = _create_event(factory)
    settings = postgres_engine_settings.model_copy(
        update={
            "supabase_jwt_strategy": "hs256",
            "supabase_jwt_secret": SecretStr(_JWT_SECRET),
            "jwt_issuer": _JWT_ISSUER,
            "jwt_audience": "authenticated",
        }
    )
    app = create_app(settings)

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = fake_session
    token = _signed_token(extra_claims={"role": "admin", "app_metadata": {"role": "admin"}})
    try:
        with TestClient(app) as client:
            response = _post(
                client,
                _VERIFY,
                event.slug,
                generate_ticket_token(),
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()
        _truncate(migrated_postgres)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_staff_without_event_membership_is_denied(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)

    verify_response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)
    confirm_response = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token)

    assert verify_response.status_code == 403
    assert confirm_response.status_code == 403
    _assert_no_checkin_side_effects(harness, ticket_fixture)


def test_viewer_cannot_verify_or_confirm(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.VIEWER, harness.user_id)

    verify_response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)
    confirm_response = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token)

    assert verify_response.status_code == 403
    assert confirm_response.status_code == 403
    _assert_no_checkin_side_effects(harness, ticket_fixture)


def test_checkin_staff_is_allowed(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "valid_ticket"


def test_admin_is_allowed(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.ADMIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "valid_ticket"


def test_membership_in_another_event_does_not_grant_access(harness: Harness) -> None:
    requested_event = _create_event(harness.factory)
    other_event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, requested_event)
    _add_membership(harness.factory, other_event.id, StaffRole.ADMIN, harness.user_id)

    response = _post(harness.client, _VERIFY, requested_event.slug, ticket_fixture.token)

    assert response.status_code == 403
    _assert_no_checkin_side_effects(harness, ticket_fixture)


# --- Verification ---------------------------------------------------------------------


def test_valid_verification_is_read_only_and_whitelisted(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)
    before = _snapshot(harness.factory, ticket_fixture.ticket_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "outcome", "message", "ticket"}
    assert body["success"] is True
    assert body["outcome"] == "valid_ticket"
    assert set(body["ticket"]) == {
        "attendee_name",
        "urn",
        "ticket_status",
        "registration_status",
        "check_in_status",
    }
    assert body["ticket"] == {
        "attendee_name": ticket_fixture.attendee_name,
        "urn": ticket_fixture.urn,
        "ticket_status": "active",
        "registration_status": "registered",
        "check_in_status": "pending",
    }
    serialized = json.dumps(body)
    for secret in (
        ticket_fixture.token,
        ticket_fixture.token_hash,
        ticket_fixture.email,
        ticket_fixture.phone,
        str(ticket_fixture.ticket_id),
        str(ticket_fixture.registration_id),
        str(ticket_fixture.attendee_id),
    ):
        assert secret not in serialized
    assert _snapshot(harness.factory, ticket_fixture.ticket_id) == before


def test_unknown_token_returns_invalid_ticket(harness: Harness) -> None:
    event = _create_event(harness.factory)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, "x" * 43)

    assert response.status_code == 200
    assert response.json()["outcome"] == "invalid_ticket"
    assert response.json()["success"] is False
    assert response.json()["ticket"] is None


def test_cross_event_token_is_indistinguishable_from_unknown(harness: Harness) -> None:
    requested_event = _create_event(harness.factory)
    other_event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, other_event)
    _add_membership(harness.factory, requested_event.id, StaffRole.CHECKIN, harness.user_id)

    verify_response = _post(harness.client, _VERIFY, requested_event.slug, ticket_fixture.token)
    confirm_response = _post(harness.client, _CONFIRM, requested_event.slug, ticket_fixture.token)

    for response in (verify_response, confirm_response):
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "invalid_ticket"
        assert body["ticket"] is None
        serialized = json.dumps(body)
        assert ticket_fixture.attendee_name not in serialized
        assert ticket_fixture.urn not in serialized
    _assert_no_checkin_side_effects(harness, ticket_fixture)


def test_revoked_ticket_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event, status=TicketStatus.REVOKED)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "revoked_ticket"
    assert body["ticket"]["ticket_status"] == "revoked"
    assert body["ticket"]["check_in_status"] == "pending"


@pytest.mark.parametrize(
    ("status", "use_past_expiry"),
    [
        (TicketStatus.EXPIRED, False),
        (TicketStatus.ACTIVE, True),
    ],
)
def test_expired_ticket_is_rejected(
    harness: Harness, status: TicketStatus, use_past_expiry: bool
) -> None:
    event = _create_event(harness.factory)
    expires_at = datetime.now(UTC) - timedelta(minutes=1) if use_past_expiry else None
    ticket_fixture = _create_ticket(harness.factory, event, status=status, expires_at=expires_at)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "expired_ticket"


def test_cancelled_registration_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(
        harness.factory, event, registration_status=RegistrationStatus.CANCELLED
    )
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "registration_cancelled"
    assert body["ticket"]["registration_status"] == "cancelled"


def test_invalid_registration_state_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(
        harness.factory, event, registration_status=RegistrationStatus.CHECKED_IN
    )
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "invalid_registration_state"


def test_previously_checked_in_ticket_reports_already_checked_in(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)
    _mark_previously_checked_in(harness.factory, ticket_fixture)
    before = _snapshot(harness.factory, ticket_fixture.ticket_id)

    response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "already_checked_in"
    assert body["success"] is False
    assert body["ticket"]["check_in_status"] == "checked_in"
    assert _snapshot(harness.factory, ticket_fixture.ticket_id) == before


# --- Atomic confirmation ---------------------------------------------------------------


def test_successful_confirmation_updates_all_records(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token, station="Gate A")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["outcome"] == "checked_in"
    assert body["ticket"]["ticket_status"] == "used"
    assert body["ticket"]["registration_status"] == "checked_in"
    assert body["ticket"]["check_in_status"] == "checked_in"

    with harness.factory() as session:
        ticket = session.get(Ticket, ticket_fixture.ticket_id)
        registration = session.get(Registration, ticket_fixture.registration_id)
        checkin = session.scalar(
            select(Checkin).where(Checkin.ticket_id == ticket_fixture.ticket_id)
        )
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.event_id == event.id,
                AuditLog.action == "checkin.confirmed",
            )
        )
        assert ticket is not None
        assert registration is not None
        assert checkin is not None
        assert audit is not None
        assert ticket.status == TicketStatus.USED
        assert ticket.used_at is not None
        assert registration.status == RegistrationStatus.CHECKED_IN
        assert registration.checked_in_at is not None
        assert checkin.event_id == event.id
        assert checkin.scanned_by == harness.user_id
        assert checkin.station == "Gate A"
        assert checkin.source == CheckinSource.MOBILE
        assert checkin.metadata_ == {"station": "Gate A"}
        assert audit.actor_user_id == harness.user_id
        assert audit.target_type == "ticket"
        assert audit.target_id == str(ticket.id)
        assert audit.context == {"outcome": "checked_in", "station": "Gate A"}


def test_duplicate_confirmation_preserves_original_state(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    first = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token)
    original = _snapshot(harness.factory, ticket_fixture.ticket_id)
    second = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token)

    assert first.json()["outcome"] == "checked_in"
    assert second.status_code == 200
    assert second.json()["outcome"] == "already_checked_in"
    assert second.json()["success"] is False
    assert _snapshot(harness.factory, ticket_fixture.ticket_id) == original
    assert _count(harness.factory, Checkin) == 1
    assert _confirmed_audit_count(harness.factory, event.id) == 1


def test_concurrent_confirmations_produce_exactly_one_checkin(harness: Harness) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token),
                range(2),
            )
        )

    outcomes = sorted(response.json()["outcome"] for response in responses)
    assert outcomes == ["already_checked_in", "checked_in"]
    assert sorted(response.json()["success"] for response in responses) == [False, True]
    assert _count(harness.factory, Checkin) == 1
    assert _confirmed_audit_count(harness.factory, event.id) == 1


def test_different_tickets_check_in_independently(harness: Harness) -> None:
    event = _create_event(harness.factory)
    first = _create_ticket(harness.factory, event)
    second = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    first_response = _post(harness.client, _CONFIRM, event.slug, first.token)
    second_response = _post(harness.client, _CONFIRM, event.slug, second.token)

    assert first_response.json()["outcome"] == "checked_in"
    assert second_response.json()["outcome"] == "checked_in"
    assert _count(harness.factory, Checkin) == 2
    assert _confirmed_audit_count(harness.factory, event.id) == 2


def test_database_failure_rolls_back_all_four_operations(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres,
        postgres_engine_settings,
        raise_server_exceptions=False,
    ) as harness:
        event = _create_event(harness.factory)
        ticket_fixture = _create_ticket(harness.factory, event)
        _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)
        before = _snapshot(harness.factory, ticket_fixture.ticket_id)

        with harness.engine.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS fail_checkin_audit ON audit_logs"))
            connection.execute(text("DROP FUNCTION IF EXISTS fail_checkin_audit()"))
            connection.execute(
                text(
                    """
                    CREATE FUNCTION fail_checkin_audit() RETURNS trigger AS $$
                    BEGIN
                      RAISE EXCEPTION 'simulated audit failure';
                    END;
                    $$ LANGUAGE plpgsql
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TRIGGER fail_checkin_audit
                    BEFORE INSERT ON audit_logs
                    FOR EACH ROW EXECUTE FUNCTION fail_checkin_audit()
                    """
                )
            )
        try:
            response = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token)
        finally:
            with harness.engine.begin() as connection:
                connection.execute(text("DROP TRIGGER IF EXISTS fail_checkin_audit ON audit_logs"))
                connection.execute(text("DROP FUNCTION IF EXISTS fail_checkin_audit()"))

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert _snapshot(harness.factory, ticket_fixture.ticket_id) == before
        assert _count(harness.factory, AuditLog) == 0


# --- Rate limits, validation, and privacy ----------------------------------------------


def test_verification_rate_limit_is_applied(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres, postgres_engine_settings, checkin_verify_rate_limit=1
    ) as built:
        event = _create_event(built.factory)
        ticket_fixture = _create_ticket(built.factory, event)
        _add_membership(built.factory, event.id, StaffRole.CHECKIN, built.user_id)

        first = _post(built.client, _VERIFY, event.slug, ticket_fixture.token)
        second = _post(built.client, _VERIFY, event.slug, ticket_fixture.token)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "TOO_MANY_REQUESTS"


def test_confirmation_rate_limit_is_applied(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres, postgres_engine_settings, checkin_confirm_rate_limit=1
    ) as built:
        event = _create_event(built.factory)
        ticket_fixture = _create_ticket(built.factory, event)
        _add_membership(built.factory, event.id, StaffRole.CHECKIN, built.user_id)

        first = _post(built.client, _CONFIRM, event.slug, ticket_fixture.token)
        second = _post(built.client, _CONFIRM, event.slug, ticket_fixture.token)

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "TOO_MANY_REQUESTS"
        assert _count(built.factory, Checkin) == 1


@pytest.mark.parametrize("station", ["x" * 101, "bad\nstation", "<script>"])
def test_invalid_station_is_rejected(harness: Harness, station: str) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    response = _post(harness.client, _CONFIRM, event.slug, ticket_fixture.token, station=station)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    _assert_no_checkin_side_effects(harness, ticket_fixture)


def test_tokens_and_pii_are_absent_from_logs_and_audit(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _create_event(harness.factory)
    ticket_fixture = _create_ticket(harness.factory, event)
    _add_membership(harness.factory, event.id, StaffRole.CHECKIN, harness.user_id)

    verify_response = _post(harness.client, _VERIFY, event.slug, ticket_fixture.token)
    confirm_response = _post(
        harness.client, _CONFIRM, event.slug, ticket_fixture.token, station="Gate B"
    )
    captured = capsys.readouterr()
    output = f"{captured.out}\n{captured.err}"

    assert verify_response.status_code == 200
    assert confirm_response.status_code == 200
    for secret in (
        ticket_fixture.token,
        ticket_fixture.token_hash,
        ticket_fixture.email,
        ticket_fixture.phone,
        ticket_fixture.urn,
        str(ticket_fixture.ticket_id),
        str(ticket_fixture.registration_id),
        str(ticket_fixture.attendee_id),
    ):
        assert secret not in output

    with harness.factory() as session:
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.event_id == event.id,
                AuditLog.action == "checkin.confirmed",
            )
        )
        assert audit is not None
        assert set(audit.context) == {"outcome", "station"}
        audit_text = json.dumps(audit.context)
        for secret in (
            ticket_fixture.token,
            ticket_fixture.token_hash,
            ticket_fixture.email,
            ticket_fixture.phone,
            ticket_fixture.urn,
        ):
            assert secret not in audit_text
