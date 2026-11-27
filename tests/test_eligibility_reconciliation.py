"""PostgreSQL-backed historical eligibility reconciliation tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.cli import eligibility_reconciliation as cli
from app.core.config import Settings
from app.db.models import (
    Attendee,
    EligibilityRosterEntry,
    EmailDelivery,
    Event,
    Registration,
    Ticket,
    WebhookEvent,
)
from app.db.models.common import EventStatus, RegistrationStatus, WebhookOutcome
from app.schemas.webhook import RsvpWebhookRequest
from app.services import eligibility_reconciliation as reconciliation
from app.services import webhook_ingestion

pytestmark = pytest.mark.postgres

_CLEANUP_TABLES = (
    "checkins",
    "tickets",
    "email_deliveries",
    "registrations",
    "eligibility_rosters",
    "webhook_events",
    "audit_logs",
    "staff_memberships",
    "attendees",
    "events",
    "rate_limit_counters",
)


@dataclass(frozen=True)
class Harness:
    factory: sessionmaker[Session]
    settings: Settings


def _truncate(engine: Engine) -> None:
    tables = ", ".join(_CLEANUP_TABLES)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def harness(migrated_postgres: Engine, postgres_engine_settings: Settings) -> Iterator[Harness]:
    _truncate(migrated_postgres)
    factory = sessionmaker(
        bind=migrated_postgres,
        autoflush=False,
        expire_on_commit=False,
    )
    yield Harness(factory=factory, settings=postgres_engine_settings)
    _truncate(migrated_postgres)


def _create_event(
    factory: sessionmaker[Session],
    *,
    status: EventStatus = EventStatus.PUBLISHED,
    capacity: int | None = None,
) -> Event:
    now = datetime.now(UTC)
    event = Event(
        slug=f"hist-event-{uuid4().hex[:12]}",
        name="Historical Reconciliation Event",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
        timezone="UTC",
        status=status,
        capacity=capacity,
    )
    with factory() as session:
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def _seed(factory: sessionmaker[Session], event_id: object, urn: str) -> None:
    with factory() as session:
        session.add(EligibilityRosterEntry(event_id=event_id, normalized_urn=urn.strip().upper()))
        session.commit()


def _request(
    event_slug: str,
    submission_id: str,
    urn: str,
    *,
    attendance: str = "yes",
    email: str | None = None,
    name: str = "Historical Attendee",
) -> RsvpWebhookRequest:
    return RsvpWebhookRequest.model_validate(
        {
            "event_slug": event_slug,
            "submission_id": submission_id,
            "name": name,
            "email": email or f"hist-{uuid4().hex[:10]}@example.com",
            "phone": None,
            "urn": urn,
            "attendance": attendance,
        }
    )


def _jsonl(path: Path, requests: list[RsvpWebhookRequest]) -> Path:
    lines = [request.model_dump_json() for request in requests]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _count(factory: sessionmaker[Session], model: object) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _parse_cli_summary(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        if '"processed"' in line:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError("CLI summary was not printed")


def _run_cli(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    input_path: Path,
    event_slug: str,
    *,
    dry_run: bool,
) -> tuple[dict[str, object], str]:
    monkeypatch.setattr(cli, "get_settings", lambda: harness.settings)
    mode = "--dry-run" if dry_run else "--confirm"
    exit_code = cli.main(["--input", str(input_path), "--event-slug", event_slug, mode])
    assert exit_code == 0
    output = capsys.readouterr().out
    return _parse_cli_summary(output), output


def test_cli_requires_event_slug_and_explicit_mode() -> None:
    parser = cli.build_parser()
    base = ["--input", "responses.jsonl"]

    with pytest.raises(SystemExit):
        parser.parse_args(base + ["--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(base + ["--event-slug", "event-x"])
    with pytest.raises(SystemExit):
        parser.parse_args(base + ["--event-slug", "event-x", "--dry-run", "--confirm"])


def test_dry_run_has_no_side_effects_and_does_not_log_urns(
    harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = _create_event(harness.factory)
    eligible_urn = "HIST-DRY-ELIGIBLE"
    ineligible_urn = "HIST-DRY-INELIGIBLE"
    _seed(harness.factory, event.id, eligible_urn)
    input_path = _jsonl(
        tmp_path / "dry-run.jsonl",
        [
            _request(event.slug, "hist-dry-1", eligible_urn),
            _request(event.slug, "hist-dry-2", ineligible_urn),
        ],
    )

    summary, output = _run_cli(
        harness,
        monkeypatch,
        capsys,
        input_path,
        event.slug,
        dry_run=True,
    )

    assert eligible_urn not in output
    assert ineligible_urn not in output
    assert summary["processed"] == 2
    assert summary["eligible"] == 1
    assert summary["ineligible"] == 1
    assert summary["registered"] == 1
    assert summary["failed"] == 0
    assert _count(harness.factory, Registration) == 0
    assert _count(harness.factory, Attendee) == 0
    assert _count(harness.factory, Ticket) == 0
    assert _count(harness.factory, EmailDelivery) == 0
    assert _count(harness.factory, WebhookEvent) == 0


def test_confirmed_reconciliation_reuses_live_services(
    harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = _create_event(harness.factory)
    eligible_urn = "HIST-CONFIRM-YES"
    declined_urn = "HIST-CONFIRM-NO"
    ineligible_urn = "HIST-CONFIRM-OUT"
    for urn in (eligible_urn, declined_urn):
        _seed(harness.factory, event.id, urn)
    input_path = _jsonl(
        tmp_path / "confirm.jsonl",
        [
            _request(event.slug, "hist-yes", eligible_urn),
            _request(event.slug, "hist-no", declined_urn, attendance="no"),
            _request(event.slug, "hist-out", ineligible_urn),
        ],
    )

    summary, output = _run_cli(
        harness,
        monkeypatch,
        capsys,
        input_path,
        event.slug,
        dry_run=False,
    )

    assert eligible_urn not in output
    assert ineligible_urn not in output
    assert summary["processed"] == 3
    assert summary["eligible"] == 2
    assert summary["ineligible"] == 1
    assert summary["registered"] == 1
    assert summary["declined"] == 1
    assert summary["skipped"] == 0
    assert summary["failed"] == 0
    assert summary["outcomes"] == {"registered": 1, "declined": 1, "ineligible": 1}
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, Attendee) == 1
    assert _count(harness.factory, Ticket) == 1
    assert _count(harness.factory, EmailDelivery) == 1
    assert _count(harness.factory, WebhookEvent) == 3

    with harness.factory() as session:
        submission_ids = set(
            session.scalars(
                select(WebhookEvent.submission_id).where(WebhookEvent.event_slug == event.slug)
            )
        )
        rejected = session.scalar(
            select(WebhookEvent).where(WebhookEvent.submission_id == "hist-out")
        )
    assert submission_ids == {"hist-yes", "hist-no", "hist-out"}
    assert rejected is not None
    assert rejected.outcome == WebhookOutcome.REJECTED
    assert rejected.error_code == "ineligible"


def test_duplicate_and_existing_registration_are_skipped_safely(harness: Harness) -> None:
    event = _create_event(harness.factory)
    existing_urn = "HIST-EXISTING-URN"
    duplicate_urn = "HIST-DUPLICATE-URN"
    for urn in (existing_urn, duplicate_urn):
        _seed(harness.factory, event.id, urn)

    with harness.factory() as session:
        existing = Attendee(
            full_name="Existing Person", email="hist-existing@example.com", urn=existing_urn
        )
        session.add(existing)
        session.flush()
        session.add(
            Registration(
                event_id=event.id,
                attendee_id=existing.id,
                source_submission_id="hist-existing-registration",
                status=RegistrationStatus.REGISTERED,
                registered_at=datetime.now(UTC),
            )
        )
        session.commit()

    duplicate_request = _request(event.slug, "hist-duplicate-pair", duplicate_urn)
    requests = [
        _request(
            event.slug,
            "hist-existing-submission",
            existing_urn,
            email="hist-existing@example.com",
        ),
        duplicate_request,
        duplicate_request,
    ]
    derivation_key = harness.settings.ticket_token_derivation_key_value()

    with harness.factory() as session:
        first = reconciliation.reconcile_records(
            session, requests=requests, derivation_key=derivation_key
        )
    with harness.factory() as session:
        second = reconciliation.reconcile_records(
            session, requests=requests, derivation_key=derivation_key
        )

    assert first.registered == 1
    assert first.skipped == 2
    assert first.outcomes["already_registered"] == 1
    assert first.outcomes["duplicate_submission"] == 1
    assert second.skipped == 3
    assert second.registered == 0
    assert second.outcomes["duplicate_submission"] == 3
    assert _count(harness.factory, Registration) == 2
    assert _count(harness.factory, Attendee) == 2
    assert _count(harness.factory, Ticket) == 2
    assert _count(harness.factory, EmailDelivery) == 2
    assert _count(harness.factory, WebhookEvent) == 2


def test_capacity_window_and_identity_conflicts_are_reported(harness: Harness) -> None:
    capacity_event = _create_event(harness.factory, capacity=1)
    identity_event = _create_event(harness.factory)
    closed_event = _create_event(harness.factory, status=EventStatus.DRAFT)
    capacity_urn = "HIST-CAPACITY-URN"
    conflict_urn = "HIST-CONFLICT-URN"
    closed_urn = "HIST-CLOSED-URN"
    _seed(harness.factory, capacity_event.id, capacity_urn)
    _seed(harness.factory, identity_event.id, conflict_urn)
    _seed(harness.factory, closed_event.id, closed_urn)

    with harness.factory() as session:
        occupant = Attendee(
            full_name="Capacity Occupant",
            email="hist-capacity@example.com",
            urn="HIST-OCCUPANT-URN",
        )
        session.add(occupant)
        session.flush()
        session.add(
            Registration(
                event_id=capacity_event.id,
                attendee_id=occupant.id,
                source_submission_id="hist-capacity-seed",
                status=RegistrationStatus.REGISTERED,
                registered_at=datetime.now(UTC),
            )
        )
        session.add(
            Attendee(
                full_name="Conflicting Person",
                email="hist-conflict-owner@example.com",
                urn=conflict_urn,
            )
        )
        session.commit()

    requests = [
        _request(capacity_event.slug, "hist-capacity", capacity_urn),
        _request(
            identity_event.slug,
            "hist-identity",
            conflict_urn,
            email="hist-conflict-new@example.com",
        ),
        _request(closed_event.slug, "hist-closed", closed_urn),
    ]
    with harness.factory() as session:
        summary = reconciliation.reconcile_records(
            session,
            requests=requests,
            derivation_key=harness.settings.ticket_token_derivation_key_value(),
        )

    assert summary.outcomes == {
        "capacity_reached": 1,
        "identity_conflict": 1,
        "event_unavailable": 1,
    }
    assert summary.eligible == 2
    assert summary.ineligible == 0
    assert summary.failed == 3
    assert summary.registered == 0
    assert _count(harness.factory, Registration) == 1
    assert _count(harness.factory, Ticket) == 0
    assert _count(harness.factory, EmailDelivery) == 0
    assert _count(harness.factory, WebhookEvent) == 3


def test_partial_failure_is_retry_safe(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _create_event(harness.factory)
    urns = ("HIST-PART-A", "HIST-PART-B", "HIST-PART-C")
    for urn in urns:
        _seed(harness.factory, event.id, urn)
    requests = [
        _request(event.slug, "hist-part-a", urns[0]),
        _request(event.slug, "hist-part-b", urns[1]),
        _request(event.slug, "hist-part-c", urns[2]),
    ]
    derivation_key = harness.settings.ticket_token_derivation_key_value()
    original_record = webhook_ingestion._record_ledger

    def flaky_record(session: Session, **kwargs: object) -> None:
        if kwargs.get("submission_id") == "hist-part-b":
            raise RuntimeError("simulated ledger failure")
        original_record(session, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(webhook_ingestion, "_record_ledger", flaky_record)
    with harness.factory() as session:
        first = reconciliation.reconcile_records(
            session,
            requests=requests,
            derivation_key=derivation_key,
        )
    monkeypatch.undo()

    assert first.registered == 2
    assert first.failed == 1
    assert _count(harness.factory, Registration) == 2
    assert _count(harness.factory, Ticket) == 2
    assert _count(harness.factory, WebhookEvent) == 2

    with harness.factory() as session:
        retry = reconciliation.reconcile_records(
            session,
            requests=requests,
            derivation_key=derivation_key,
        )

    assert retry.skipped == 2
    assert retry.registered == 1
    assert _count(harness.factory, Registration) == 3
    assert _count(harness.factory, Ticket) == 3
    assert _count(harness.factory, WebhookEvent) == 3


def test_invalid_jsonl_lines_are_counted_without_identifiers(
    harness: Harness, tmp_path: Path
) -> None:
    event = _create_event(harness.factory)
    valid = _request(event.slug, "hist-valid-line", "HIST-VALID-URN")
    _seed(harness.factory, event.id, "HIST-VALID-URN")
    path = tmp_path / "mixed.jsonl"
    path.write_text(
        "{not json}\n"
        + valid.model_dump_json()
        + "\n"
        + json.dumps({"submission_id": "hist-bad"})
        + "\n",
        encoding="utf-8",
    )

    requests, invalid = reconciliation.load_historical_requests(path, event.slug)
    with harness.factory() as session:
        summary = reconciliation.reconcile_records(
            session,
            requests=requests,
            derivation_key=harness.settings.ticket_token_derivation_key_value(),
            invalid_records=invalid,
        )

    assert invalid == 2
    assert summary.processed == 3
    assert summary.failed == 2
    assert summary.registered == 1
    assert _count(harness.factory, WebhookEvent) == 1


def test_event_slug_is_explicit_and_unknown_events_fail(harness: Harness) -> None:
    with harness.factory() as session, pytest.raises(ValueError):
        reconciliation.resolve_event_id(session, "missing-historical-event")
