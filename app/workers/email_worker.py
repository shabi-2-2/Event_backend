"""Separately executed ticket-email worker with a database-backed outbox.

Jobs are claimed in a short transaction using ``FOR UPDATE SKIP LOCKED`` on
PostgreSQL. The row lease is committed before Resend is called, so no database
row lock is held during network I/O. Interrupted jobs become eligible again
when their lease expires.
"""

from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.logging import configure_logging, get_logger, log_event
from app.db.models import Attendee, EmailDelivery, Event, Registration, Ticket
from app.db.models.common import EmailDeliveryStatus, EmailPurpose
from app.db.session import create_db_engine, create_session_factory
from app.security.ticket_tokens import derive_ticket_token
from app.services.email_gateway import (
    EmailDeliveryError,
    ResendEmailGateway,
    TicketEmailPayload,
    TicketEmailSender,
)
from app.services.ticket_email import TicketEmailContext, render_ticket_email
from app.services.ticket_qr import generate_ticket_qr_png, qr_png_to_base64

logger = get_logger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    """Detached snapshot of a claimed outbox row."""

    delivery_id: UUID
    to_email: str
    ticket_code: str
    context: TicketEmailContext
    attempts: int


@dataclass(frozen=True)
class DeliveryOutcome:
    """Final state written back to the outbox."""

    status: EmailDeliveryStatus
    error_code: str | None
    provider_message_id: str | None


def _retry_delay(settings: Settings, attempts: int) -> timedelta:
    exponent = max(0, attempts - 1)
    delay = settings.email_retry_backoff_initial_seconds * (
        settings.email_retry_backoff_multiplier**exponent
    )
    return timedelta(seconds=min(delay, settings.email_retry_backoff_max_seconds))


def claim_jobs(
    session_factory: sessionmaker[Session],
    *,
    now: datetime,
    batch_size: int,
    max_attempts: int,
    lease_seconds: int,
) -> list[ClaimedJob]:
    """Atomically claim eligible jobs and commit a short visibility lease."""
    statement = (
        select(EmailDelivery, Ticket, Registration, Attendee, Event)
        .join(Ticket, Ticket.id == EmailDelivery.ticket_id)
        .join(Registration, Registration.id == EmailDelivery.registration_id)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .join(Event, Event.id == Registration.event_id)
        .where(
            EmailDelivery.status.in_((EmailDeliveryStatus.PENDING, EmailDeliveryStatus.FAILED)),
            EmailDelivery.purpose == EmailPurpose.TICKET_ISSUED,
            or_(
                EmailDelivery.next_attempt_at.is_(None),
                EmailDelivery.next_attempt_at <= now,
            ),
            EmailDelivery.attempts < max_attempts,
        )
        .order_by(EmailDelivery.created_at, EmailDelivery.id)
        .limit(batch_size)
    )

    with session_factory() as session:
        with session.begin():
            bind = session.get_bind()
            if bind.dialect.name == "postgresql":
                statement = statement.with_for_update(of=EmailDelivery, skip_locked=True)
            rows = session.execute(statement).all()
            claimed: list[ClaimedJob] = []
            for delivery, ticket, _registration, attendee, event in rows:
                delivery.attempts += 1
                delivery.next_attempt_at = now + timedelta(seconds=lease_seconds)
                claimed.append(
                    ClaimedJob(
                        delivery_id=delivery.id,
                        to_email=attendee.email,
                        ticket_code=ticket.ticket_code,
                        attempts=delivery.attempts,
                        context=TicketEmailContext(
                            attendee_name=attendee.full_name,
                            event_name=event.name,
                            event_description=event.description,
                            starts_at=event.starts_at,
                            ends_at=event.ends_at,
                            timezone_name=event.timezone,
                            venue=event.venue,
                            ticket_code=ticket.ticket_code,
                        ),
                    )
                )
            session.flush()
        return claimed


