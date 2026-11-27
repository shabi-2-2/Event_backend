"""PostgreSQL-backed Google Forms webhook ingestion tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Attendee, Event, Registration, WebhookEvent
from app.db.models.common import EventStatus, RegistrationStatus, WebhookOutcome
from app.main import create_app
from app.schemas.webhook import RsvpWebhookRequest
from app.security.webhook import WEBHOOK_PATH
from app.services import webhook_ingestion

pytestmark = pytest.mark.postgres

ENDPOINT = "/api/v1/webhooks/google-forms"
SECRET = "phase4-webhook-test-secret"

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
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    settings: Settings


def _truncate(engine: Engine) -> None:
    tables = ", ".join(_CLEANUP_TABLES)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def _make_client(base_settings: Settings, **overrides: object) -> TestClient:
    values: dict[str, object] = {
        "webhook_signing_keys": {"v1": SecretStr(SECRET)},
        "webhook_rate_limit": 1000,
    }
    values.update(overrides)
    return TestClient(create_app(base_settings.model_copy(update=values)))


@pytest.fixture
def harness(
    migrated_postgres: Engine,
    postgres_engine_settings: Settings,
) -> Iterator[Harness]:
    _truncate(migrated_postgres)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    with _make_client(postgres_engine_settings) as client:
        yield Harness(client=client, factory=factory, settings=postgres_engine_settings)
    _truncate(migrated_postgres)


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _headers(
    body: bytes,
    *,
    key_id: str = "v1",
    timestamp: str | None = None,
    secret: str = SECRET,
) -> dict[str, str]:
    supplied_timestamp = timestamp or str(int(time.time()))
    message = f"{supplied_timestamp}.POST.{WEBHOOK_PATH}.".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Key-Id": key_id,
        "X-Webhook-Timestamp": supplied_timestamp,
        "X-Webhook-Signature": signature,
        "Content-Type": "application/json",
    }


def _post(client: TestClient, payload: dict[str, Any], **header_overrides: object) -> Response:
    body = _body(payload)
    headers = _headers(body)
    headers.update(header_overrides)  # type: ignore[arg-type]
    return client.post(ENDPOINT, content=body, headers=headers)


def _payload(
    event_slug: str,
    submission_id: str,
    *,
    attendance: str = "yes",
    email: str | None = None,
    urn: str | None = None,
    name: str = "Test Attendee",
    phone: str | None = None,
) -> dict[str, Any]:
    suffix = uuid4().hex[:10]
    return {
        "event_slug": event_slug,
        "submission_id": submission_id,
        "name": name,
        "email": email or f"attendee-{suffix}@example.com",
        "phone": phone,
        "urn": urn or f"URN-{suffix}",
        "attendance": attendance,
    }


def _create_event(
    factory: sessionmaker[Session],
    *,
    status: EventStatus = EventStatus.PUBLISHED,
    capacity: int | None = None,
    registration_opens_at: datetime | None = None,
    registration_closes_at: datetime | None = None,
) -> Event:
    slug = f"event-{uuid4().hex[:12]}"
    now = datetime.now(UTC)
    with factory() as session:
        event = Event(
            slug=slug,
            name="Webhook Test Event",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            timezone="UTC",
            status=status,
            capacity=capacity,
            registration_opens_at=registration_opens_at,
            registration_closes_at=registration_closes_at,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def _add_attendee(
    factory: sessionmaker[Session],
    *,
    email: str,
    urn: str,
    name: str = "Existing Attendee",
) -> Attendee:
    with factory() as session:
        attendee = Attendee(full_name=name, email=email, urn=urn)
        session.add(attendee)
        session.commit()
        session.refresh(attendee)
        return attendee


def _count(factory: sessionmaker[Session], model: Any) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _ledger(
    factory: sessionmaker[Session], event_slug: str, submission_id: str
) -> WebhookEvent | None:
    with factory() as session:
        return session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.event_slug == event_slug,
                WebhookEvent.submission_id == submission_id,
            )
        )


def test_valid_signed_request_is_registered(harness: Harness) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-valid", name="  Grace Hopper  ")

    response = _post(harness.client, payload)

    assert response.status_code == 201
    assert response.json() == {
        "success": True,
        "outcome": "registered",
        "submission_id": "sub-valid",
        "message": "RSVP registered.",
    }
    with harness.factory() as session:
        registration = session.scalar(
            select(Registration).where(Registration.source_submission_id == "sub-valid")
        )
        assert registration is not None
        assert registration.status == RegistrationStatus.REGISTERED
        attendee = session.get(Attendee, registration.attendee_id)
        assert attendee is not None
        assert attendee.full_name == "Grace Hopper"
        assert attendee.email == payload["email"].lower()
        assert attendee.urn == payload["urn"].upper()

    ledger = _ledger(harness.factory, event.slug, "sub-valid")
    assert ledger is not None
    assert ledger.outcome == WebhookOutcome.REGISTERED
    assert ledger.payload_hash == hashlib.sha256(_body(payload)).hexdigest()
    assert ledger.error_code is None


def test_declined_rsvp_is_recorded_without_registration(harness: Harness) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-declined", attendance="no")

    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "declined"
    assert _count(harness.factory, Registration) == 0
    ledger = _ledger(harness.factory, event.slug, "sub-declined")
    assert ledger is not None
    assert ledger.outcome == WebhookOutcome.IGNORED_DECLINED
    assert ledger.error_code is None


def test_unknown_event_is_recorded_as_unavailable(harness: Harness) -> None:
    payload = _payload("missing-event", "sub-unknown")

    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "event_unavailable"
    ledger = _ledger(harness.factory, "missing-event", "sub-unknown")
    assert ledger is not None
    assert ledger.outcome == WebhookOutcome.REJECTED
    assert ledger.error_code == "event_unavailable"


def test_closed_event_is_unavailable(harness: Harness) -> None:
    event = _create_event(harness.factory, status=EventStatus.DRAFT)
    payload = _payload(event.slug, "sub-closed")

    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "event_unavailable"
    assert _count(harness.factory, Registration) == 0


def test_event_with_past_registration_window_is_unavailable(harness: Harness) -> None:
    past = datetime.now(UTC) - timedelta(days=1)
    event = _create_event(harness.factory, registration_closes_at=past)
    payload = _payload(event.slug, "sub-past-window")

    response = _post(harness.client, payload)

    assert response.json()["outcome"] == "event_unavailable"


def test_capacity_reached_is_controlled(harness: Harness) -> None:
    event = _create_event(harness.factory, capacity=1)
    existing = _add_attendee(harness.factory, email="seed@example.com", urn="SEED-URN")
    with harness.factory() as session:
        session.add(
            Registration(
                event_id=event.id,
                attendee_id=existing.id,
                source_submission_id="seed-submission",
            )
        )
        session.commit()

    payload = _payload(event.slug, "sub-over-capacity")
    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "capacity_reached"
    assert _count(harness.factory, Registration) == 1
    ledger = _ledger(harness.factory, event.slug, "sub-over-capacity")
    assert ledger is not None
    assert ledger.error_code == "capacity_reached"


def test_existing_matching_attendee_is_reused_without_overwrite(harness: Harness) -> None:
    event = _create_event(harness.factory)
    email = "matching@example.com"
    urn = "MATCH-URN"
    existing = _add_attendee(harness.factory, email=email, urn=urn, name="Original Name")
    original_phone = "111"
    with harness.factory() as session:
        attendee = session.get(Attendee, existing.id)
        assert attendee is not None
        attendee.phone = original_phone
        session.commit()

    payload = _payload(
        event.slug,
        "sub-existing-match",
        email=email.upper(),
        urn=f"  {urn.lower()}  ",
        name="Changed Name",
        phone="999",
    )
    response = _post(harness.client, payload)

    assert response.status_code == 201
    assert _count(harness.factory, Attendee) == 1
    with harness.factory() as session:
        attendee = session.get(Attendee, existing.id)
        assert attendee is not None
        assert attendee.full_name == "Original Name"
        assert attendee.phone == original_phone


def test_urn_conflict_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    _add_attendee(harness.factory, email="owner@example.com", urn="CONFLICT-URN")

    payload = _payload(
        event.slug,
        "sub-urn-conflict",
        email="different@example.com",
        urn="CONFLICT-URN",
    )
    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "identity_conflict"
    assert _count(harness.factory, Registration) == 0
    assert _count(harness.factory, Attendee) == 1


def test_email_conflict_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    _add_attendee(harness.factory, email="taken@example.com", urn="OWNER-URN")

    payload = _payload(
        event.slug,
        "sub-email-conflict",
        email="TAKEN@example.com",
        urn="NEW-URN",
    )
    response = _post(harness.client, payload)

    assert response.json()["outcome"] == "identity_conflict"
    assert _count(harness.factory, Registration) == 0
    assert _count(harness.factory, Attendee) == 1


def test_different_submission_for_registered_attendee_is_already_registered(
    harness: Harness,
) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-first", email="repeat@example.com", urn="REPEAT-URN")
    assert _post(harness.client, payload).status_code == 201

    second = _payload(
        event.slug,
        "sub-second",
        email="repeat@example.com",
        urn="REPEAT-URN",
    )
    response = _post(harness.client, second)

    assert response.status_code == 200
    assert response.json()["outcome"] == "already_registered"
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, Attendee) == 1


def test_duplicate_submission_is_idempotent(harness: Harness) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-duplicate")

    first = _post(harness.client, payload)
    second = _post(harness.client, payload)

    assert first.status_code == 201
    assert first.json()["outcome"] == "registered"
    assert second.status_code == 200
    assert second.json() == {
        "success": True,
        "outcome": "duplicate_submission",
        "submission_id": "sub-duplicate",
        "message": "Submission already processed.",
    }
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, WebhookEvent) == 1
    assert _count(harness.factory, Attendee) == 1


def test_concurrent_duplicate_submissions_are_idempotent(harness: Harness) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-concurrent-duplicate")
    body = _body(payload)
    headers = _headers(body)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: harness.client.post(ENDPOINT, content=body, headers=headers),
                range(2),
            )
        )

    outcomes = sorted(response.json()["outcome"] for response in responses)
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert outcomes == ["duplicate_submission", "registered"]
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, WebhookEvent) == 1


def test_concurrent_registrations_respect_capacity(harness: Harness) -> None:
    event = _create_event(harness.factory, capacity=1)
    bodies = [
        _body(_payload(event.slug, "sub-capacity-a")),
        _body(_payload(event.slug, "sub-capacity-b")),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda body: harness.client.post(ENDPOINT, content=body, headers=_headers(body)),
                bodies,
            )
        )

    outcomes = sorted(response.json()["outcome"] for response in responses)
    assert outcomes == ["capacity_reached", "registered"]
    assert _count(harness.factory, Registration) == 1


@pytest.mark.parametrize(
    ("payload", "expected_submission_id"),
    [
        (
            {
                "event_slug": "event-x",
                "name": "A",
                "email": "a@example.com",
                "urn": "U",
                "attendance": "yes",
            },
            "sub-missing",
        ),
        (
            {
                "event_slug": "event-x",
                "submission_id": "sub-bad-email",
                "name": "A",
                "email": "not-an-email",
                "urn": "U",
                "attendance": "yes",
            },
            "sub-bad-email",
        ),
        (
            {
                "event_slug": "event-x",
                "submission_id": "sub-bad-attendance",
                "name": "A",
                "email": "a@example.com",
                "urn": "U",
                "attendance": "maybe",
            },
            "sub-bad-attendance",
        ),
        (
            {
                "event_slug": "event-x",
                "submission_id": "sub-empty-name",
                "name": "   ",
                "email": "a@example.com",
                "urn": "U",
                "attendance": "yes",
            },
            "sub-empty-name",
        ),
    ],
)
def test_validation_failures_are_recorded(
    harness: Harness, payload: dict[str, Any], expected_submission_id: str
) -> None:
    response = _post(harness.client, payload)
    if "submission_id" not in payload:
        expected_submission_id = hashlib.sha256(_body(payload)).hexdigest()

    assert response.status_code == 422
    assert response.json()["outcome"] == "rejected_validation"
    assert response.json()["submission_id"] == expected_submission_id
    assert _count(harness.factory, Registration) == 0
    ledger = _ledger(harness.factory, "event-x", expected_submission_id)
    assert ledger is not None
    assert ledger.outcome == WebhookOutcome.REJECTED
    assert ledger.error_code == "rejected_validation"


def test_malformed_json_is_recorded_without_personal_fields(harness: Harness) -> None:
    body = b'{"event_slug": "event-x", "email": "private@example.com"'
    headers = _headers(body)

    response = harness.client.post(ENDPOINT, content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["outcome"] == "rejected_validation"
    assert response.json()["submission_id"] == hashlib.sha256(body).hexdigest()
    ledger = _ledger(
        harness.factory,
        "_invalid",
        hashlib.sha256(body).hexdigest(),
    )
    assert ledger is not None
    assert "private@example.com" not in str(ledger.event_slug)
    assert "private@example.com" not in str(ledger.submission_id)


@pytest.mark.parametrize(
    ("overrides", "removals"),
    [
        (
            {},
            ["X-Webhook-Key-Id", "X-Webhook-Timestamp", "X-Webhook-Signature"],
        ),
        ({"X-Webhook-Signature": "0" * 64}, []),
    ],
)
def test_authentication_failures_are_rejected(
    harness: Harness, overrides: dict[str, str], removals: list[str]
) -> None:
    event = _create_event(harness.factory)
    body = _body(_payload(event.slug, f"sub-auth-{uuid4().hex[:8]}"))
    supplied = _headers(body)
    for header in removals:
        supplied.pop(header, None)
    supplied.update(overrides)

    response = harness.client.post(ENDPOINT, content=body, headers=supplied)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert _count(harness.factory, WebhookEvent) == 0


def test_expired_timestamp_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    body = _body(_payload(event.slug, "sub-expired"))
    timestamp = str(int(time.time()) - 600)
    headers = _headers(body, timestamp=timestamp)

    response = harness.client.post(ENDPOINT, content=body, headers=headers)

    assert response.status_code == 401
    assert _count(harness.factory, WebhookEvent) == 0


def test_unknown_key_id_is_rejected(harness: Harness) -> None:
    event = _create_event(harness.factory)
    body = _body(_payload(event.slug, "sub-unknown-key"))
    headers = _headers(body, key_id="v9")

    response = harness.client.post(ENDPOINT, content=body, headers=headers)

    assert response.status_code == 401
    assert _count(harness.factory, WebhookEvent) == 0


def test_processing_does_not_log_personal_data_or_signature(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _create_event(harness.factory)
    payload = _payload(
        event.slug,
        "sub-no-logging",
        email="private-person@example.com",
        phone="+1-555-0199",
        urn="PRIVATE-URN-123",
    )
    body = _body(payload)
    headers = _headers(body)

    response = harness.client.post(ENDPOINT, content=body, headers=headers)

    captured = capsys.readouterr()
    output = f"{captured.out}\n{captured.err}"
    assert response.status_code == 201
    assert payload["email"] not in output
    assert payload["phone"] not in output
    assert payload["urn"] not in output
    assert headers["X-Webhook-Signature"] not in output
    assert body.decode() not in output


def test_webhook_rate_limit_is_applied(
    migrated_postgres: Engine, postgres_engine_settings: Settings
) -> None:
    _truncate(migrated_postgres)
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    event = _create_event(factory)
    body = _body(_payload(event.slug, "sub-rate-limited"))

    with _make_client(postgres_engine_settings, webhook_rate_limit=1) as client:
        first = client.post(ENDPOINT, content=body, headers=_headers(body))
        second = client.post(ENDPOINT, content=body, headers=_headers(body))

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    _truncate(migrated_postgres)


def test_rollback_leaves_no_successful_ledger_record(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _create_event(harness.factory)
    payload = _payload(event.slug, "sub-rollback")
    body = _body(payload)
    request = RsvpWebhookRequest.model_validate(payload)

    def fail_on_ledger(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr(webhook_ingestion, "WebhookEvent", fail_on_ledger)
    with harness.factory() as session, pytest.raises(RuntimeError):
        webhook_ingestion.process_rsvp(session, request, body)

    assert _count(harness.factory, WebhookEvent) == 0
    assert _count(harness.factory, Registration) == 0
    assert _count(harness.factory, Attendee) == 0

    monkeypatch.undo()
    response = _post(harness.client, payload)
    assert response.status_code == 201
    assert _count(harness.factory, WebhookEvent) == 1
