"""PostgreSQL integration tests for Phase 7 administrative APIs."""

from __future__ import annotations

import base64
import csv
import io
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
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import (
    Attendee,
    AuditLog,
    Checkin,
    EligibilityRosterEntry,
    EmailDelivery,
    Event,
    Registration,
    StaffMembership,
    Ticket,
    WebhookEvent,
)
from app.db.models.common import (
    CheckinSource,
    EmailDeliveryStatus,
    EmailPurpose,
    EventStatus,
    RegistrationStatus,
    StaffRole,
    TicketStatus,
    WebhookOutcome,
)
from app.db.session import get_session
from app.main import create_app
from app.security.jwt import AuthenticatedUser, get_current_user
from app.security.ticket_tokens import generate_ticket_reference, hash_ticket_token

pytestmark = pytest.mark.postgres

_BASE = "/api/v1/admin"
_JWT_SECRET = "admin-jwt-test-secret-at-least-32-characters"
_JWT_ISSUER = "https://project.example.supabase.co/auth/v1"
_CLEANUP_TABLES = (
    "checkins",
    "tickets",
    "email_deliveries",
    "registrations",
    "eligibility_rosters",
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
    ticket_reference: str
    ticket_id: UUID
    registration_id: UUID
    event_id: UUID
    event_slug: str
    urn: str
    name: str
    email: str
    phone: str


@dataclass(frozen=True)
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    app: FastAPI
    engine: Engine
    user_id: UUID
    current_user: list[UUID]


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
        "admin_export_rate_limit": 100,
        "admin_roster_import_rate_limit": 100,
        "checkin_verify_rate_limit": 100,
        "checkin_confirm_rate_limit": 100,
    }
    values.update(overrides)
    settings = base_settings.model_copy(update=values)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    app = create_app(settings)
    user_id = uuid4()
    current_user = [user_id]

    def fake_current_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=current_user[0])

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app, raise_server_exceptions=raise_server_exceptions) as client:
            yield Harness(client, factory, app, migrated_postgres, user_id, current_user)
    finally:
        app.dependency_overrides.clear()
        _truncate(migrated_postgres)


@pytest.fixture
def harness(migrated_postgres: Engine, postgres_engine_settings: Settings) -> Iterator[Harness]:
    with _harness(migrated_postgres, postgres_engine_settings) as built:
        yield built


def _signed_token(user_id: UUID) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "exp": now + 300,
        "iat": now,
        "iss": _JWT_ISSUER,
        "aud": "authenticated",
    }
    return jwt.encode(claims, _JWT_SECRET, algorithm="HS256")


def _jwt_settings(base: Settings) -> Settings:
    return base.model_copy(
        update={
            "supabase_jwt_strategy": "hs256",
            "supabase_jwt_secret": SecretStr(_JWT_SECRET),
            "jwt_issuer": _JWT_ISSUER,
            "jwt_audience": "authenticated",
            "admin_export_rate_limit": 100,
        }
    )


def _create_event(
    factory: sessionmaker[Session],
    *,
    slug: str | None = None,
    status: EventStatus = EventStatus.PUBLISHED,
) -> Event:
    now = datetime.now(UTC)
    event = Event(
        slug=slug or f"event-{uuid4().hex[:12]}",
        name="Admin Test Event",
        starts_at=now + timedelta(days=10),
        ends_at=now + timedelta(days=11),
        timezone="UTC",
        venue="Test Hall",
        status=status,
    )
    with factory() as session:
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def _add_membership(
    factory: sessionmaker[Session],
    event_id: UUID,
    role: StaffRole,
    user_id: UUID,
) -> None:
    with factory() as session:
        session.add(StaffMembership(user_id=user_id, event_id=event_id, role=role))
        session.commit()


def _bootstrap(harness: Harness, role: StaffRole = StaffRole.ADMIN) -> Event:
    event = _create_event(harness.factory)
    _add_membership(harness.factory, event.id, role, harness.user_id)
    return event


