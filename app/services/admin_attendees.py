"""Event attendee listing and detail queries with role-specific privacy."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Attendee, Checkin, Registration, Ticket
from app.db.models.common import RegistrationStatus, StaffRole, TicketStatus
from app.schemas.admin import (
    AdminAttendeeResponse,
    AttendeeSortField,
    CheckinFilterStatus,
    Page,
    SortOrder,
    ViewerAttendeeResponse,
)
from app.services.admin_common import as_utc, like_term, not_found, paginate

_AttendeeRow = tuple[Any, Any, Any, Any]


def _base_statement(event_id: UUID) -> Any:
    return (
        select(Registration, Attendee, Ticket, Checkin)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .outerjoin(Ticket, Ticket.registration_id == Registration.id)
        .outerjoin(Checkin, Checkin.ticket_id == Ticket.id)
        .where(Registration.event_id == event_id)
    )


def _checkin_status(checkin: Checkin | None) -> CheckinFilterStatus:
    return CheckinFilterStatus.CHECKED_IN if checkin is not None else CheckinFilterStatus.PENDING


def _admin_response(row: _AttendeeRow) -> AdminAttendeeResponse:
    registration, attendee, ticket, checkin = row
    return AdminAttendeeResponse(
        attendee_reference=attendee.urn or "",
        full_name=attendee.full_name,
        urn=attendee.urn or "",
        email=attendee.email,
        phone=attendee.phone,
        registration_reference=attendee.urn or "",
        registration_status=registration.status,
        registered_at=as_utc(registration.registered_at),
        checked_in_at=as_utc(registration.checked_in_at) if registration.checked_in_at else None,
        cancelled_at=as_utc(registration.cancelled_at) if registration.cancelled_at else None,
        ticket_reference=ticket.ticket_code if ticket else None,
        ticket_status=ticket.status if ticket else None,
        ticket_expires_at=as_utc(ticket.expires_at) if ticket and ticket.expires_at else None,
        ticket_used_at=as_utc(ticket.used_at) if ticket and ticket.used_at else None,
        check_in_status=_checkin_status(checkin),
        check_in_at=as_utc(checkin.checked_in_at) if checkin else None,
        station=checkin.station if checkin else None,
    )


def _viewer_response(row: _AttendeeRow) -> ViewerAttendeeResponse:
    registration, attendee, ticket, checkin = row
    return ViewerAttendeeResponse(
        attendee_reference=attendee.urn or "",
        full_name=attendee.full_name,
        urn=attendee.urn or "",
        registration_status=registration.status,
        ticket_status=ticket.status if ticket else None,
        check_in_status=_checkin_status(checkin),
        checked_in_at=as_utc(registration.checked_in_at) if registration.checked_in_at else None,
    )


def list_attendees(
    session: Session,
    *,
    event_id: UUID,
    role: StaffRole,
    page: int,
    page_size: int,
    search: str | None,
    urn: str | None,
    email_search: str | None,
    registration_status: RegistrationStatus | None,
    ticket_status: TicketStatus | None,
    check_in_status: CheckinFilterStatus | None,
    sort_by: AttendeeSortField,
    sort_order: SortOrder,
) -> Page[AdminAttendeeResponse] | Page[ViewerAttendeeResponse]:
    """Return a filtered attendee page using the caller's privacy schema."""

    if email_search is not None and role != StaffRole.ADMIN:
        raise AppError(
            status_code=403,
            code="FORBIDDEN",
            message="Email search is restricted to event administrators.",
        )

    statement = _base_statement(event_id)
    if search:
        pattern = like_term(search)
        statement = statement.where(
            or_(
                Attendee.full_name.ilike(pattern, escape="\\"),
                func.coalesce(Attendee.urn, "").ilike(pattern, escape="\\"),
            )
        )
    if urn:
        statement = statement.where(
            func.upper(func.coalesce(Attendee.urn, "")) == urn.strip().upper()
        )
    if email_search:
        statement = statement.where(Attendee.email.ilike(like_term(email_search), escape="\\"))
    if registration_status is not None:
        statement = statement.where(Registration.status == registration_status)
    if ticket_status is not None:
        statement = statement.where(Ticket.status == ticket_status)
    if check_in_status == CheckinFilterStatus.CHECKED_IN:
        statement = statement.where(Checkin.id.is_not(None))
    elif check_in_status == CheckinFilterStatus.PENDING:
        statement = statement.where(Checkin.id.is_(None))

    sort_column = (
        Attendee.full_name if sort_by == AttendeeSortField.NAME else Registration.registered_at
    )
    ordered = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
    statement = statement.order_by(ordered, Registration.id.asc())

    rows, total = paginate(session, statement, page=page, page_size=page_size)
    typed_rows = [tuple(row) for row in rows]
    if role == StaffRole.ADMIN:
        return Page[AdminAttendeeResponse](
            items=[_admin_response(row) for row in typed_rows],
            page=page,
            page_size=page_size,
            total=total,
        )
    return Page[ViewerAttendeeResponse](
        items=[_viewer_response(row) for row in typed_rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_attendee(
    session: Session,
    *,
    event_id: UUID,
    attendee_reference: str,
    role: StaffRole,
) -> AdminAttendeeResponse | ViewerAttendeeResponse:
    """Return one attendee scoped to the event, or a generic 404."""

    normalized = attendee_reference.strip().upper()
    statement = _base_statement(event_id).where(
        func.upper(func.coalesce(Attendee.urn, "")) == normalized
    )
    row = session.execute(statement).first()
    if row is None:
        raise not_found()
    typed_row: _AttendeeRow = tuple(row)  # type: ignore[assignment]
    if role == StaffRole.ADMIN:
        return _admin_response(typed_row)
    return _viewer_response(typed_row)
