"""Ticket listing, revocation, and outbox-only resend operations."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Attendee, Checkin, EmailDelivery, Registration, Ticket
from app.db.models.common import (
    EmailDeliveryStatus,
    EmailPurpose,
    RegistrationStatus,
    TicketStatus,
    utc_now,
)
from app.schemas.admin import Page, TicketResendResponse, TicketResponse
from app.services.admin_common import (
    add_audit,
    as_utc,
    conflict,
    like_term,
    log_admin_action,
    mutation_transaction,
    not_found,
    paginate,
    with_row_lock,
)

_TicketRow = tuple[Ticket, Registration, Attendee, Checkin | None]


def _base_statement(event_id: UUID) -> Any:
    return (
        select(Ticket, Registration, Attendee, Checkin)
        .join(Registration, Registration.id == Ticket.registration_id)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .outerjoin(Checkin, Checkin.ticket_id == Ticket.id)
        .where(Registration.event_id == event_id)
    )


def _response(row: _TicketRow) -> TicketResponse:
    ticket, registration, attendee, checkin = row
    return TicketResponse(
        ticket_reference=ticket.ticket_code,
        attendee_reference=attendee.urn or "",
        attendee_name=attendee.full_name,
        registration_status=registration.status,
        ticket_status=ticket.status,
        issued_at=as_utc(ticket.issued_at),
        expires_at=as_utc(ticket.expires_at) if ticket.expires_at else None,
        used_at=as_utc(ticket.used_at) if ticket.used_at else None,
        revoked_at=as_utc(ticket.revoked_at) if ticket.revoked_at else None,
        check_in_at=as_utc(checkin.checked_in_at) if checkin else None,
    )


def list_tickets(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
    ticket_status: TicketStatus | None,
    reference: str | None,
) -> Page[TicketResponse]:
    """Return a paginated ticket listing without credentials or hashes."""

    statement = _base_statement(event_id)
    if ticket_status is not None:
        statement = statement.where(Ticket.status == ticket_status)
    if reference:
        statement = statement.where(Ticket.ticket_code.ilike(like_term(reference), escape="\\"))
    statement = statement.order_by(Ticket.issued_at.desc(), Ticket.ticket_code.asc())
    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[TicketResponse](
        items=[_response(tuple(row)) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def _locked_ticket(session: Session, event_id: UUID, reference: str) -> Ticket:
    ticket = session.scalar(
        with_row_lock(
            select(Ticket).where(Ticket.ticket_code == reference.strip()), session, Ticket
        )
    )
    if ticket is None or ticket.registration.event_id != event_id:
        raise not_found("Ticket was not found for this event.")
    return cast(Ticket, ticket)


def revoke_ticket(
    session: Session,
    *,
    event_id: UUID,
    ticket_reference: str,
    actor_user_id: UUID,
) -> TicketResponse:
    """Revoke an active ticket atomically; repeated revocation is idempotent."""

    with mutation_transaction(session):
        ticket = _locked_ticket(session, event_id, ticket_reference)
        existing_checkin = session.scalar(select(Checkin).where(Checkin.ticket_id == ticket.id))
        if ticket.status == TicketStatus.REVOKED:
            response_row = _ticket_row(session, ticket, existing_checkin)
        else:
            if (
                ticket.status == TicketStatus.USED
                or ticket.status == TicketStatus.EXPIRED
                or existing_checkin is not None
            ):
                raise conflict(
                    "Only active tickets can be revoked; used, expired, and checked-in "
                    "tickets are immutable."
                )
            previous = ticket.status
            ticket.status = TicketStatus.REVOKED
            ticket.revoked_at = utc_now()
            add_audit(
                session,
                event_id=event_id,
                actor_user_id=actor_user_id,
                action="ticket.revoked",
                target_type="ticket",
                target_id=str(ticket.id),
                context={
                    "from_status": previous.value,
                    "to_status": TicketStatus.REVOKED.value,
                },
            )
            session.flush()
            response_row = _ticket_row(session, ticket, existing_checkin)

    log_admin_action("ticket.revoked", event_id=event_id, actor_user_id=actor_user_id)
    return _response(response_row)


def _ticket_row(session: Session, ticket: Ticket, checkin: Checkin | None) -> _TicketRow:
    registration = session.get(Registration, ticket.registration_id)
    attendee = session.get(Attendee, registration.attendee_id) if registration is not None else None
    if registration is None or attendee is None:
        raise not_found("Ticket was not found for this event.")
    return ticket, registration, attendee, checkin


def resend_ticket(
    session: Session,
    *,
    event_id: UUID,
    ticket_reference: str,
    actor_user_id: UUID,
) -> TicketResendResponse:
    """Queue a new ticket-email job without calling Resend or regenerating a ticket."""

    with mutation_transaction(session):
        ticket = _locked_ticket(session, event_id, ticket_reference)
        registration = ticket.registration
        if registration.status == RegistrationStatus.CANCELLED:
            raise conflict("Ticket email cannot be resent for a cancelled registration.")
        if ticket.status != TicketStatus.ACTIVE:
            raise conflict("Ticket email can only be resent while the ticket is active.")

        active_job = session.scalar(
            select(EmailDelivery).where(
                EmailDelivery.ticket_id == ticket.id,
                EmailDelivery.purpose == EmailPurpose.TICKET_ISSUED,
                EmailDelivery.status.in_((EmailDeliveryStatus.PENDING, EmailDeliveryStatus.FAILED)),
            )
        )
        if active_job is not None:
            raise conflict(
                "An email delivery job is still active for this ticket.",
                code="RESEND_ALREADY_PENDING",
            )

        next_sequence = int(
            session.scalar(
                select(func.coalesce(func.max(EmailDelivery.resend_sequence), 0) + 1).where(
                    EmailDelivery.ticket_id == ticket.id,
                    EmailDelivery.purpose == EmailPurpose.TICKET_ISSUED,
                )
            )
            or 1
        )
        delivery = EmailDelivery(
            registration_id=registration.id,
            ticket_id=ticket.id,
            purpose=EmailPurpose.TICKET_ISSUED,
            status=EmailDeliveryStatus.PENDING,
            attempts=0,
            resend_sequence=next_sequence,
            next_attempt_at=None,
        )
        session.add(delivery)
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="ticket.resend_queued",
            target_type="ticket",
            target_id=str(ticket.id),
            context={
                "sequence": next_sequence,
                "purpose": EmailPurpose.TICKET_ISSUED.value,
            },
        )
        session.flush()
        delivery_id = delivery.id

    log_admin_action("ticket.resend_queued", event_id=event_id, actor_user_id=actor_user_id)
    return TicketResendResponse(
        ticket_reference=ticket.ticket_code,
        delivery_reference=delivery_id,
        status=EmailDeliveryStatus.PENDING,
        resend_sequence=next_sequence,
        message="Ticket email resend queued for the worker.",
    )
