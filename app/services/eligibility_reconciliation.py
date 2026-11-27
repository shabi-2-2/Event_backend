"""Controlled historical Google Forms response reconciliation.

This module deliberately reuses the live webhook's ingestion service. It does
not insert tickets, registrations, webhook ledger rows, or outbox jobs itself.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.db.models import Event
from app.schemas.webhook import AttendanceValue, RsvpWebhookRequest
from app.services.webhook_ingestion import WebhookOutcomeCode, process_rsvp

logger = get_logger(__name__)


class HistoricalRsvpRecord(BaseModel):
    """One historical response. The event is supplied explicitly by the operator."""

    model_config = ConfigDict(extra="forbid")

    # Historical exports may carry an event slug. It is accepted only when it
    # matches the explicit --event-slug argument; it never selects the event.
    event_slug: str | None = Field(default=None, max_length=100)
    submission_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    urn: str = Field(min_length=1, max_length=64)
    attendance: AttendanceValue


@dataclass
class ReconciliationSummary:
    """Counts only; never contains student, submission, or contact details."""

    processed: int = 0
    eligible: int = 0
    ineligible: int = 0
    registered: int = 0
    declined: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_historical_requests(
    input_path: Path, event_slug: str
) -> tuple[list[RsvpWebhookRequest], int]:
    """Load valid historical records; invalid lines are counted, not logged."""

    requests: list[RsvpWebhookRequest] = []
    failed = 0
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = HistoricalRsvpRecord.model_validate_json(line)
                if record.event_slug is not None and record.event_slug.strip() != event_slug:
                    failed += 1
                    continue
                requests.append(
                    RsvpWebhookRequest(
                        event_slug=event_slug,
                        submission_id=record.submission_id,
                        name=record.name,
                        email=record.email,
                        phone=record.phone,
                        urn=record.urn,
                        attendance=record.attendance,
                    )
                )
            except (ValidationError, ValueError):
                failed += 1
    return requests, failed


def canonical_raw_body(request: RsvpWebhookRequest) -> bytes:
    """Build a deterministic ledger digest input for a historical record."""

    return json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def reconcile_records(
    session: Session,
    *,
    requests: list[RsvpWebhookRequest],
    derivation_key: str,
    invalid_records: int = 0,
) -> ReconciliationSummary:
    """Process records through the live webhook service and count safe outcomes."""

    summary = ReconciliationSummary(
        processed=len(requests) + invalid_records,
        failed=invalid_records,
    )
    for request in requests:
        try:
            # The live webhook service is the single eligibility authority. Its
            # result carries the roster decision made inside the same transaction
            # that created (or refused) registrations, tickets, and outbox jobs.
            result = process_rsvp(
                session,
                request,
                canonical_raw_body(request),
                derivation_key=derivation_key,
            )
        except Exception as exc:  # Keep the CLI safe for partial-batch retries.
            session.rollback()
            summary.failed += 1
            log_event(
                logger,
                logging.WARNING,
                "historical_reconciliation_record_failed",
                error_type=type(exc).__name__,
            )
            continue

        if result.eligible is True:
            summary.eligible += 1
        elif result.eligible is False:
            summary.ineligible += 1

        summary.outcomes[result.outcome.value] = summary.outcomes.get(result.outcome.value, 0) + 1
        if result.outcome == WebhookOutcomeCode.REGISTERED:
            summary.registered += 1
        elif result.outcome == WebhookOutcomeCode.DECLINED:
            summary.declined += 1
        elif result.outcome in {
            WebhookOutcomeCode.DUPLICATE_SUBMISSION,
            WebhookOutcomeCode.ALREADY_REGISTERED,
        }:
            summary.skipped += 1
        elif result.outcome in {
            WebhookOutcomeCode.CAPACITY_REACHED,
            WebhookOutcomeCode.IDENTITY_CONFLICT,
            WebhookOutcomeCode.EVENT_UNAVAILABLE,
        }:
            summary.failed += 1

    return summary


def resolve_event_id(session: Session, event_slug: str) -> UUID:
    event = session.scalar(select(Event).where(Event.slug == event_slug))
    if event is None:
        raise ValueError("The requested event was not found.")
    return event.id