def finalize_delivery(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    outcome: DeliveryOutcome,
    *,
    now: datetime,
    settings: Settings,
) -> None:
    """Write a terminal or retryable result in a fresh transaction."""
    with session_factory() as session, session.begin():
        delivery = session.get(EmailDelivery, job.delivery_id)
        if delivery is None:
            return
        # Another worker may have finalized first after a lease expiry.
        if delivery.status in (
            EmailDeliveryStatus.SENT,
            EmailDeliveryStatus.DEAD_LETTER,
        ):
            return
        delivery.status = outcome.status
        delivery.error_code = outcome.error_code
        delivery.provider_message_id = outcome.provider_message_id
        if outcome.status == EmailDeliveryStatus.SENT:
            delivery.sent_at = now
            delivery.next_attempt_at = None
        elif outcome.status == EmailDeliveryStatus.DEAD_LETTER:
            delivery.next_attempt_at = None
        else:
            delivery.next_attempt_at = now + _retry_delay(settings, job.attempts)


def process_job(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    gateway: TicketEmailSender,
    settings: Settings,
    *,
    now: datetime,
) -> DeliveryOutcome:
    """Derive the raw token in memory, render the QR, and send via Resend."""
    raw_token = derive_ticket_token(job.ticket_code, settings.ticket_token_derivation_key_value())
    qr_png = generate_ticket_qr_png(raw_token)
    del raw_token
    html_body, text_body = render_ticket_email(job.context)
    payload = TicketEmailPayload(
        to_email=job.to_email,
        subject=f"Your ticket for {job.context.event_name}",
        html=html_body,
        text=text_body,
        qr_base64=qr_png_to_base64(qr_png),
        idempotency_key=f"ticket-email:{job.delivery_id}",
    )

    try:
        message_id = gateway.send_ticket_email(payload)
    except EmailDeliveryError as exc:
        if job.attempts >= settings.email_worker_max_attempts:
            outcome = DeliveryOutcome(
                status=EmailDeliveryStatus.DEAD_LETTER,
                error_code=exc.code,
                provider_message_id=None,
            )
            log_event(
                logger,
                logging.ERROR,
                "email_job_dead_letter",
                delivery_id=str(job.delivery_id),
                attempts=job.attempts,
                error_code=exc.code,
            )
        else:
            outcome = DeliveryOutcome(
                status=EmailDeliveryStatus.FAILED,
                error_code=exc.code,
                provider_message_id=None,
            )
            log_event(
                logger,
                logging.WARNING,
                "email_job_failed",
                delivery_id=str(job.delivery_id),
                attempts=job.attempts,
                error_code=exc.code,
            )
    else:
        outcome = DeliveryOutcome(
            status=EmailDeliveryStatus.SENT,
            error_code=None,
            provider_message_id=message_id,
        )
        log_event(
            logger,
            logging.INFO,
            "email_job_sent",
            delivery_id=str(job.delivery_id),
            attempts=job.attempts,
        )

    finalize_delivery(session_factory, job, outcome, now=now, settings=settings)
    return outcome


def run_worker(
    settings: Settings,
    session_factory: sessionmaker[Session],
    gateway: TicketEmailSender,
    stop_event: threading.Event | None = None,
) -> None:
    """Run the polling loop until a shutdown signal is received."""
    stop = stop_event or threading.Event()
    while not stop.is_set():
        now = datetime.now(UTC)
        jobs = claim_jobs(
            session_factory,
            now=now,
            batch_size=settings.email_worker_batch_size,
            max_attempts=settings.email_worker_max_attempts,
            lease_seconds=settings.email_worker_lease_seconds,
        )
        for job in jobs:
            if stop.is_set():
                break
            log_event(
                logger,
                logging.INFO,
                "email_job_claimed",
                delivery_id=str(job.delivery_id),
                attempts=job.attempts,
            )
            process_job(session_factory, job, gateway, settings, now=datetime.now(UTC))
        if not jobs and not stop.is_set():
            stop.wait(settings.email_worker_poll_interval_seconds)


def main() -> None:
    """Console entry point for the separate email worker process."""
    from app.core.config import get_settings

    settings = get_settings()
    configure_logging(settings)
    gateway = ResendEmailGateway(settings)
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    stop_event = threading.Event()

    def handle_signal(signum: int, frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log_event(logger, logging.INFO, "email_worker_started")
    try:
        run_worker(settings, session_factory, gateway, stop_event)
    finally:
        engine.dispose()
        log_event(logger, logging.INFO, "email_worker_stopped")


if __name__ == "__main__":
    main()
