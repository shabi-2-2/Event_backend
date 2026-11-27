"""PostgreSQL tests for safe outbox claiming, retries, and worker recovery."""

from __future__ import annotations

import base64
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Attendee, EmailDelivery, Event, Registration, Ticket
from app.db.models.common import (
    EmailDeliveryStatus,
    EmailPurpose,
    EventStatus,
    RegistrationStatus,
    TicketStatus,
)
from app.security.ticket_tokens import (
    derive_ticket_token,
    generate_ticket_reference,
    hash_ticket_token,
)
from app.services.email_gateway import EmailDeliveryError, TicketEmailPayload
from app.workers.email_worker import claim_jobs, process_job

pytestmark = pytest.mark.postgres

KEY = "phase5-worker-derivation-key-with-sufficient-length"
_CLEANUP_TABLES = (
    "checkins",
    "tickets",
    "email_deliveries",
    "registrations",
    "attendees",
    "events",
    "rate_limit_counters",
)


@dataclass
class RecordingGateway:
    """Test double that captures the exact payload sent to the provider."""

    payloads: list[TicketEmailPayload]
    fail: bool = False
    message_id: str = "msg_test_123"

    def send_ticket_email(self, payload: TicketEmailPayload) -> str:
        if self.fail:
            raise EmailDeliveryError("resend_test_error")
        self.payloads.append(payload)
        return self.message_id


@dataclass(frozen=True)
class JobSetup:
    delivery_id: UUID
    ticket_code: str
    attendee_email: str


@pytest.fixture
def factory(migrated_postgres: Engine) -> Iterator[sessionmaker[Session]]:
    tables = ", ".join(_CLEANUP_TABLES)
    with migrated_postgres.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)
    with migrated_postgres.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def worker_settings(postgres_engine_settings: Settings) -> Settings:
    return postgres_engine_settings.model_copy(
        update={
            "ticket_token_derivation_key": SecretStr(KEY),
            "email_worker_max_attempts": 3,
            "email_worker_lease_seconds": 10,
            "email_retry_backoff_initial_seconds": 60,
            "email_retry_backoff_multiplier": 1.0,
            "email_retry_backoff_max_seconds": 60,
            "email_worker_poll_interval_seconds": 0.01,
        }
    )


def _create_job(factory: sessionmaker[Session]) -> JobSetup:
    suffix = uuid4().hex[:10]
    now = datetime.now(UTC)
    with factory() as session:
        event = Event(
            slug=f"worker-event-{suffix}",
            name="Worker Test Event",
            description="A test gathering",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            timezone="UTC",
            venue="Main Hall",
            status=EventStatus.PUBLISHED,
        )
        attendee = Attendee(
            full_name="Grace Hopper",
            email=f"grace-{suffix}@example.com",
            urn=f"URN-{suffix}",
        )
        session.add_all((event, attendee))
        session.flush()
        registration = Registration(
            event_id=event.id,
            attendee_id=attendee.id,
            source_submission_id=f"sub-{suffix}",
            status=RegistrationStatus.REGISTERED,
        )
        session.add(registration)
        session.flush()

        ticket_code = generate_ticket_reference()
        raw_token = derive_ticket_token(ticket_code, KEY)
        ticket = Ticket(
            registration_id=registration.id,
            token_hash=hash_ticket_token(raw_token),
            ticket_code=ticket_code,
            status=TicketStatus.ACTIVE,
        )
        session.add(ticket)
        session.flush()
        delivery = EmailDelivery(
            registration_id=registration.id,
            ticket_id=ticket.id,
            purpose=EmailPurpose.TICKET_ISSUED,
            status=EmailDeliveryStatus.PENDING,
            attempts=0,
            next_attempt_at=None,
        )
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        return JobSetup(
            delivery_id=delivery.id,
            ticket_code=ticket_code,
            attendee_email=attendee.email,
        )


def _job_count(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(EmailDelivery)) or 0)


def _delivery(factory: sessionmaker[Session], delivery_id: UUID) -> EmailDelivery:
    with factory() as session:
        delivery = session.get(EmailDelivery, delivery_id)
        assert delivery is not None
        session.refresh(delivery)
        return delivery