def _create_ticket(
    factory: sessionmaker[Session],
    event: Event,
    *,
    name: str = "Ada Lovelace",
    urn: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    token: str | None = None,
    ticket_status: TicketStatus = TicketStatus.ACTIVE,
    registration_status: RegistrationStatus = RegistrationStatus.REGISTERED,
    registered_at: datetime | None = None,
    delivery_status: EmailDeliveryStatus | None = None,
) -> TicketFixture:
    suffix = uuid4().hex[:10]
    raw_token = token or f"raw-admin-token-{suffix}-with-enough-length"
    attendee_urn = urn or f"URN-{suffix}"
    attendee_email = email or f"attendee-{suffix}@example.com"
    attendee_phone = phone if phone is not None else f"+1-555-{suffix[:4]}"
    attendee = Attendee(
        full_name=name,
        email=attendee_email,
        phone=attendee_phone,
        urn=attendee_urn,
    )
    registration = Registration(
        event_id=event.id,
        attendee=attendee,
        source_submission_id=f"sub-{suffix}",
        status=registration_status,
        registered_at=registered_at or datetime.now(UTC),
    )
    ticket = Ticket(
        registration=registration,
        token_hash=hash_ticket_token(raw_token),
        ticket_code=generate_ticket_reference(),
        status=ticket_status,
    )
    with factory() as session:
        session.add(ticket)
        session.flush()
        if delivery_status is not None:
            session.add(
                EmailDelivery(
                    registration_id=registration.id,
                    ticket_id=ticket.id,
                    purpose=EmailPurpose.TICKET_ISSUED,
                    status=delivery_status,
                    attempts=1 if delivery_status != EmailDeliveryStatus.PENDING else 0,
                    error_code="provider_timeout"
                    if delivery_status
                    in (EmailDeliveryStatus.FAILED, EmailDeliveryStatus.DEAD_LETTER)
                    else None,
                    next_attempt_at=None,
                )
            )
        session.commit()
        session.refresh(ticket)
        session.refresh(registration)
        session.refresh(attendee)
    return TicketFixture(
        token=raw_token,
        token_hash=ticket.token_hash,
        ticket_reference=ticket.ticket_code,
        ticket_id=ticket.id,
        registration_id=registration.id,
        event_id=event.id,
        event_slug=event.slug,
        urn=attendee.urn or "",
        name=attendee.full_name,
        email=attendee.email,
        phone=attendee_phone or "",
    )


def _mark_checked_in(factory: sessionmaker[Session], fixture: TicketFixture) -> None:
    now = datetime.now(UTC)
    with factory() as session:
        session.add(
            Checkin(
                ticket_id=fixture.ticket_id,
                registration_id=fixture.registration_id,
                event_id=fixture.event_id,
                checked_in_at=now,
                scanned_by=uuid4(),
                station="Gate A",
                source=CheckinSource.MOBILE,
                metadata_={},
            )
        )
        ticket = session.get(Ticket, fixture.ticket_id)
        registration = session.get(Registration, fixture.registration_id)
        assert ticket is not None and registration is not None
        ticket.status = TicketStatus.USED
        ticket.used_at = now
        registration.status = RegistrationStatus.CHECKED_IN
        registration.checked_in_at = now
        session.commit()


def _url(event_slug: str, suffix: str) -> str:
    return f"{_BASE}/events/{event_slug}/{suffix}"


def _count(factory: sessionmaker[Session], model: Any, **filters: object) -> int:
    with factory() as session:
        statement = select(func.count()).select_from(model)
        for key, value in filters.items():
            statement = statement.where(getattr(model, key) == value)
        return int(session.scalar(statement) or 0)


# --- Authentication and authorization -------------------------------------------------


def test_missing_jwt_is_rejected(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    del migrated_postgres
    app = create_app(_jwt_settings(postgres_engine_settings))
    with TestClient(app) as client:
        response = client.get(_BASE + "/events")
    assert response.status_code == 401


def test_signed_jwt_membership_is_required(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    _truncate(migrated_postgres)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    event = _create_event(factory)
    user_id = uuid4()
    _add_membership(factory, event.id, StaffRole.VIEWER, user_id)
    settings = _jwt_settings(postgres_engine_settings)
    app = create_app(settings)

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_signed_token(user_id)}"}
            viewer_event = client.get(_url(event.slug, "attendees"), headers=headers)
            viewer_staff = client.get(_url(event.slug, "staff"), headers=headers)
            stranger = client.get(
                _url(event.slug, "attendees"),
                headers={"Authorization": f"Bearer {_signed_token(uuid4())}"},
            )
    finally:
        app.dependency_overrides.clear()
        _truncate(migrated_postgres)

    assert viewer_event.status_code == 200
    assert viewer_staff.status_code == 403
    assert stranger.status_code == 403


def test_roles_are_taken_from_database_not_jwt_claims(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    _truncate(migrated_postgres)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    event = _create_event(factory)
    user_id = uuid4()
    _add_membership(factory, event.id, StaffRole.CHECKIN, user_id)
    app = create_app(_jwt_settings(postgres_engine_settings))

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = fake_session
    token = _signed_token(user_id)
    try:
        with TestClient(app) as client:
            response = client.get(
                _url(event.slug, "attendees"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Role": "admin",
                },
            )
    finally:
        app.dependency_overrides.clear()
        _truncate(migrated_postgres)

    assert response.status_code == 403


def test_checkin_role_and_missing_membership_are_denied(harness: Harness) -> None:
    admin_event = _bootstrap(harness)
    other_event = _create_event(harness.factory)

    harness.current_user[0] = uuid4()
    no_membership = harness.client.get(_url(admin_event.slug, "attendees"))

    checkin_user = uuid4()
    _add_membership(harness.factory, other_event.id, StaffRole.CHECKIN, checkin_user)
    harness.current_user[0] = checkin_user
    checkin_denied = harness.client.get(_url(other_event.slug, "attendees"))
    cross_event = harness.client.get(_url(admin_event.slug, "staff"))

    assert no_membership.status_code == 403
    assert checkin_denied.status_code == 403
    assert cross_event.status_code == 403


# --- Events ---------------------------------------------------------------------------


def _event_payload(slug: str = "new-event-2026") -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "slug": slug,
        "name": "New Event",
        "description": "A test event",
        "starts_at": (now + timedelta(days=30)).isoformat(),
        "ends_at": (now + timedelta(days=31)).isoformat(),
        "timezone": "UTC",
        "venue": "Main Hall",
        "capacity": 100,
        "registration_opens_at": (now + timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=29)).isoformat(),
    }


