"""Ticket verification and atomic check-in domain logic."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.db.models import AuditLog, Checkin, Registration, Ticket
from app.db.models.common import (
    CheckinSource,
    RegistrationStatus,
    TicketStatus,
    utc_now,
)
from app.schemas.checkin import (
    CheckinOutcome,
    CheckinResponse,
    CheckinStatus,
    ScannerTicketInfo,
)
from app.security.ticket_tokens import hash_ticket_token

logger = get_logger(__name__)

_MESSAGES: dict[CheckinOutcome, str] = {
    CheckinOutcome.VALID_TICKET: "Ticket verified.",
    CheckinOutcome.CHECKED_IN: "Check-in confirmed.",
    CheckinOutcome.ALREADY_CHECKED_IN: "Ticket was already checked in.",
    CheckinOutcome.INVALID_TICKET: "Ticket is not valid for this event.",
    CheckinOutcome.REVOKED_TICKET: "Ticket has been revoked.",
    CheckinOutcome.EXPIRED_TICKET: "Ticket has expired.",
    CheckinOutcome.REGISTRATION_CANCELLED: "Registration is cancelled.",
    CheckinOutcome.INVALID_REGISTRATION_STATE: "Registration is not eligible for check-in.",
}

_SUCCESS_OUTCOMES = {
    CheckinOutcome.VALID_TICKET,
    CheckinOutcome.CHECKED_IN,
}


@contextmanager
def _request_transaction(session: Session) -> Iterator[None]:
    """Commit domain work in the same transaction used by the RBAC dependency.

    The request-scoped session has usually already begun a read transaction while
    resolving event membership. A savepoint keeps the domain work isolated, and
    the outer commit releases both it and those reads before the response is sent.
    No database lock is held after this context exits.
    """

    savepoint = session.begin_nested()
    try:
        yield
        savepoint.commit()
        session.commit()
    except Exception:
        if savepoint.is_active:
            savepoint.rollback()
        session.rollback()
        raise


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_expired(ticket: Ticket, *, now: datetime) -> bool:
    return ticket.expires_at is not None and _as_utc(ticket.expires_at) <= now


def _resolve_ticket(session: Session, token_hash: str, *, lock: bool) -> Ticket | None:
    statement = select(Ticket).where(Ticket.token_hash == token_hash)
    if lock and session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(of=Ticket)
    return session.scalar(statement)


def _lock_registration(session: Session, registration_id: UUID) -> Registration | None:
    statement = select(Registration).where(Registration.id == registration_id)
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(of=Registration)
    return session.scalar(statement)


def _existing_checkin(session: Session, ticket_id: UUID) -> Checkin | None:
    return session.scalar(select(Checkin).where(Checkin.ticket_id == ticket_id))


def _check_in_status(ticket: Ticket, checkin: Checkin | None) -> CheckinStatus:
    if (
        checkin is not None
        or ticket.status == TicketStatus.USED
        or ticket.registration.status == RegistrationStatus.CHECKED_IN
    ):
        return CheckinStatus.CHECKED_IN
    return CheckinStatus.PENDING


def _ticket_info(ticket: Ticket, checkin: Checkin | None) -> ScannerTicketInfo:
    return ScannerTicketInfo(
        attendee_name=ticket.registration.attendee.full_name,
        urn=ticket.registration.attendee.urn or "",
        ticket_status=ticket.status,
        registration_status=ticket.registration.status,
        check_in_status=_check_in_status(ticket, checkin),
    )


def _response(
    outcome: CheckinOutcome,
    *,
    ticket: Ticket | None = None,
    checkin: Checkin | None = None,
) -> CheckinResponse:
    ticket_info = (
        _ticket_info(ticket, checkin)
        if ticket is not None and outcome != CheckinOutcome.INVALID_TICKET
        else None
    )
    return CheckinResponse(
        success=outcome in _SUCCESS_OUTCOMES,
        outcome=outcome,
        message=_MESSAGES[outcome],
        ticket=ticket_info,
    )


def _evaluate(
    ticket: Ticket,
    registration: Registration,
    checkin: Checkin | None,
    *,
    event_id: UUID,
    now: datetime,
) -> CheckinOutcome | None:
    """Return the first controlled denial outcome, or None when eligible."""
    if registration.event_id != event_id:
        # Same response as an unknown token: do not disclose cross-event existence.
        return CheckinOutcome.INVALID_TICKET
    if ticket.status == TicketStatus.USED or checkin is not None:
        return CheckinOutcome.ALREADY_CHECKED_IN
    if registration.status == RegistrationStatus.CANCELLED:
        # Administrative cancellation also revokes the ticket. Prefer the
        # registration-level outcome so cancelled attendees get a clear denial.
        return CheckinOutcome.REGISTRATION_CANCELLED
    if ticket.status == TicketStatus.REVOKED:
        return CheckinOutcome.REVOKED_TICKET
    if ticket.status == TicketStatus.EXPIRED or _is_expired(ticket, now=now):
        return CheckinOutcome.EXPIRED_TICKET
    if ticket.status != TicketStatus.ACTIVE or registration.status != RegistrationStatus.REGISTERED:
        return CheckinOutcome.INVALID_REGISTRATION_STATE
    return None


def _safe_context(outcome: CheckinOutcome, station: str | None) -> dict[str, str]:
    context = {"outcome": outcome.value}
    if station:
        context["station"] = station
    return context


def _audit(
    session: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    ticket: Ticket,
    action: str,
    outcome: CheckinOutcome,
    station: str | None,
) -> None:
    session.add(
        AuditLog(
            event_id=event_id,
            actor_user_id=user_id,
            action=action,
            target_type="ticket",
            target_id=str(ticket.id),
            context=_safe_context(outcome, station),
        )
    )


def verify_ticket(session: Session, *, event_id: UUID, ticket_token: str) -> CheckinResponse:
    """Verify a ticket without mutating any domain record."""
    token_hash = hash_ticket_token(ticket_token)
    now = utc_now()
    with _request_transaction(session):
        ticket = _resolve_ticket(session, token_hash, lock=False)
        if ticket is None:
            return _response(CheckinOutcome.INVALID_TICKET)
        registration = ticket.registration
        checkin = _existing_checkin(session, ticket.id)
        denial = _evaluate(ticket, registration, checkin, event_id=event_id, now=now)
        outcome = denial or CheckinOutcome.VALID_TICKET
        return _response(outcome, ticket=ticket, checkin=checkin)


def confirm_checkin(
    session: Session,
    *,
    event_id: UUID,
    ticket_token: str,
    station: str | None,
    user_id: UUID,
) -> CheckinResponse:
    """Atomically create a check-in and update ticket/registration/audit state."""
    token_hash = hash_ticket_token(ticket_token)
    now = utc_now()
    with _request_transaction(session):
        ticket = _resolve_ticket(session, token_hash, lock=True)
        if ticket is None:
            return _response(CheckinOutcome.INVALID_TICKET)

        registration = _lock_registration(session, ticket.registration_id)
        if registration is None:
            return _response(CheckinOutcome.INVALID_TICKET)

        checkin = _existing_checkin(session, ticket.id)
        denial = _evaluate(ticket, registration, checkin, event_id=event_id, now=now)
        if denial is not None:
            if denial != CheckinOutcome.INVALID_TICKET:
                _audit(
                    session,
                    event_id=event_id,
                    user_id=user_id,
                    ticket=ticket,
                    action="checkin.denied",
                    outcome=denial,
                    station=station,
                )
            return _response(denial, ticket=ticket, checkin=checkin)

        created = Checkin(
            ticket_id=ticket.id,
            registration_id=registration.id,
            event_id=event_id,
            checked_in_at=now,
            scanned_by=user_id,
            station=station,
            source=CheckinSource.MOBILE,
            metadata_={"station": station} if station else {},
        )
        session.add(created)
        ticket.status = TicketStatus.USED
        ticket.used_at = now
        registration.status = RegistrationStatus.CHECKED_IN
        registration.checked_in_at = now
        _audit(
            session,
            event_id=event_id,
            user_id=user_id,
            ticket=ticket,
            action="checkin.confirmed",
            outcome=CheckinOutcome.CHECKED_IN,
            station=station,
        )
        session.flush()
        log_event(
            logger,
            logging.INFO,
            "checkin_confirmed",
            event_id=str(event_id),
            actor_user_id=str(user_id),
        )
        return _response(CheckinOutcome.CHECKED_IN, ticket=ticket, checkin=created)
