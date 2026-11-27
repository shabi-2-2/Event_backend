"""Registration administration, including safe cancellation policy."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Attendee, Checkin, Registration, Ticket
from app.db.models.common import RegistrationStatus, TicketStatus, utc_now
from app.schemas.admin import (
    CheckinFilterStatus,
    Page,
    RegistrationResponse,
)
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

_RegistrationRow = tuple[Any, Any, Any, Any]


def _base_statement(event_id: UUID) -> Any:
    return (
        select(Registration, Attendee, Ticket, Checkin)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .outerjoin(Ticket, Ticket.registration_id == Registration.id)
        .outerjoin(Checkin, Checkin.ticket_id == Ticket.id)
        .where(Registration.event_id == event_id)
    )


def _response(row: _RegistrationRow) -> RegistrationResponse:
    registration, attendee, ticket, checkin = row
    return RegistrationResponse(
        registration_reference=attendee.urn or "",
        attendee_reference=attendee.urn or "",
        attendee_name=attendee.full_name,
        email=attendee.email,
        phone=attendee.phone,
        registration_status=registration.status,
        registered_at=as_utc(registration.registered_at),
        checked_in_at=as_utc(registration.checked_in_at) if registration.checked_in_at else None,
        cancelled_at=as_utc(registration.cancelled_at) if registration.cancelled_at else None,
        ticket_reference=ticket.ticket_code if ticket else None,
        ticket_status=ticket.status if ticket else None,
        check_in_status=(
            CheckinFilterStatus.CHECKED_IN if checkin else CheckinFilterStatus.PENDING
        ),
        check_in_at=as_utc(checkin.checked_in_at) if checkin else None,
        station=checkin.station if checkin else None,
    )


def list_registrations(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
    reference: str | None,
    name: str | None,
    email: str | None,
    registration_status: RegistrationStatus | None,
    ticket_status: TicketStatus | None,
    check_in_status: CheckinFilterStatus | None,
) -> Page[RegistrationResponse]:
    """Return a paginated registration listing with safe filters."""

    statement = _base_statement(event_id)
    if reference:
        statement = statement.where(
            func.upper(func.coalesce(Attendee.urn, "")) == reference.strip().upper()
        )
    if name:
        statement = statement.where(Attendee.full_name.ilike(like_term(name), escape="\\"))
    if email:
        statement = statement.where(Attendee.email.ilike(like_term(email), escape="\\"))
    if registration_status is not None:
        statement = statement.where(Registration.status == registration_status)
    if ticket_status is not None:
        statement = statement.where(Ticket.status == ticket_status)
    if check_in_status == CheckinFilterStatus.CHECKED_IN:
        statement = statement.where(Checkin.id.is_not(None))
    elif check_in_status == CheckinFilterStatus.PENDING:
        statement = statement.where(Checkin.id.is_(None))
    statement = statement.order_by(Registration.registered_at.desc(), Registration.id.asc())

    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[RegistrationResponse](
        items=[_response((row[0], row[1], row[2], row[3])) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_registration(
    session: Session,
    *,
    event_id: UUID,
    registration_reference: str,
) -> RegistrationResponse:
    """Return one registration scoped to the event."""

    statement = _base_statement(event_id).where(
        func.upper(func.coalesce(Attendee.urn, "")) == registration_reference.strip().upper()
    )
    row = session.execute(statement).first()
    if row is None:
        raise not_found()
    return _response((row[0], row[1], row[2], row[3]))


def cancel_registration(
    session: Session,
    *,
    event_id: UUID,
    registration_reference: str,
    actor_user_id: UUID,
) -> RegistrationResponse:
    """Cancel a registration and revoke its active ticket atomically.

    Checked-in registrations are never silently reverted. Duplicate cancellation
    is idempotent and creates no additional audit record.
    """

    normalized = registration_reference.strip().upper()
    with mutation_transaction(session):
        registration = session.scalar(
            select(Registration)
            .where(
                Registration.event_id == event_id,
                func.upper(Attendee.urn) == normalized,
            )
            .join(Attendee, Attendee.id == Registration.attendee_id)
        )
        if registration is None:
            raise not_found()

        locked_ticket = session.scalar(
            with_row_lock(
                select(Ticket).where(Ticket.registration_id == registration.id),
                session,
                Ticket,
            )
        )
        locked_registration = session.scalar(
            with_row_lock(
                select(Registration).where(Registration.id == registration.id),
                session,
                Registration,
            )
        )
        if locked_registration is None:
            raise not_found()
        existing_checkin = session.scalar(
            select(Checkin).where(
                Checkin.event_id == event_id,
                Checkin.registration_id == locked_registration.id,
            )
        )
        if locked_registration.status == RegistrationStatus.CANCELLED:
            return _response(
                (
                    locked_registration,
                    session.get(Attendee, locked_registration.attendee_id),  # type: ignore[arg-type]
                    locked_ticket,
                    existing_checkin,
                )
            )
        if (
            locked_registration.status == RegistrationStatus.CHECKED_IN
            or existing_checkin is not None
            or (locked_ticket is not None and locked_ticket.status == TicketStatus.USED)
        ):
            raise conflict(
                "Checked-in registrations cannot be cancelled; attendance history is preserved."
            )

        previous_status = locked_registration.status
        now = utc_now()
        locked_registration.status = RegistrationStatus.CANCELLED
        locked_registration.cancelled_at = now
        if locked_ticket is not None and locked_ticket.status == TicketStatus.ACTIVE:
            locked_ticket.status = TicketStatus.REVOKED
            locked_ticket.revoked_at = now
            ticket_revoked = True
        else:
            ticket_revoked = False
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="registration.cancelled",
            target_type="registration",
            target_id=str(locked_registration.id),
            context={
                "from_status": previous_status.value,
                "to_status": RegistrationStatus.CANCELLED.value,
                "ticket_revoked": ticket_revoked,
            },
        )
        session.flush()
        response_row = (
            locked_registration,
            session.get(Attendee, locked_registration.attendee_id),  # type: ignore[arg-type]
            locked_ticket,
            None,
        )

    log_admin_action("registration.cancelled", event_id=event_id, actor_user_id=actor_user_id)
    return _response(response_row)
