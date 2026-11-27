"""Transactional ticket issuance and initial ticket-email outbox creation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmailDelivery, Ticket
from app.db.models.common import EmailDeliveryStatus, EmailPurpose
from app.security.ticket_tokens import (
    derive_ticket_token,
    generate_ticket_reference,
    hash_ticket_token,
)


def issue_ticket_and_outbox(
    session: Session,
    registration_id: UUID,
    *,
    derivation_key: str,
) -> bool:
    """Ensure a registration has exactly one ticket and one initial email job.

    Returns ``True`` when a new ticket was created, ``False`` when the
    registration already had one. The raw derived token exists only in memory
    long enough to compute its SHA-256 digest.
    """
    existing = session.scalar(select(Ticket).where(Ticket.registration_id == registration_id))
    if existing is not None:
        return False

    ticket_reference = generate_ticket_reference()
    raw_token = derive_ticket_token(ticket_reference, derivation_key)
    token_hash = hash_ticket_token(raw_token)
    del raw_token

    ticket = Ticket(
        registration_id=registration_id,
        token_hash=token_hash,
        ticket_code=ticket_reference,
    )
    session.add(ticket)
    session.flush()

    pending_email = session.scalar(
        select(EmailDelivery).where(
            EmailDelivery.ticket_id == ticket.id,
            EmailDelivery.purpose == EmailPurpose.TICKET_ISSUED,
        )
    )
    if pending_email is None:
        session.add(
            EmailDelivery(
                registration_id=registration_id,
                ticket_id=ticket.id,
                purpose=EmailPurpose.TICKET_ISSUED,
                status=EmailDeliveryStatus.PENDING,
                attempts=0,
                next_attempt_at=None,
            )
        )
    session.flush()
    return True
