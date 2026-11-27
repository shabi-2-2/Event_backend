"""Transactional Google Forms RSVP ingestion.

The route layer remains thin: it authenticates, rate-limits, parses JSON, and
delegates all domain decisions here. Every outcome is recorded in the existing
``webhook_events`` ledger inside the same transaction as any attendee or
registration change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Attendee, Event, Registration, WebhookEvent
from app.db.models.common import EventStatus, RegistrationStatus, WebhookOutcome
from app.schemas.webhook import AttendanceValue, RsvpWebhookRequest, WebhookOutcomeCode
from app.services.eligibility import is_eligible
from app.services.ticket_issuance import issue_ticket_and_outbox

SOURCE = "google_forms"
_INVALID_EVENT_SLUG = "_invalid"

_DB_OUTCOME: dict[WebhookOutcomeCode, WebhookOutcome] = {
    WebhookOutcomeCode.REGISTERED: WebhookOutcome.REGISTERED,
    WebhookOutcomeCode.DECLINED: WebhookOutcome.IGNORED_DECLINED,
    WebhookOutcomeCode.DUPLICATE_SUBMISSION: WebhookOutcome.DUPLICATE,
    WebhookOutcomeCode.ALREADY_REGISTERED: WebhookOutcome.DUPLICATE,
    WebhookOutcomeCode.REJECTED_VALIDATION: WebhookOutcome.REJECTED,
    WebhookOutcomeCode.EVENT_UNAVAILABLE: WebhookOutcome.REJECTED,
    WebhookOutcomeCode.CAPACITY_REACHED: WebhookOutcome.REJECTED,
    WebhookOutcomeCode.IDENTITY_CONFLICT: WebhookOutcome.REJECTED,
    WebhookOutcomeCode.INELIGIBLE: WebhookOutcome.REJECTED,
}

_MESSAGES: dict[WebhookOutcomeCode, str] = {
    WebhookOutcomeCode.REGISTERED: "RSVP registered.",
    WebhookOutcomeCode.DECLINED: "Declined RSVP recorded.",
    WebhookOutcomeCode.DUPLICATE_SUBMISSION: "Submission already processed.",
    WebhookOutcomeCode.ALREADY_REGISTERED: "Attendee is already registered for this event.",
    WebhookOutcomeCode.REJECTED_VALIDATION: "Submission validation failed.",
    WebhookOutcomeCode.EVENT_UNAVAILABLE: "Event is not accepting registrations.",
    WebhookOutcomeCode.CAPACITY_REACHED: "Event registration capacity has been reached.",
    WebhookOutcomeCode.IDENTITY_CONFLICT: "Submitted identity conflicts with an existing attendee.",
    WebhookOutcomeCode.INELIGIBLE: "Submission is not eligible for this event.",
}

_ACTIVE_REGISTRATION_STATUSES = (
    RegistrationStatus.REGISTERED,
    RegistrationStatus.CHECKED_IN,
)


@dataclass(frozen=True)
class WebhookProcessingResult:
    """A safe result that can be mapped directly to an HTTP response.

    ``eligible`` is internal metadata used by controlled reconciliation. It is
    ``None`` when the roster was not reached (for example a duplicate delivery
    or an unavailable event), so it never becomes an API response field.
    """

    outcome: WebhookOutcomeCode
    submission_id: str
    message: str
    success: bool
    eligible: bool | None = None


def payload_hash(raw_body: bytes) -> str:
    """Return the deterministic digest stored in the webhook ledger."""
    return hashlib.sha256(raw_body).hexdigest()


def _result(
    outcome: WebhookOutcomeCode,
    submission_id: str,
    *,
    eligible: bool | None = None,
) -> WebhookProcessingResult:
    return WebhookProcessingResult(
        outcome=outcome,
        submission_id=submission_id,
        message=_MESSAGES[outcome],
        success=outcome
        in {
            WebhookOutcomeCode.REGISTERED,
            WebhookOutcomeCode.DECLINED,
            WebhookOutcomeCode.DUPLICATE_SUBMISSION,
            WebhookOutcomeCode.ALREADY_REGISTERED,
        },
        eligible=eligible,
    )


def _safe_string(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(char for char in value.strip() if char.isprintable())
    return cleaned[:max_length]


def _ledger_identity(parsed: object, raw_body: bytes) -> tuple[str, str]:
    """Extract ledger keys without ever deriving them from personal fields."""
    digest = payload_hash(raw_body)
    if not isinstance(parsed, dict):
        return _INVALID_EVENT_SLUG, digest
    event_slug = _safe_string(parsed.get("event_slug"), 100) or _INVALID_EVENT_SLUG
    submission_id = _safe_string(parsed.get("submission_id"), 128) or digest
    return event_slug, submission_id


def _find_ledger(session: Session, event_slug: str, submission_id: str) -> WebhookEvent | None:
    return session.scalar(
        select(WebhookEvent).where(
            WebhookEvent.source == SOURCE,
            WebhookEvent.event_slug == event_slug,
            WebhookEvent.submission_id == submission_id,
        )
    )


def _lock_submission(session: Session, event_slug: str, submission_id: str) -> None:
    """Serialize same-submission deliveries on PostgreSQL.

    The ledger unique constraint remains the final safeguard; this advisory lock
    makes the common duplicate path deterministic instead of relying on an
    IntegrityError race.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    material = f"{SOURCE}:{event_slug}:{submission_id}".encode()
    key = int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _get_event(session: Session, event_slug: str) -> Event | None:
    statement = select(Event).where(Event.slug == event_slug)
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return session.scalar(statement)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_accepting_registrations(event: Event, *, now: datetime) -> bool:
    if event.status != EventStatus.PUBLISHED:
        return False
    if event.registration_opens_at is not None and now < _as_utc(event.registration_opens_at):
        return False
    return not (
        event.registration_closes_at is not None and now > _as_utc(event.registration_closes_at)
    )


