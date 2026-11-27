"""Ticket token utility tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Attendee, Event, Registration, Ticket
from app.security.ticket_tokens import (
    generate_ticket_token,
    hash_ticket_token,
    verify_ticket_token,
)


def test_generated_tokens_are_unique_and_url_safe(db_session: Session) -> None:
    tokens = [generate_ticket_token() for _ in range(100)]

    assert len(set(tokens)) == 100
    assert all(len(token) >= 43 for token in tokens)
    assert all(token.isascii() for token in tokens)
    assert all("=" not in token for token in tokens)


def test_token_hash_is_deterministic_sha256_hex() -> None:
    token = generate_ticket_token()
    digest = hash_ticket_token(token)

    assert digest == hash_ticket_token(token)
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    assert token not in digest


def test_verify_ticket_token_uses_hashed_comparison() -> None:
    token = generate_ticket_token()
    digest = hash_ticket_token(token)

    assert verify_ticket_token(token, digest)
    assert verify_ticket_token(token, digest.upper())
    assert not verify_ticket_token(token, hash_ticket_token(generate_ticket_token()))
    assert not verify_ticket_token("", digest)
    assert not verify_ticket_token(token, "")


def test_raw_token_is_not_persisted(db_session: Session) -> None:
    event = Event(
        slug=f"token-event-{uuid4().hex[:8]}",
        name="Token Event",
        starts_at=datetime(2026, 8, 1, 9, tzinfo=UTC),
        ends_at=datetime(2026, 8, 1, 18, tzinfo=UTC),
        timezone="UTC",
    )
    attendee = Attendee(
        full_name="Token Attendee",
        email=f"token-{uuid4().hex[:8]}@example.com",
        urn=f"URN-{uuid4().hex[:8]}",
    )
    db_session.add_all([event, attendee])
    db_session.flush()
    registration = Registration(
        event_id=event.id,
        attendee_id=attendee.id,
        source_submission_id=f"token-sub-{uuid4().hex}",
    )
    db_session.add(registration)
    db_session.flush()

    raw_token = generate_ticket_token()
    token_hash = hash_ticket_token(raw_token)
    ticket = Ticket(
        registration_id=registration.id,
        token_hash=token_hash,
        ticket_code=f"TICKET-{uuid4().hex[:8]}",
    )
    db_session.add(ticket)
    db_session.commit()

    stored_rows = db_session.execute(
        select(Ticket.token_hash, Ticket.ticket_code).where(Ticket.id == ticket.id)
    ).all()
    assert stored_rows == [(token_hash, ticket.ticket_code)]
    assert all(raw_token not in str(cell) for row in stored_rows for cell in row)
