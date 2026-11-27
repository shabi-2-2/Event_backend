"""PostgreSQL integration tests for transactional ticket and outbox issuance."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import resend
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import (
    Attendee,
    EligibilityRosterEntry,
    EmailDelivery,
    Event,
    Registration,
    Ticket,
    WebhookEvent,
)
from app.db.models.common import EmailDeliveryStatus, EmailPurpose, EventStatus
from app.main import create_app
from app.schemas.webhook import RsvpWebhookRequest
from app.security.ticket_tokens import derive_ticket_token, hash_ticket_token
from app.security.webhook import WEBHOOK_PATH
from app.services import webhook_ingestion

pytestmark = pytest.mark.postgres

ENDPOINT = "/api/v1/webhooks/google-forms"
SECRET = "phase5-ticket-test-secret"
TICKET_URN = "TICKET-ELIGIBLE-URN"
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
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    settings: Settings


def _truncate(engine: Engine) -> None:
    tables = ", ".join(_CLEANUP_TABLES)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def harness(migrated_postgres: Engine, postgres_engine_settings: Settings) -> Iterator[Harness]:
    _truncate(migrated_postgres)
    settings = postgres_engine_settings.model_copy(
        update={
            "webhook_signing_keys": {"v1": SecretStr(SECRET)},
            "webhook_rate_limit": 1000,
        }
    )
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    with TestClient(create_app(settings)) as client:
        yield Harness(client=client, factory=factory, settings=settings)
    _truncate(migrated_postgres)


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _headers(body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    message = f"{timestamp}.POST.{WEBHOOK_PATH}.".encode() + body
    signature = hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Key-Id": "v1",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": signature,
        "Content-Type": "application/json",
    }


def _post(client: TestClient, payload: dict[str, Any]) -> Response:
    body = _body(payload)
    return client.post(ENDPOINT, content=body, headers=_headers(body))


def _payload(submission_id: str) -> dict[str, Any]:
    suffix = uuid4().hex[:10]
    return {
        "event_slug": f"ticket-event-{suffix}",
        "submission_id": submission_id,
        "name": "Ada Lovelace",
        "email": f"ada-{suffix}@example.com",
        "phone": None,
        "urn": TICKET_URN,
        "attendance": "yes",
    }


def _create_event(factory: sessionmaker[Session], slug: str) -> Event:
    now = datetime.now(UTC)
    with factory() as session:
        event = Event(
            slug=slug,
            name="Ticket Test Event",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            timezone="UTC",
            status=EventStatus.PUBLISHED,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        session.add(EligibilityRosterEntry(event_id=event.id, normalized_urn=TICKET_URN))
        session.commit()
        return event


def _count(factory: sessionmaker[Session], model: Any) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_confirmed_registration_creates_one_ticket_and_pending_email(
    harness: Harness,
) -> None:
    payload = _payload("sub-ticket-create")
    _create_event(harness.factory, payload["event_slug"])

    response = _post(harness.client, payload)

    assert response.status_code == 201
    with harness.factory() as session:
        ticket = session.scalar(select(Ticket))
        assert ticket is not None
        assert len(ticket.token_hash) == 64
        assert ticket.token_hash != ticket.ticket_code
        assert ticket.status.value == "active"

        delivery = session.scalar(select(EmailDelivery))
        assert delivery is not None
        assert delivery.ticket_id == ticket.id
        assert delivery.purpose == EmailPurpose.TICKET_ISSUED
        assert delivery.status == EmailDeliveryStatus.PENDING
        assert delivery.attempts == 0
        assert delivery.provider_message_id is None

        raw_token = derive_ticket_token(
            ticket.ticket_code, harness.settings.ticket_token_derivation_key_value()
        )
        assert hash_ticket_token(raw_token) == ticket.token_hash
        stored_raw = session.execute(
            text("SELECT id FROM tickets WHERE ticket_code = :token OR token_hash = :token"),
            {"token": raw_token},
        ).first()
        assert stored_raw is None

    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1


def test_registration_does_not_call_resend(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload("sub-no-resend")
    _create_event(harness.factory, payload["event_slug"])

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Resend must only be called by the worker")

    monkeypatch.setattr(resend.Emails, "send", forbidden)

    response = _post(harness.client, payload)

    assert response.status_code == 201
    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1


def test_duplicate_webhook_does_not_duplicate_ticket_or_email(harness: Harness) -> None:
    payload = _payload("sub-ticket-duplicate")
    _create_event(harness.factory, payload["event_slug"])

    first = _post(harness.client, payload)
    second = _post(harness.client, payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["outcome"] == "duplicate_submission"
    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, WebhookEvent) == 1


def test_declined_rsvp_does_not_create_ticket(harness: Harness) -> None:
    payload = {**_payload("sub-ticket-declined"), "attendance": "no"}
    _create_event(harness.factory, payload["event_slug"])

    response = _post(harness.client, payload)

    assert response.status_code == 200
    assert _count(harness.factory, Ticket) == 0
    assert _count(harness.factory, EmailDelivery) == 0


def test_already_registered_without_ticket_is_backfilled_once(harness: Harness) -> None:
    payload = _payload("sub-ticket-backfill")
    event = _create_event(harness.factory, payload["event_slug"])
    with harness.factory() as session:
        attendee = Attendee(full_name=payload["name"], email=payload["email"], urn=payload["urn"])
        session.add(attendee)
        session.flush()
        session.add(
            Registration(
                event_id=event.id,
                attendee_id=attendee.id,
                source_submission_id="legacy-submission",
            )
        )
        session.commit()

    response = _post(harness.client, payload)
    assert response.status_code == 200
    assert response.json()["outcome"] == "already_registered"
    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1

    repeat = _post(harness.client, {**payload, "submission_id": "sub-ticket-backfill-2"})
    assert repeat.json()["outcome"] == "already_registered"
    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1


def test_failed_issuance_rolls_back_registration_ticket_and_email(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload("sub-ticket-rollback")
    _create_event(harness.factory, payload["event_slug"])
    request = RsvpWebhookRequest.model_validate(payload)

    def fail(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("simulated ticket failure")

    monkeypatch.setattr(webhook_ingestion, "issue_ticket_and_outbox", fail)
    with harness.factory() as session, pytest.raises(RuntimeError):
        webhook_ingestion.process_rsvp(
            session,
            request,
            _body(payload),
            derivation_key=harness.settings.ticket_token_derivation_key_value(),
        )

    assert _count(harness.factory, Registration) == 0
    assert _count(harness.factory, Ticket) == 0
    assert _count(harness.factory, EmailDelivery) == 0
    assert _count(harness.factory, WebhookEvent) == 0