def _is_at_capacity(session: Session, event: Event) -> bool:
    if event.capacity is None:
        return False
    active_count = (
        session.scalar(
            select(func.count())
            .select_from(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status.in_(_ACTIVE_REGISTRATION_STATUSES),
            )
        )
        or 0
    )
    return active_count >= event.capacity


@dataclass(frozen=True)
class _AttendeeResolution:
    attendee: Attendee | None
    created: bool


def _resolve_attendee(session: Session, request: RsvpWebhookRequest) -> _AttendeeResolution | None:
    """Return an existing matching attendee or create one; None means conflict."""
    by_email = session.scalar(select(Attendee).where(Attendee.email == str(request.email)))
    by_urn = session.scalar(select(Attendee).where(Attendee.urn == request.urn))

    if by_email is not None and by_urn is not None and by_email.id != by_urn.id:
        return None
    if by_email is not None and by_email.urn != request.urn:
        return None
    if by_urn is not None and by_urn.email != str(request.email):
        return None

    if by_email is not None:
        return _AttendeeResolution(attendee=by_email, created=False)
    if by_urn is not None:
        return _AttendeeResolution(attendee=by_urn, created=False)

    attendee = Attendee(
        full_name=request.name,
        email=str(request.email),
        phone=request.phone,
        urn=request.urn,
    )
    session.add(attendee)
    session.flush()
    return _AttendeeResolution(attendee=attendee, created=True)


def _existing_registration(
    session: Session, event_id: object, attendee_id: object, submission_id: str
) -> Registration | None:
    return session.scalar(
        select(Registration).where(
            or_(
                and_(
                    Registration.event_id == event_id,
                    Registration.attendee_id == attendee_id,
                ),
                and_(
                    Registration.event_id == event_id,
                    Registration.source_submission_id == submission_id,
                ),
            )
        )
    )


def _record_ledger(
    session: Session,
    *,
    event_slug: str,
    submission_id: str,
    digest: str,
    outcome: WebhookOutcomeCode,
) -> None:
    error_code = (
        None
        if outcome
        in {
            WebhookOutcomeCode.REGISTERED,
            WebhookOutcomeCode.DECLINED,
            WebhookOutcomeCode.DUPLICATE_SUBMISSION,
        }
        else outcome.value
    )
    session.add(
        WebhookEvent(
            source=SOURCE,
            event_slug=event_slug,
            submission_id=submission_id,
            request_id=None,
            payload_hash=digest,
            outcome=_DB_OUTCOME[outcome],
            error_code=error_code,
        )
    )
    session.flush()


def _record_and_return(
    session: Session,
    *,
    event_slug: str,
    submission_id: str,
    digest: str,
    outcome: WebhookOutcomeCode,
    eligible: bool | None = None,
) -> WebhookProcessingResult:
    _record_ledger(
        session,
        event_slug=event_slug,
        submission_id=submission_id,
        digest=digest,
        outcome=outcome,
    )
    return _result(outcome, submission_id, eligible=eligible)