def test_event_create_duplicate_and_lifecycle(harness: Harness) -> None:
    _bootstrap(harness)
    payload = _event_payload()

    created = harness.client.post(_BASE + "/events", json=payload)
    duplicate = harness.client.post(_BASE + "/events", json=payload)
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert "id" not in created.json()
    assert created.json()["status"] == "draft"

    slug = payload["slug"]
    invalid_patch = harness.client.patch(
        _url(slug, "").rstrip("/"),
        json={"starts_at": payload["ends_at"]},
    )
    assert invalid_patch.status_code == 422

    published = harness.client.post(_url(slug, "publish"))
    archived = harness.client.post(_url(slug, "archive"))
    reopened = harness.client.post(_url(slug, "publish"))
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert reopened.status_code == 409


def test_event_listing_pagination(harness: Harness) -> None:
    _bootstrap(harness)
    for index in range(3):
        response = harness.client.post(
            _BASE + "/events", json=_event_payload(f"page-event-{index}")
        )
        assert response.status_code == 201

    page = harness.client.get(_BASE + "/events", params={"page": 2, "page_size": 2})
    assert page.status_code == 200
    body = page.json()
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    max_size = harness.client.get(_BASE + "/events", params={"page_size": 101})
    assert max_size.status_code == 422


def test_unauthorized_event_mutation(harness: Harness) -> None:
    event = _bootstrap(harness, StaffRole.VIEWER)
    mutation = harness.client.patch(_url(event.slug, "").rstrip("/"), json={"name": "Nope"})
    assert mutation.status_code == 403


# --- Attendees ------------------------------------------------------------------------


