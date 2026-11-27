"""Outbox monitoring and safe administrative retries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Attendee, EmailDelivery, Registration, Ticket
from app.db.models.common import EmailDeliveryStatus, EmailPurpose
from app.schemas.admin import EmailDeliveryResponse, EmailRetryResponse, Page
from app.services.admin_common import (
    add_audit,
    as_utc,
    conflict,
    like_term,
    log_admin_action,
    mutation_transaction,
    not_found,
    paginate,
    require_aware,
    with_row_lock,
)

_EmailRow = tuple[Any, Any, Any, Any]


def _base_statement(event_id: UUID) -> Any:
    return (
        select(EmailDelivery, Registration, Attendee, Ticket)
        .join(Registration, Registration.id == EmailDelivery.registration_id)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .join(Ticket, Ticket.id == EmailDelivery.ticket_id)
        .where(Registration.event_id == event_id)
    )


def _response(row: _EmailRow) -> EmailDeliveryResponse:
    delivery, registration, attendee, ticket = row
    return EmailDeliveryResponse(
        delivery_reference=delivery.id,
        registration_reference=attendee.urn or "",
        ticket_reference=ticket.ticket_code,
        purpose=delivery.purpose,
        status=delivery.status,
        attempts=delivery.attempts,
        resend_sequence=delivery.resend_sequence,
        error_code=delivery.error_code,
        next_attempt_at=as_utc(delivery.next_attempt_at) if delivery.next_attempt_at else None,
        created_at=as_utc(delivery.created_at),
        sent_at=as_utc(delivery.sent_at) if delivery.sent_at else None,
    )


def list_deliveries(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
    status: EmailDeliveryStatus | None,
    registration_reference: str | None,
    ticket_reference: str | None,
    min_attempts: int | None,
    max_attempts: int | None,
    error_code: str | None,
    next_attempt_before: datetime | None,
    next_attempt_after: datetime | None,
) -> Page[EmailDeliveryResponse]:
    """Return a paginated outbox view with safe operational filters."""

    require_aware(next_attempt_before, field="next_attempt_before")
    require_aware(next_attempt_after, field="next_attempt_after")
    if min_attempts is not None and max_attempts is not None and max_attempts < min_attempts:
        raise conflict("max_attempts must not be less than min_attempts.")

    statement = _base_statement(event_id)
    if status is not None:
        statement = statement.where(EmailDelivery.status == status)
    if registration_reference:
        statement = statement.where(
            func.upper(func.coalesce(Attendee.urn, "")) == registration_reference.strip().upper()
        )
    if ticket_reference:
        statement = statement.where(
            Ticket.ticket_code.ilike(like_term(ticket_reference), escape="\\")
        )
    if min_attempts is not None:
        statement = statement.where(EmailDelivery.attempts >= min_attempts)
    if max_attempts is not None:
        statement = statement.where(EmailDelivery.attempts <= max_attempts)
    if error_code:
        statement = statement.where(
            EmailDelivery.error_code.ilike(like_term(error_code), escape="\\")
        )
    if next_attempt_before is not None:
        statement = statement.where(EmailDelivery.next_attempt_at <= next_attempt_before)
    if next_attempt_after is not None:
        statement = statement.where(EmailDelivery.next_attempt_at >= next_attempt_after)
    statement = statement.order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.asc())

    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[EmailDeliveryResponse](
        items=[_response((row[0], row[1], row[2], row[3])) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def retry_delivery(
    session: Session,
    *,
    event_id: UUID,
    delivery_reference: UUID,
    actor_user_id: UUID,
) -> EmailRetryResponse:
    """Queue a fresh job and suppress retries of the old failed job.

    The original delivery record is preserved: its attempt count and error code
    are never reset. A failed old job is moved to ``dead_letter`` so the worker
    cannot deliver the same ticket twice.
    """

    with mutation_transaction(session):
        delivery = session.scalar(
            with_row_lock(
                select(EmailDelivery).where(EmailDelivery.id == delivery_reference),
                session,
                EmailDelivery,
            )
        )
        if delivery is None or delivery.registration.event_id != event_id:
            raise not_found("Email delivery was not found for this event.")
        previous_status = delivery.status
        if previous_status not in (
            EmailDeliveryStatus.FAILED,
            EmailDeliveryStatus.DEAD_LETTER,
        ):
            raise conflict("Only failed or dead-letter deliveries can be retried.")

        other_active = session.scalar(
            select(EmailDelivery.id).where(
                EmailDelivery.ticket_id == delivery.ticket_id,
                EmailDelivery.id != delivery.id,
                EmailDelivery.status.in_((EmailDeliveryStatus.PENDING, EmailDeliveryStatus.FAILED)),
            )
        )
        if other_active is not None:
            raise conflict(
                "Another delivery job is already active for this ticket.",
                code="RESEND_ALREADY_PENDING",
            )

        next_sequence = int(
            session.scalar(
                select(func.coalesce(func.max(EmailDelivery.resend_sequence), 0) + 1).where(
                    EmailDelivery.ticket_id == delivery.ticket_id,
                    EmailDelivery.purpose == EmailPurpose.TICKET_ISSUED,
                )
            )
            or 1
        )
        # Suppress the old job without clearing its history.
        delivery.next_attempt_at = None
        if previous_status == EmailDeliveryStatus.FAILED:
            delivery.status = EmailDeliveryStatus.DEAD_LETTER
        replacement = EmailDelivery(
            registration_id=delivery.registration_id,
            ticket_id=delivery.ticket_id,
            purpose=EmailPurpose.TICKET_ISSUED,
            status=EmailDeliveryStatus.PENDING,
            attempts=0,
            resend_sequence=next_sequence,
            next_attempt_at=None,
        )
        session.add(replacement)
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="email_retry.queued",
            target_type="email_delivery",
            target_id=str(delivery.id),
            context={
                "previous_status": previous_status.value,
                "sequence": next_sequence,
            },
        )
        session.flush()
        response = EmailRetryResponse(
            delivery_reference=replacement.id,
            registration_reference=delivery.registration.attendee.urn or "",
            ticket_reference=delivery.ticket.ticket_code,
            status=replacement.status,
            resend_sequence=replacement.resend_sequence,
            previous_status=previous_status,
            message="A replacement delivery job was queued for the worker.",
        )

    log_admin_action("email_retry.queued", event_id=event_id, actor_user_id=actor_user_id)
    return response