def _process_new_submission(
    session: Session,
    request: RsvpWebhookRequest,
    digest: str,
    *,
    derivation_key: str,
) -> WebhookProcessingResult:
    event_slug = request.event_slug
    submission_id = request.submission_id
    now = datetime.now(UTC)

    _lock_submission(session, event_slug, submission_id)
    existing = _find_ledger(session, event_slug, submission_id)
    if existing is not None:
        return _result(WebhookOutcomeCode.DUPLICATE_SUBMISSION, submission_id)

    event = _get_event(session, event_slug)
    if event is None or not _is_accepting_registrations(event, now=now):
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.EVENT_UNAVAILABLE,
        )

    # Eligibility is enforced here, inside the webhook transaction and before
    # declined handling, capacity accounting, attendee creation, registration,
    # and ticket issuance. The backend roster is the only authority.
    eligible = is_eligible(session, event.id, request.urn)
    if not eligible:
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.INELIGIBLE,
            eligible=False,
        )

    if request.attendance == AttendanceValue.NO:
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.DECLINED,
            eligible=True,
        )

    if _is_at_capacity(session, event):
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.CAPACITY_REACHED,
            eligible=True,
        )

    resolution = _resolve_attendee(session, request)
    if resolution is None or resolution.attendee is None:
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.IDENTITY_CONFLICT,
            eligible=True,
        )

    attendee = resolution.attendee
    existing_registration = _existing_registration(session, event.id, attendee.id, submission_id)
    if existing_registration is not None:
        # Backfill tickets for registrations created before Phase 5 without
        # issuing a second ticket for registrations that already have one.
        issue_ticket_and_outbox(session, existing_registration.id, derivation_key=derivation_key)
        return _record_and_return(
            session,
            event_slug=event_slug,
            submission_id=submission_id,
            digest=digest,
            outcome=WebhookOutcomeCode.ALREADY_REGISTERED,
            eligible=True,
        )

    registration = Registration(
        event_id=event.id,
        attendee_id=attendee.id,
        source_submission_id=submission_id,
        status=RegistrationStatus.REGISTERED,
    )
    session.add(registration)
    session.flush()
    issue_ticket_and_outbox(session, registration.id, derivation_key=derivation_key)
    return _record_and_return(
        session,
        event_slug=event_slug,
        submission_id=submission_id,
        digest=digest,
        outcome=WebhookOutcomeCode.REGISTERED,
        eligible=True,
    )


def _resolve_post_conflict(
    session: Session,
    request: RsvpWebhookRequest,
    digest: str,
    *,
    derivation_key: str,
) -> WebhookProcessingResult:
    """Re-read committed state after a constraint race and record a safe outcome."""
    event_slug = request.event_slug
    submission_id = request.submission_id
    try:
        with session.begin():
            _lock_submission(session, event_slug, submission_id)
            if _find_ledger(session, event_slug, submission_id) is not None:
                return _result(WebhookOutcomeCode.DUPLICATE_SUBMISSION, submission_id)

            event = _get_event(session, event_slug)
            now = datetime.now(UTC)
            eligible: bool | None = None
            if event is None or not _is_accepting_registrations(event, now=now):
                outcome = WebhookOutcomeCode.EVENT_UNAVAILABLE
            else:
                eligible = is_eligible(session, event.id, request.urn)
                if not eligible:
                    outcome = WebhookOutcomeCode.INELIGIBLE
                elif request.attendance == AttendanceValue.NO:
                    outcome = WebhookOutcomeCode.DECLINED
                elif _is_at_capacity(session, event):
                    outcome = WebhookOutcomeCode.CAPACITY_REACHED
                else:
                    resolution = _resolve_attendee(session, request)
                    if resolution is None or resolution.attendee is None:
                        outcome = WebhookOutcomeCode.IDENTITY_CONFLICT
                    elif (
                        existing_registration := _existing_registration(
                            session, event.id, resolution.attendee.id, submission_id
                        )
                    ) is not None:
                        issue_ticket_and_outbox(
                            session, existing_registration.id, derivation_key=derivation_key
                        )
                        outcome = WebhookOutcomeCode.ALREADY_REGISTERED
                    else:
                        outcome = WebhookOutcomeCode.IDENTITY_CONFLICT

            return _record_and_return(
                session,
                event_slug=event_slug,
                submission_id=submission_id,
                digest=digest,
                outcome=outcome,
                eligible=eligible,
            )
    except IntegrityError:
        session.rollback()
        return _result(WebhookOutcomeCode.IDENTITY_CONFLICT, submission_id)


def process_rsvp(
    session: Session,
    request: RsvpWebhookRequest,
    raw_body: bytes,
    *,
    derivation_key: str,
) -> WebhookProcessingResult:
    """Process one validated RSVP submission transactionally."""
    digest = payload_hash(raw_body)
    try:
        with session.begin():
            result = _process_new_submission(
                session, request, digest, derivation_key=derivation_key
            )
        return result
    except IntegrityError:
        session.rollback()
        return _resolve_post_conflict(session, request, digest, derivation_key=derivation_key)


def record_validation_rejection(
    session: Session, raw_body: bytes, parsed: object
) -> WebhookProcessingResult:
    """Record a rejected submission that failed JSON/schema validation."""
    digest = payload_hash(raw_body)
    event_slug, submission_id = _ledger_identity(parsed, raw_body)
    try:
        with session.begin():
            _lock_submission(session, event_slug, submission_id)
            if _find_ledger(session, event_slug, submission_id) is not None:
                return _result(WebhookOutcomeCode.DUPLICATE_SUBMISSION, submission_id)
            return _record_and_return(
                session,
                event_slug=event_slug,
                submission_id=submission_id,
                digest=digest,
                outcome=WebhookOutcomeCode.REJECTED_VALIDATION,
            )
    except IntegrityError:
        session.rollback()
        with session.begin():
            if _find_ledger(session, event_slug, submission_id) is not None:
                return _result(WebhookOutcomeCode.DUPLICATE_SUBMISSION, submission_id)
        return _result(WebhookOutcomeCode.REJECTED_VALIDATION, submission_id)