def test_attendee_privacy_search_filters_and_pagination(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture_a = _create_ticket(harness.factory, event, name="Grace Hopper", urn="URN-GRACE")
    fixture_b = _create_ticket(
        harness.factory,
        event,
        name="=FORMULA()",
        urn="URN-FORMULA",
        email="formula@example.com",
        ticket_status=TicketStatus.REVOKED,
    )
    _mark_checked_in(harness.factory, fixture_a)

    admin_page = harness.client.get(
        _url(event.slug, "attendees"),
        params={"page": 1, "page_size": 1, "sort_by": "name", "sort_order": "asc"},
    )
    assert admin_page.status_code == 200
    body = admin_page.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert set(body["items"][0]) >= {"email", "phone", "attendee_reference"}

    filtered = harness.client.get(
        _url(event.slug, "attendees"),
        params={"check_in_status": "checked_in", "ticket_status": "used"},
    )
    assert [item["urn"] for item in filtered.json()["items"]] == [fixture_a.urn]

    email_search = harness.client.get(
        _url(event.slug, "attendees"), params={"email": "formula@example.com"}
    )
    assert email_search.json()["items"][0]["urn"] == fixture_b.urn

    viewer_id = uuid4()
    _add_membership(harness.factory, event.id, StaffRole.VIEWER, viewer_id)
    harness.current_user[0] = viewer_id
    viewer_page = harness.client.get(_url(event.slug, "attendees"))
    viewer_detail = harness.client.get(_url(event.slug, f"attendees/{fixture_b.urn}"))
    viewer_email_search = harness.client.get(
        _url(event.slug, "attendees"), params={"email": "formula@example.com"}
    )
    viewer_body = viewer_page.json()["items"][0]
    assert viewer_page.status_code == 200
    assert set(viewer_body) == {
        "attendee_reference",
        "full_name",
        "urn",
        "registration_status",
        "ticket_status",
        "check_in_status",
        "checked_in_at",
    }
    assert "email" not in viewer_detail.text
    assert viewer_email_search.status_code == 403


def test_cross_event_attendee_reference_is_not_disclosed(harness: Harness) -> None:
    event = _bootstrap(harness)
    other_event = _create_event(harness.factory)
    fixture = _create_ticket(harness.factory, other_event)

    response = harness.client.get(_url(event.slug, f"attendees/{fixture.urn}"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- Registrations ---------------------------------------------------------------------


def test_registration_cancel_revokes_ticket_and_is_idempotent(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event)

    first = harness.client.post(_url(event.slug, f"registrations/{fixture.urn}/cancel"))
    second = harness.client.post(_url(event.slug, f"registrations/{fixture.urn}/cancel"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["registration_status"] == "cancelled"
    assert first.json()["ticket_status"] == "revoked"

    with harness.factory() as session:
        ticket = session.get(Ticket, fixture.ticket_id)
        registration = session.get(Registration, fixture.registration_id)
        assert ticket is not None and registration is not None
        assert ticket.status == TicketStatus.REVOKED
        assert registration.status == RegistrationStatus.CANCELLED

    assert _count(harness.factory, AuditLog, action="registration.cancelled") == 1

    verify = harness.client.post(
        f"/api/v1/events/{event.slug}/checkins/verify",
        json={"ticket_token": fixture.token},
    )
    assert verify.status_code == 200
    assert verify.json()["outcome"] == "registration_cancelled"


def test_checked_in_registration_cannot_be_cancelled(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event)
    _mark_checked_in(harness.factory, fixture)

    response = harness.client.post(_url(event.slug, f"registrations/{fixture.urn}/cancel"))
    assert response.status_code == 409
    with harness.factory() as session:
        registration = session.get(Registration, fixture.registration_id)
        assert registration is not None
        assert registration.status == RegistrationStatus.CHECKED_IN
    assert _count(harness.factory, AuditLog, action="registration.cancelled") == 0


def test_registration_filters_and_cross_event_denial(harness: Harness) -> None:
    event = _bootstrap(harness)
    other_event = _create_event(harness.factory)
    own = _create_ticket(harness.factory, event)
    _create_ticket(harness.factory, other_event)

    listed = harness.client.get(
        _url(event.slug, "registrations"),
        params={"reference": own.urn, "registration_status": "registered"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    cross = harness.client.get(_url(event.slug, f"registrations/{own.urn}"))
    assert cross.status_code == 200
    other = _create_ticket(harness.factory, other_event, urn="URN-OTHER-EVENT")
    denied = harness.client.get(_url(event.slug, f"registrations/{other.urn}"))
    assert denied.status_code == 404


# --- Tickets and email resend ----------------------------------------------------------


def test_ticket_revoke_fails_checkin_and_is_audited(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event)

    listed = harness.client.get(_url(event.slug, "tickets"), params={"ticket_status": "active"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fixture.token not in listed.text
    assert fixture.token_hash not in listed.text

    revoked = harness.client.post(_url(event.slug, f"tickets/{fixture.ticket_reference}/revoke"))
    repeated = harness.client.post(_url(event.slug, f"tickets/{fixture.ticket_reference}/revoke"))
    assert revoked.status_code == 200
    assert repeated.status_code == 200
    assert revoked.json()["ticket_status"] == "revoked"
    assert _count(harness.factory, AuditLog, action="ticket.revoked") == 1

    confirm = harness.client.post(
        f"/api/v1/events/{event.slug}/checkins/confirm",
        json={"ticket_token": fixture.token},
    )
    assert confirm.status_code == 200
    assert confirm.json()["outcome"] == "revoked_ticket"


def test_resend_creates_outbox_job_without_direct_send(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event, delivery_status=EmailDeliveryStatus.SENT)
    calls: list[object] = []

    def forbidden_send(*args: object, **kwargs: object) -> str:
        calls.append((args, kwargs))
        return "should-not-happen"

    from app.services.email_gateway import ResendEmailGateway

    monkeypatch.setattr(ResendEmailGateway, "send_ticket_email", forbidden_send)

    first = harness.client.post(_url(event.slug, f"tickets/{fixture.ticket_reference}/resend"))
    duplicate = harness.client.post(_url(event.slug, f"tickets/{fixture.ticket_reference}/resend"))
    assert first.status_code == 200
    assert first.json()["resend_sequence"] == 1
    assert duplicate.status_code == 409
    assert not calls

    with harness.factory() as session:
        deliveries = list(
            session.scalars(
                select(EmailDelivery).where(EmailDelivery.ticket_id == fixture.ticket_id)
            )
        )
    assert len(deliveries) == 2
    assert sorted(delivery.resend_sequence for delivery in deliveries) == [0, 1]
    assert any(delivery.status == EmailDeliveryStatus.SENT for delivery in deliveries)
    assert any(
        delivery.status == EmailDeliveryStatus.PENDING and delivery.resend_sequence == 1
        for delivery in deliveries
    )


def test_used_ticket_resend_is_rejected(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event, delivery_status=EmailDeliveryStatus.SENT)
    _mark_checked_in(harness.factory, fixture)

    response = harness.client.post(_url(event.slug, f"tickets/{fixture.ticket_reference}/resend"))
    assert response.status_code == 409


# --- Staff -----------------------------------------------------------------------------


def test_staff_add_change_remove_and_final_admin_rules(harness: Harness) -> None:
    event = _bootstrap(harness)
    new_user = uuid4()

    invalid = harness.client.post(
        _url(event.slug, "staff"), json={"user_id": "not-a-uuid", "role": "viewer"}
    )
    assert invalid.status_code == 422

    added = harness.client.post(
        _url(event.slug, "staff"), json={"user_id": str(new_user), "role": "viewer"}
    )
    assert added.status_code == 201
    changed = harness.client.patch(_url(event.slug, f"staff/{new_user}"), json={"role": "checkin"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "checkin"

    removed = harness.client.delete(_url(event.slug, f"staff/{new_user}"))
    assert removed.status_code == 204

    demote = harness.client.patch(
        _url(event.slug, f"staff/{harness.user_id}"), json={"role": "viewer"}
    )
    remove_final = harness.client.delete(_url(event.slug, f"staff/{harness.user_id}"))
    assert demote.status_code == 409
    assert remove_final.status_code == 409
    assert _count(harness.factory, AuditLog, action="staff.role_changed") == 1
    assert _count(harness.factory, AuditLog, action="staff.removed") == 1


# --- Analytics -------------------------------------------------------------------------


def test_empty_event_analytics(harness: Harness) -> None:
    event = _bootstrap(harness)
    overview = harness.client.get(_url(event.slug, "analytics/overview"))
    attendance = harness.client.get(_url(event.slug, "analytics/attendance"))
    registrations = harness.client.get(_url(event.slug, "analytics/registrations"))
    email = harness.client.get(_url(event.slug, "analytics/email-deliveries"))

    assert overview.status_code == 200
    assert all(value == 0 for value in overview.json().values())
    assert attendance.json()["attendance_percentage"] == 0.0
    assert registrations.json()["buckets"] == []
    assert email.json()["total_deliveries"] == 0


def test_analytics_counts_ranges_and_privacy(harness: Harness) -> None:
    event = _bootstrap(harness)
    now = datetime.now(UTC)
    old = now - timedelta(days=10)
    first = _create_ticket(
        harness.factory,
        event,
        registered_at=old,
        delivery_status=EmailDeliveryStatus.SENT,
    )
    _create_ticket(harness.factory, event, delivery_status=EmailDeliveryStatus.PENDING)
    _mark_checked_in(harness.factory, first)
    with harness.factory() as session:
        session.add(
            WebhookEvent(
                source="google_forms",
                event_slug=event.slug,
                submission_id="declined-1",
                request_id=f"req-{uuid4()}",
                payload_hash="a" * 64,
                outcome=WebhookOutcome.IGNORED_DECLINED,
            )
        )
        session.commit()

    overview_response = harness.client.get(_url(event.slug, "analytics/overview"))
    attendance_response = harness.client.get(_url(event.slug, "analytics/attendance"))
    range_response = harness.client.get(
        _url(event.slug, "analytics/registrations"),
        params={
            "from_date": (now - timedelta(days=5)).isoformat(),
            "to_date": (now + timedelta(days=1)).isoformat(),
        },
    )
    email_response = harness.client.get(_url(event.slug, "analytics/email-deliveries"))

    overview = overview_response.json()
    attendance = attendance_response.json()
    assert overview["total_registrations"] == 2
    assert overview["confirmed_registrations"] == 2
    assert overview["checked_in_attendees"] == 1
    assert overview["not_checked_in_attendees"] == 1
    assert overview["declined_rsvps"] == 1
    assert overview["used_tickets"] == 1
    assert overview["active_tickets"] == 1
    assert overview["sent_email_deliveries"] == 1
    assert overview["pending_email_deliveries"] == 1
    assert attendance["attendance_percentage"] == 50.0
    assert range_response.json()["granularity"] == "day"
    assert sum(item["count"] for item in range_response.json()["buckets"]) == 1
    assert email_response.json()["status_counts"]["pending"] == 1
    assert email_response.json()["attempt_summary"]["total_attempts"] == 1
    assert email_response.json()["attempt_summary"]["max_attempts"] == 1
    assert email_response.json()["attempt_summary"]["retried_deliveries"] == 0

    serialized = (
        overview_response.text
        + attendance_response.text
        + range_response.text
        + email_response.text
    )
    for leaked in (first.name, first.email, first.urn, first.token_hash):
        assert leaked not in serialized


# --- Exports ---------------------------------------------------------------------------


def test_csv_export_headers_formula_safety_and_privacy(harness: Harness) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event, name='=HYPERLINK("evil")')
    _mark_checked_in(harness.factory, fixture)

    attendees = harness.client.get(_url(event.slug, "exports/attendees.csv"))
    checkins = harness.client.get(_url(event.slug, "exports/checkins.csv"))

    assert attendees.status_code == 200
    assert attendees.headers["content-type"].startswith("text/csv")
    assert attendees.headers["content-disposition"] == (
        f'attachment; filename="attendees-{event.slug}.csv"'
    )
    rows = list(csv.reader(io.StringIO(attendees.text)))
    assert rows[0] == [
        "name",
        "urn",
        "email",
        "phone",
        "registration_status",
        "ticket_status",
        "registered_at",
        "checked_in_at",
        "station",
    ]
    assert rows[1][0] == '\'=HYPERLINK("evil")'
    assert checkins.headers["content-disposition"] == (
        f'attachment; filename="checkins-{event.slug}.csv"'
    )
    checkin_rows = list(csv.reader(io.StringIO(checkins.text)))
    assert "checked_in_at" in checkin_rows[0]
    assert "station" in checkin_rows[0]
    assert "Gate A" in checkin_rows[1]
    for response in (attendees, checkins):
        assert fixture.token not in response.text
        assert fixture.token_hash not in response.text
        assert fixture.ticket_reference not in response.text


def test_xlsx_export_is_valid(harness: Harness) -> None:
    from openpyxl import load_workbook

    event = _bootstrap(harness)
    fixture = _create_ticket(harness.factory, event, name="+SUM(1,2)")

    response = harness.client.get(_url(event.slug, "exports/attendees.xlsx"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"].endswith('.xlsx"')
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    assert rows[0][0] == "name"
    assert rows[1][0] == "'+SUM(1,2)"
    workbook.close()
    assert fixture.token not in response.content.decode("latin-1", errors="ignore")


def test_export_authorization_and_rate_limit(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres,
        postgres_engine_settings,
        admin_export_rate_limit=1,
        rate_limit_window_seconds=60,
    ) as harness:
        event = _bootstrap(harness)
        first = harness.client.get(_url(event.slug, "exports/attendees.csv"))
        second = harness.client.get(_url(event.slug, "exports/attendees.csv"))

        viewer_id = uuid4()
        _add_membership(harness.factory, event.id, StaffRole.VIEWER, viewer_id)
        harness.current_user[0] = viewer_id
        viewer = harness.client.get(_url(event.slug, "exports/attendees.csv"))

    assert first.status_code == 200
    assert second.status_code == 429
    assert viewer.status_code == 403


# --- Audit logs ------------------------------------------------------------------------


def test_audit_log_filters_and_no_mutation_endpoint(harness: Harness) -> None:
    event = _bootstrap(harness)
    payload = _event_payload("audit-event")
    created = harness.client.post(_BASE + "/events", json=payload)
    published = harness.client.post(_url(payload["slug"], "publish"))
    added = harness.client.post(
        _url(event.slug, "staff"),
        json={"user_id": str(uuid4()), "role": "viewer"},
    )
    listed = harness.client.get(
        _url(event.slug, "audit-logs"),
        params={
            "action": "staff.added",
            "actor_user_id": str(harness.user_id),
            "page": 1,
            "page_size": 10,
            "sort_order": "asc",
        },
    )
    # Audit logs are event-scoped: the new event has its own admin membership.
    new_event_logs = harness.client.get(
        _url(payload["slug"], "audit-logs"),
        params={"action": "event.published", "actor_user_id": str(harness.user_id)},
    )
    patch = harness.client.patch(_url(event.slug, "audit-logs"), json={})
    delete = harness.client.delete(_url(event.slug, "audit-logs"))

    assert created.status_code == 201
    assert published.status_code == 200
    assert added.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert new_event_logs.status_code == 200
    assert new_event_logs.json()["total"] == 1
    assert set(new_event_logs.json()["items"][0]) == {
        "audit_reference",
        "action",
        "target_type",
        "target_id",
        "context",
        "actor_user_id",
        "created_at",
    }
    assert patch.status_code == 405
    assert delete.status_code == 405


# --- Email monitoring ------------------------------------------------------------------


def test_email_monitoring_filters_and_retry(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _bootstrap(harness)
    fixture = _create_ticket(
        harness.factory,
        event,
        delivery_status=EmailDeliveryStatus.FAILED,
    )
    calls: list[object] = []

    def forbidden_send(*args: object, **kwargs: object) -> str:
        calls.append((args, kwargs))
        return "should-not-happen"

    from app.services.email_gateway import ResendEmailGateway

    monkeypatch.setattr(ResendEmailGateway, "send_ticket_email", forbidden_send)

    listed = harness.client.get(
        _url(event.slug, "email-deliveries"),
        params={
            "status": "failed",
            "registration_reference": fixture.urn,
            "ticket_reference": fixture.ticket_reference,
            "min_attempts": 1,
        },
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    delivery_id = listed.json()["items"][0]["delivery_reference"]
    assert listed.json()["items"][0]["error_code"] == "provider_timeout"

    retried = harness.client.post(_url(event.slug, f"email-deliveries/{delivery_id}/retry"))
    assert retried.status_code == 200
    assert retried.json()["previous_status"] == "failed"
    assert retried.json()["resend_sequence"] == 1
    assert not calls

    with harness.factory() as session:
        deliveries = list(
            session.scalars(
                select(EmailDelivery).where(EmailDelivery.ticket_id == fixture.ticket_id)
            )
        )
    assert len(deliveries) == 2
    old = next(item for item in deliveries if str(item.id) == delivery_id)
    assert old.status == EmailDeliveryStatus.DEAD_LETTER
    assert old.attempts == 1
    assert old.error_code == "provider_timeout"
    assert any(
        item.status == EmailDeliveryStatus.PENDING and item.resend_sequence == 1
        for item in deliveries
    )

    repeat = harness.client.post(_url(event.slug, f"email-deliveries/{delivery_id}/retry"))
    assert repeat.status_code == 409


# --- Event-scoped eligibility roster ----------------------------------------------------


def _roster_body(
    text: str, *, filename: str = "roster.csv", confirm: bool = False
) -> dict[str, object]:
    body: dict[str, object] = {
        "filename": filename,
        "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }
    if confirm:
        body["confirm"] = True
    return body


def _roster_count(factory: sessionmaker[Session], event_id: UUID | None = None) -> int:
    with factory() as session:
        statement = select(func.count()).select_from(EligibilityRosterEntry)
        if event_id is not None:
            statement = statement.where(EligibilityRosterEntry.event_id == event_id)
        return int(session.scalar(statement) or 0)


def test_roster_dry_run_confirmed_import_and_redacted_audit(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _bootstrap(harness)
    csv_text = (
        "Lead ID,URN,Name\n"
        "1, roster-a1 ,Alpha\n"
        "2,ROSTER-B2,Beta\n"
        "3,,Missing\n"
        "4,roster-a1,Duplicate\n"
    )
    body = _roster_body(csv_text)

    dry_run = harness.client.post(_url(event.slug, "eligibility-roster/import/dry-run"), json=body)
    confirmed = harness.client.post(
        _url(event.slug, "eligibility-roster/import"), json=_roster_body(csv_text, confirm=True)
    )
    listed = harness.client.get(_url(event.slug, "eligibility-roster"))

    assert dry_run.status_code == 200
    assert dry_run.json() == {
        "mode": "dry_run",
        "rows": 4,
        "valid_unique": 2,
        "duplicates": 1,
        "invalid_rows": 1,
        "already_imported": 0,
        "imported": 0,
        "skipped": 0,
    }
    assert confirmed.status_code == 201
    assert confirmed.json() == {
        "mode": "confirmed",
        "rows": 4,
        "valid_unique": 2,
        "duplicates": 1,
        "invalid_rows": 1,
        "already_imported": 0,
        "imported": 2,
        "skipped": 0,
    }
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert {item["normalized_urn"] for item in listed.json()["items"]} == {
        "ROSTER-A1",
        "ROSTER-B2",
    }
    assert _roster_count(harness.factory, event.id) == 2

    with harness.factory() as session:
        assert session.scalar(select(func.count()).select_from(Registration)) == 0
        assert session.scalar(select(func.count()).select_from(Ticket)) == 0
        assert session.scalar(select(func.count()).select_from(EmailDelivery)) == 0

    audit = harness.client.get(_url(event.slug, "audit-logs"), params={"action": "roster.imported"})
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["items"][0]["context"] == {
        "outcome": "success",
        "rows": 4,
        "valid_unique": 2,
        "duplicates": 1,
        "invalid_rows": 1,
        "already_imported": 0,
        "imported": 2,
        "skipped": 0,
    }
    captured = capsys.readouterr()
    output = f"{captured.out}\n{captured.err}"
    assert "ROSTER-A1" not in output
    assert "ROSTER-B2" not in output


def test_roster_dry_run_has_no_database_side_effects(harness: Harness) -> None:
    event = _bootstrap(harness)
    body = _roster_body("Lead ID,URN,Name\n1,DRY-RUN-URN,Ada\n")

    response = harness.client.post(_url(event.slug, "eligibility-roster/import/dry-run"), json=body)

    assert response.status_code == 200
    assert response.json()["imported"] == 0
    assert _roster_count(harness.factory) == 0
    assert _count_audit_logs(harness.factory) == 0


def _count_audit_logs(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(AuditLog)) or 0)


def test_roster_import_requires_event_admin(harness: Harness) -> None:
    event = _bootstrap(harness, role=StaffRole.VIEWER)
    body = _roster_body("Lead ID,URN,Name\n1,PRIVATE-URN,Ada\n", confirm=True)

    listed = harness.client.get(_url(event.slug, "eligibility-roster"))
    dry_run = harness.client.post(_url(event.slug, "eligibility-roster/import/dry-run"), json=body)
    confirmed = harness.client.post(_url(event.slug, "eligibility-roster/import"), json=body)

    assert listed.status_code == 403
    assert dry_run.status_code == 403
    assert confirmed.status_code == 403
    assert _roster_count(harness.factory) == 0
    assert _count_audit_logs(harness.factory) == 0


def test_roster_is_event_scoped_for_admin_of_another_event(harness: Harness) -> None:
    owned = _bootstrap(harness)
    other = _create_event(harness.factory)
    body = _roster_body("Lead ID,URN,Name\n1,OTHER-EVENT-URN,Ada\n", confirm=True)

    denied = harness.client.post(_url(other.slug, "eligibility-roster/import"), json=body)
    allowed = harness.client.post(_url(owned.slug, "eligibility-roster/import"), json=body)

    assert denied.status_code == 403
    assert allowed.status_code == 201
    assert _roster_count(harness.factory, other.id) == 0
    assert _roster_count(harness.factory, owned.id) == 1


def test_roster_import_normalization_duplicates_and_leading_zeros(harness: Harness) -> None:
    event = _bootstrap(harness)
    other = _bootstrap(harness)
    csv_text = (
        "Lead ID,URN,Name\n"
        "1,  abc-001 ,Alpha\n"
        "2,ABC-001,Duplicate\n"
        "3,00123,Leading Zero\n"
        "4,,Missing\n"
    )

    first = harness.client.post(
        _url(event.slug, "eligibility-roster/import"),
        json=_roster_body(csv_text, confirm=True),
    )
    second = harness.client.post(
        _url(other.slug, "eligibility-roster/import"),
        json=_roster_body(csv_text, confirm=True),
    )
    repeat = harness.client.post(
        _url(event.slug, "eligibility-roster/import"),
        json=_roster_body(csv_text, confirm=True),
    )

    assert first.json()["imported"] == 2
    assert second.json()["imported"] == 2
    assert repeat.json()["already_imported"] == 2
    assert repeat.json()["imported"] == 0
    assert repeat.json()["skipped"] == 2
    assert _roster_count(harness.factory, event.id) == 2
    assert _roster_count(harness.factory, other.id) == 2

    with harness.factory() as session:
        urns = set(
            session.scalars(
                select(EligibilityRosterEntry.normalized_urn).where(
                    EligibilityRosterEntry.event_id == event.id
                )
            )
        )
    assert urns == {"ABC-001", "00123"}


@pytest.mark.parametrize(
    ("filename", "csv_text"),
    [
        ("../roster.csv", "Lead ID,URN,Name\n1,SAFE-URN,Ada\n"),
        ("/tmp/roster.csv", "Lead ID,URN,Name\n1,SAFE-URN,Ada\n"),
        ("roster.txt", "Lead ID,URN,Name\n1,SAFE-URN,Ada\n"),
        ("roster.csv", "Lead ID;URN;Name\n1;SAFE-URN;Ada\n"),
        ("roster.csv", "Lead ID,Student,Name\n1,SAFE-URN,Ada\n"),
        ("roster.csv", "Lead ID,URN,URN\n1,SAFE-URN,OTHER\n"),
    ],
)
def test_roster_import_rejects_unsafe_or_malformed_uploads(
    harness: Harness, filename: str, csv_text: str
) -> None:
    event = _bootstrap(harness)
    response = harness.client.post(
        _url(event.slug, "eligibility-roster/import/dry-run"),
        json=_roster_body(csv_text, filename=filename),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _roster_count(harness.factory) == 0


def test_roster_import_rejects_invalid_base64(harness: Harness) -> None:
    event = _bootstrap(harness)
    response = harness.client.post(
        _url(event.slug, "eligibility-roster/import/dry-run"),
        json={"filename": "roster.csv", "content_base64": "not-base64!"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_roster_import_rate_limit(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres,
        postgres_engine_settings,
        admin_roster_import_rate_limit=1,
    ) as limited:
        event = _bootstrap(limited)
        body = _roster_body("Lead ID,URN,Name\n1,RATE-LIMIT-URN,Ada\n")
        first = limited.client.post(
            _url(event.slug, "eligibility-roster/import/dry-run"), json=body
        )
        second = limited.client.post(
            _url(event.slug, "eligibility-roster/import/dry-run"), json=body
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "TOO_MANY_REQUESTS"


def test_roster_import_enforces_size_and_row_limits(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    with _harness(
        migrated_postgres,
        postgres_engine_settings,
        roster_import_max_upload_bytes=1024,
        roster_import_max_rows=2,
    ) as limited:
        event = _bootstrap(limited)
        oversized = _roster_body(
            "Lead ID,URN,Name\n" + "".join(f"{i},URN-{i},Name\n" for i in range(100))
        )
        too_many_rows = _roster_body("Lead ID,URN,Name\n1,URN-A,A\n2,URN-B,B\n3,URN-C,C\n")
        size_response = limited.client.post(
            _url(event.slug, "eligibility-roster/import/dry-run"), json=oversized
        )
        row_response = limited.client.post(
            _url(event.slug, "eligibility-roster/import/dry-run"), json=too_many_rows
        )

    assert size_response.status_code == 422
    assert row_response.status_code == 422
    assert _roster_count(limited.factory) == 0


def test_concurrent_roster_imports_are_unique(harness: Harness) -> None:
    event = _bootstrap(harness)
    csv_text = "Lead ID,URN,Name\n1,CONCURRENT-A,A\n2,CONCURRENT-B,B\n3,CONCURRENT-C,C\n"
    body = _roster_body(csv_text, confirm=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: harness.client.post(
                    _url(event.slug, "eligibility-roster/import"), json=body
                ),
                range(2),
            )
        )

    assert all(response.status_code == 201 for response in responses)
    assert sum(int(response.json()["imported"]) for response in responses) == 3
    assert _roster_count(harness.factory, event.id) == 3
    assert _count_audit_logs(harness.factory) == 2
