"""Portable SQLAlchemy model, relationship, and constraint tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Attendee,
    AuditLog,
    Checkin,
    EmailDelivery,
    Event,
    Registration,
    StaffMembership,
    Ticket,
    WebhookEvent,
)
from app.db.models.common import EmailPurpose, StaffRole, WebhookOutcome

_START = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
_END = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)


def make_event(**overrides: object) -> Event:
    values: dict[str, object] = {
        "slug": f"event-{uuid4().hex[:10]}",
        "name": "Test Event",
        "starts_at": _START,
        "ends_at": _END,
        "timezone": "UTC",
    }
    values.update(overrides)
    return Event(**values)  # type: ignore[arg-type]


def make_attendee(**overrides: object) -> Attendee:
    token = uuid4().hex[:10]
    values: dict[str, object] = {
        "full_name": "Test Attendee",
        "email": f"attendee-{token}@example.com",
        "urn": f"URN-{token}",
    }
    values.update(overrides)
    return Attendee(**values)  # type: ignore[arg-type]


def expect_integrity_error(session: Session) -> None:
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def base_registration(session: Session) -> tuple[Event, Attendee, Registration]:
    event = make_event()
    attendee = make_attendee()
    session.add_all([event, attendee])
    session.flush()
    registration = Registration(
        event_id=event.id,
        attendee_id=attendee.id,
        source_submission_id=f"sub-{uuid4().hex}",
    )
    session.add(registration)
    session.flush()
    return event, attendee, registration


def make_ticket(registration: Registration, *, suffix: str = "1") -> Ticket:
    return Ticket(
        registration_id=registration.id,
        token_hash=uuid4().hex + suffix,
        ticket_code=f"TICKET-{uuid4().hex[:10]}-{suffix}",
    )


def test_model_creation_uuids_and_relationships(db_session: Session) -> None:
    event = make_event()
    attendee = make_attendee()
    db_session.add_all([event, attendee])
    db_session.flush()

    registration = Registration(
        event_id=event.id,
        attendee_id=attendee.id,
        source_submission_id="sub-relationship-1",
    )
    db_session.add(registration)
    db_session.flush()

    ticket = make_ticket(registration)
    db_session.add(ticket)
    db_session.flush()

    checkin = Checkin(
        ticket_id=ticket.id,
        registration_id=registration.id,
        event_id=event.id,
        station="gate-1",
        metadata_={"attempt": 1},
    )
    email_delivery = EmailDelivery(
        registration_id=registration.id,
        ticket_id=ticket.id,
        purpose=EmailPurpose.TICKET_ISSUED,
    )
    webhook_event = WebhookEvent(
        source="google_forms",
        event_slug=event.slug,
        submission_id="sub-relationship-1",
        payload_hash="a" * 64,
        outcome=WebhookOutcome.REGISTERED,
    )
    membership = StaffMembership(user_id=uuid4(), event_id=event.id, role=StaffRole.CHECKIN)
    audit_log = AuditLog(
        event_id=event.id,
        action="test.action",
        target_type="registration",
        target_id=str(registration.id),
        context={"rows": 1},
    )
    db_session.add_all([checkin, email_delivery, webhook_event, membership, audit_log])
    db_session.flush()

    for entity in (
        event,
        attendee,
        registration,
        ticket,
        checkin,
        email_delivery,
        webhook_event,
        audit_log,
    ):
        assert isinstance(entity.id, UUID)

    assert registration.event is event
    assert registration.attendee is attendee
    assert registration.ticket is ticket
    assert ticket.registration is registration
    assert ticket.checkin is checkin
    assert checkin.ticket is ticket
    assert email_delivery.registration is registration
    assert webhook_event.event is event
    assert membership.event is event
    assert audit_log.event is event

    assert event.registrations == [registration]
    assert event.staff_memberships == [membership]
    assert event.audit_logs == [audit_log]
    assert attendee.registrations == [registration]
    assert registration.email_deliveries == [email_delivery]


def test_email_and_urn_are_normalized(db_session: Session) -> None:
    attendee = make_attendee(email="  ADA.Lovelace@Example.COM ", urn="  urn-42  ")
    db_session.add(attendee)
    db_session.flush()

    assert attendee.email == "ada.lovelace@example.com"
    assert attendee.urn == "URN-42"


def test_global_urn_uniqueness(db_session: Session) -> None:
    db_session.add_all(
        [
            make_attendee(urn="URN-100"),
            make_attendee(urn=" urn-100 ", email="different@example.com"),
        ]
    )
    expect_integrity_error(db_session)


def test_global_email_uniqueness(db_session: Session) -> None:
    db_session.add_all(
        [
            make_attendee(email="Same@Example.com", urn="URN-EMAIL-1"),
            make_attendee(email="same@example.com", urn="URN-EMAIL-2"),
        ]
    )
    expect_integrity_error(db_session)


def test_null_urns_are_allowed_for_future_external_attendees(
    db_session: Session,
) -> None:
    db_session.add_all([make_attendee(urn=None), make_attendee(urn=None)])
    db_session.flush()


def test_duplicate_registration_for_same_event_and_attendee_is_rejected(
    db_session: Session,
) -> None:
    event, attendee, registration = base_registration(db_session)
    duplicate = Registration(
        event_id=event.id,
        attendee_id=attendee.id,
        source_submission_id=f"different-{registration.source_submission_id}",
    )
    db_session.add(duplicate)
    expect_integrity_error(db_session)


def test_duplicate_submission_for_same_event_is_rejected(db_session: Session) -> None:
    event, _, registration = base_registration(db_session)
    other_attendee = make_attendee()
    db_session.add(other_attendee)
    db_session.flush()
    duplicate = Registration(
        event_id=event.id,
        attendee_id=other_attendee.id,
        source_submission_id=registration.source_submission_id,
    )
    db_session.add(duplicate)
    expect_integrity_error(db_session)


def test_one_ticket_per_registration(db_session: Session) -> None:
    _, _, registration = base_registration(db_session)
    db_session.add(make_ticket(registration))
    db_session.flush()
    db_session.add(make_ticket(registration, suffix="2"))
    expect_integrity_error(db_session)


def test_one_checkin_per_ticket(db_session: Session) -> None:
    event, _, registration = base_registration(db_session)
    ticket = make_ticket(registration)
    db_session.add(ticket)
    db_session.flush()

    db_session.add(
        Checkin(
            ticket_id=ticket.id,
            registration_id=registration.id,
            event_id=event.id,
        )
    )
    db_session.flush()
    db_session.add(
        Checkin(
            ticket_id=ticket.id,
            registration_id=registration.id,
            event_id=event.id,
            station="second-scan",
        )
    )
    expect_integrity_error(db_session)


def test_email_outbox_uniqueness_per_ticket_and_purpose(db_session: Session) -> None:
    _, _, registration = base_registration(db_session)
    ticket = make_ticket(registration)
    db_session.add(ticket)
    db_session.flush()

    db_session.add(
        EmailDelivery(
            registration_id=registration.id,
            ticket_id=ticket.id,
            purpose=EmailPurpose.TICKET_ISSUED,
        )
    )
    db_session.flush()
    db_session.add(
        EmailDelivery(
            registration_id=registration.id,
            ticket_id=ticket.id,
            purpose=EmailPurpose.TICKET_ISSUED,
        )
    )
    expect_integrity_error(db_session)


def test_webhook_event_idempotency_constraints(db_session: Session) -> None:
    def webhook(*, submission_id: str, request_id: str | None) -> WebhookEvent:
        return WebhookEvent(
            source="google_forms",
            event_slug="event-constraints",
            submission_id=submission_id,
            request_id=request_id,
            payload_hash="b" * 64,
            outcome=WebhookOutcome.REGISTERED,
        )

    db_session.add(webhook(submission_id="sub-1", request_id="req-1"))
    db_session.flush()

    db_session.add(webhook(submission_id="sub-1", request_id="req-2"))
    expect_integrity_error(db_session)

    # The rollback removed the baseline row, so restore it before the next case.
    db_session.add(webhook(submission_id="sub-1", request_id="req-1"))
    db_session.flush()
    db_session.add(webhook(submission_id="sub-2", request_id="req-1"))
    expect_integrity_error(db_session)

    db_session.add_all(
        [
            webhook(submission_id="sub-3", request_id=None),
            webhook(submission_id="sub-4", request_id=None),
        ]
    )
    db_session.flush()


def test_jsonb_fields_round_trip(db_session: Session) -> None:
    event, _, registration = base_registration(db_session)
    ticket = make_ticket(registration)
    db_session.add(ticket)
    db_session.flush()

    checkin = Checkin(
        ticket_id=ticket.id,
        registration_id=registration.id,
        event_id=event.id,
        metadata_={"station": "gate-2", "scan_attempt": 2},
    )
    audit_log = AuditLog(
        event_id=event.id,
        action="attendees.export",
        target_type="event",
        context={"format": "csv", "row_count": 2},
    )
    db_session.add_all([checkin, audit_log])
    db_session.commit()
    checkin_id = checkin.id
    audit_id = audit_log.id
    db_session.expunge_all()

    loaded_checkin = db_session.get(Checkin, checkin_id)
    loaded_audit = db_session.get(AuditLog, audit_id)
    assert loaded_checkin is not None
    assert loaded_audit is not None
    assert loaded_checkin.metadata_ == {"station": "gate-2", "scan_attempt": 2}
    assert loaded_audit.context == {"format": "csv", "row_count": 2}


def test_timestamps_are_populated(db_session: Session) -> None:
    event, _, registration = base_registration(db_session)
    ticket = make_ticket(registration)
    db_session.add(ticket)
    db_session.flush()

    checkin = Checkin(
        ticket_id=ticket.id,
        registration_id=registration.id,
        event_id=event.id,
    )
    audit_log = AuditLog(
        event_id=event.id,
        action="test.timestamp",
        target_type="ticket",
    )
    membership = StaffMembership(user_id=uuid4(), event_id=event.id, role=StaffRole.VIEWER)
    webhook_event = WebhookEvent(
        source="google_forms",
        event_slug=event.slug,
        submission_id="sub-timestamp",
        payload_hash="c" * 64,
        outcome=WebhookOutcome.IGNORED_DECLINED,
    )
    db_session.add_all([checkin, audit_log, membership, webhook_event])
    db_session.flush()

    assert event.created_at is not None
    assert event.updated_at is not None
    assert event.updated_at >= event.created_at
    assert registration.registered_at is not None
    assert ticket.issued_at is not None
    assert checkin.checked_in_at is not None
    assert audit_log.created_at is not None
    assert membership.created_at is not None
    assert webhook_event.received_at is not None