def _claim(
    factory: sessionmaker[Session],
    settings: Settings,
    now: datetime,
) -> list[UUID]:
    jobs = claim_jobs(
        factory,
        now=now,
        batch_size=settings.email_worker_batch_size,
        max_attempts=settings.email_worker_max_attempts,
        lease_seconds=settings.email_worker_lease_seconds,
    )
    return [job.delivery_id for job in jobs]


def test_successful_delivery_marks_job_sent_with_idempotency_key(
    factory: sessionmaker[Session], worker_settings: Settings
) -> None:
    setup = _create_job(factory)
    now = datetime.now(UTC)
    jobs = claim_jobs(
        factory,
        now=now,
        batch_size=10,
        max_attempts=3,
        lease_seconds=60,
    )
    assert len(jobs) == 1
    gateway = RecordingGateway(payloads=[])

    process_job(factory, jobs[0], gateway, worker_settings, now=now)

    delivery = _delivery(factory, setup.delivery_id)
    assert delivery.status == EmailDeliveryStatus.SENT
    assert delivery.provider_message_id == "msg_test_123"
    assert delivery.sent_at is not None
    assert delivery.error_code is None
    assert delivery.next_attempt_at is None
    assert delivery.attempts == 1

    assert len(gateway.payloads) == 1
    payload = gateway.payloads[0]
    assert payload.to_email == setup.attendee_email
    assert payload.idempotency_key == f"ticket-email:{setup.delivery_id}"
    assert base64.b64decode(payload.qr_base64).startswith(b"\x89PNG")
    raw_token = derive_ticket_token(
        setup.ticket_code, worker_settings.ticket_token_derivation_key_value()
    )
    assert raw_token not in payload.html
    assert raw_token not in payload.text
    assert "Worker Test Event" in payload.html
    assert "Grace Hopper" in payload.html


def test_failed_delivery_retries_then_dead_letters(
    factory: sessionmaker[Session], worker_settings: Settings
) -> None:
    setup = _create_job(factory)
    gateway = RecordingGateway(payloads=[], fail=True)
    start = datetime.now(UTC)

    for expected_attempt, claim_time in enumerate(
        (start, start + timedelta(seconds=61), start + timedelta(seconds=122)),
        start=1,
    ):
        jobs = claim_jobs(
            factory,
            now=claim_time,
            batch_size=10,
            max_attempts=3,
            lease_seconds=10,
        )
        assert len(jobs) == 1
        assert jobs[0].attempts == expected_attempt
        process_job(factory, jobs[0], gateway, worker_settings, now=claim_time)

    delivery = _delivery(factory, setup.delivery_id)
    assert delivery.status == EmailDeliveryStatus.DEAD_LETTER
    assert delivery.attempts == 3
    assert delivery.error_code == "resend_test_error"
    assert delivery.next_attempt_at is None
    assert delivery.provider_message_id is None
    assert gateway.payloads == []

    no_jobs = _claim(factory, worker_settings, start + timedelta(days=1))
    assert no_jobs == []


def test_concurrent_workers_cannot_claim_the_same_job(
    factory: sessionmaker[Session], worker_settings: Settings
) -> None:
    setup = _create_job(factory)
    now = datetime.now(UTC)
    stop = threading.Event()

    def claim() -> list[UUID]:
        return _claim(factory, worker_settings, now)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    claimed = [delivery_id for result in results for delivery_id in result]
    assert claimed.count(setup.delivery_id) == 1
    assert len(claimed) == 1
    stop.set()


def test_interrupted_job_recovers_after_lease_expiry(
    factory: sessionmaker[Session], worker_settings: Settings
) -> None:
    setup = _create_job(factory)
    start = datetime.now(UTC)

    first = _claim(factory, worker_settings, start)
    assert first == [setup.delivery_id]
    assert _claim(factory, worker_settings, start) == []

    recovered = _claim(factory, worker_settings, start + timedelta(seconds=11))
    assert recovered == [setup.delivery_id]
    assert _delivery(factory, setup.delivery_id).attempts == 2
    assert _job_count(factory) == 1
