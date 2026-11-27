"""Event-scoped eligibility roster import and exact-match lookup."""

from __future__ import annotations

import base64
import binascii
import csv
import io
import logging
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.db.models import EligibilityRosterEntry, Event
from app.schemas.admin import Page
from app.schemas.eligibility import RosterEntryResponse, RosterImportResponse
from app.services.admin_common import (
    add_audit,
    log_admin_action,
    mutation_transaction,
    not_found,
    paginate,
    with_row_lock,
)
from app.services.urn import try_normalize_urn

logger = get_logger(__name__)


@dataclass(frozen=True)
class ParsedRoster:
    """Sanitized parsing result; never contains source row contents."""

    urns: tuple[str, ...]
    rows: int
    duplicates: int
    invalid_rows: int


def _validation_error(message: str) -> AppError:
    return AppError(status_code=422, code="VALIDATION_ERROR", message=message)


def _validate_filename(filename: str) -> str:
    value = filename.strip()
    if not value or len(value) > 255:
        raise _validation_error("A valid CSV filename is required.")
    path = PurePath(value)
    if path.is_absolute() or "/" in value or "\\" in value or ".." in path.parts:
        raise _validation_error("Unsafe upload filename.")
    if path.suffix.lower() != ".csv":
        raise _validation_error("Only CSV roster files are accepted.")
    return value


def _decode_csv(payload: str, filename: str, settings: Settings) -> bytes:
    _validate_filename(filename)
    try:
        encoded = payload.encode("ascii")
    except UnicodeEncodeError as exc:
        raise _validation_error("CSV payload must be valid base64.") from exc
    if len(encoded) > settings.roster_import_max_upload_bytes * 2:
        raise _validation_error("CSV upload exceeds the configured size limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _validation_error("CSV payload must be valid base64.") from exc
    if not raw:
        raise _validation_error("CSV upload is empty.")
    if len(raw) > settings.roster_import_max_upload_bytes:
        raise _validation_error("CSV upload exceeds the configured size limit.")
    return raw


def parse_roster_csv(payload: str, filename: str, settings: Settings) -> ParsedRoster:
    """Validate the inspected CSV structure and collect normalized URNs."""

    raw = _decode_csv(payload, filename, settings)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _validation_error("CSV upload must be UTF-8 encoded.") from exc
    if "\x00" in text:
        raise _validation_error("CSV upload contains invalid control characters.")

    lines = text.splitlines()
    if not lines:
        raise _validation_error("CSV upload is empty.")

    separator_counts = {
        ",": lines[0].count(","),
        ";": lines[0].count(";"),
        "\t": lines[0].count("\t"),
        "|": lines[0].count("|"),
    }
    if separator_counts[","] == 0 or any(
        count > 0 for separator, count in separator_counts.items() if separator != ","
    ):
        raise _validation_error("CSV upload must be comma-delimited.")

    data_rows = lines[1:]
    if len(data_rows) > settings.roster_import_max_rows:
        raise _validation_error("CSV upload exceeds the configured row limit.")

    reader = csv.reader(io.StringIO(text), delimiter=",")
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise _validation_error("CSV upload is missing a header row.") from exc
    except csv.Error as exc:
        raise _validation_error("CSV upload is malformed.") from exc

    urn_columns = [index for index, cell in enumerate(header) if cell.lower() == "urn"]
    if len(urn_columns) != 1:
        raise _validation_error("CSV upload requires exactly one URN column.")

    urn_index = urn_columns[0]
    seen: set[str] = set()
    urns: list[str] = []
    duplicates = 0
    invalid_rows = 0
    rows = 0

    try:
        for row in reader:
            rows += 1
            if len(row) != len(header) or not any(cell.strip() for cell in row):
                invalid_rows += 1
                continue
            normalized = try_normalize_urn(row[urn_index])
            if normalized is None:
                invalid_rows += 1
                continue
            if normalized in seen:
                duplicates += 1
                continue
            seen.add(normalized)
            urns.append(normalized)
    except csv.Error as exc:
        raise _validation_error("CSV upload is malformed.") from exc

    return ParsedRoster(
        urns=tuple(urns),
        rows=rows,
        duplicates=duplicates,
        invalid_rows=invalid_rows,
    )


def _existing_urns(session: Session, event_id: UUID, urns: tuple[str, ...]) -> set[str]:
    if not urns:
        return set()
    return set(
        session.scalars(
            select(EligibilityRosterEntry.normalized_urn).where(
                EligibilityRosterEntry.event_id == event_id,
                EligibilityRosterEntry.normalized_urn.in_(urns),
            )
        ).all()
    )


def _summary(
    *,
    mode: str,
    parsed: ParsedRoster,
    already_imported: int,
    imported: int,
    concurrent_skips: int = 0,
) -> RosterImportResponse:
    return RosterImportResponse(
        mode=mode,  # type: ignore[arg-type]
        rows=parsed.rows,
        valid_unique=len(parsed.urns),
        duplicates=parsed.duplicates,
        invalid_rows=parsed.invalid_rows,
        already_imported=already_imported,
        imported=imported,
        skipped=already_imported + concurrent_skips,
    )


def preview_import(
    session: Session,
    *,
    event_id: UUID,
    payload: str,
    filename: str,
    settings: Settings,
) -> RosterImportResponse:
    """Parse and validate without writing any roster records."""

    parsed = parse_roster_csv(payload, filename, settings)
    existing = _existing_urns(session, event_id, parsed.urns)
    return _summary(
        mode="dry_run",
        parsed=parsed,
        already_imported=len(existing),
        imported=0,
    )


def confirm_import(
    session: Session,
    *,
    event_id: UUID,
    payload: str,
    filename: str,
    settings: Settings,
    actor_user_id: UUID,
) -> RosterImportResponse:
    """Insert valid new URNs transactionally and record a redacted audit entry."""

    parsed = parse_roster_csv(payload, filename, settings)

    with mutation_transaction(session):
        locked_event = session.scalar(
            with_row_lock(select(Event).where(Event.id == event_id), session, Event)
        )
        if locked_event is None:
            raise not_found("The event was not found.")

        existing = _existing_urns(session, event_id, parsed.urns)
        new_urns = [urn for urn in parsed.urns if urn not in existing]
        imported = 0
        if new_urns:
            values: list[dict[str, Any]] = [
                {"event_id": event_id, "normalized_urn": urn} for urn in new_urns
            ]
            dialect = session.get_bind().dialect.name
            insert_builder = postgresql.insert if dialect == "postgresql" else sqlite.insert
            statement = insert_builder(EligibilityRosterEntry).values(values)
            statement = statement.on_conflict_do_nothing(
                index_elements=["event_id", "normalized_urn"]
            )
            result = session.execute(statement)
            rowcount = cast("CursorResult[Any]", result).rowcount
            imported = int(rowcount) if rowcount >= 0 else len(new_urns)

        concurrent_skips = max(0, len(new_urns) - imported)
        summary = _summary(
            mode="confirmed",
            parsed=parsed,
            already_imported=len(existing),
            imported=imported,
            concurrent_skips=concurrent_skips,
        )
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="roster.imported",
            target_type="eligibility_roster",
            context={
                "outcome": "success",
                "rows": summary.rows,
                "valid_unique": summary.valid_unique,
                "duplicates": summary.duplicates,
                "invalid_rows": summary.invalid_rows,
                "already_imported": summary.already_imported,
                "imported": summary.imported,
                "skipped": summary.skipped,
            },
        )

    log_admin_action(
        "roster.imported",
        event_id=event_id,
        actor_user_id=actor_user_id,
    )
    return summary


def is_eligible(session: Session, event_id: UUID, urn: object) -> bool:
    """Return whether the exact normalized URN is in this event's roster."""

    normalized = try_normalize_urn(urn)
    if normalized is None:
        return False
    return (
        session.scalar(
            select(EligibilityRosterEntry.id).where(
                EligibilityRosterEntry.event_id == event_id,
                EligibilityRosterEntry.normalized_urn == normalized,
            )
        )
        is not None
    )


def list_entries(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
) -> Page[RosterEntryResponse]:
    """Return paginated roster entries for authorized event administrators."""

    statement = (
        select(EligibilityRosterEntry)
        .where(EligibilityRosterEntry.event_id == event_id)
        .order_by(EligibilityRosterEntry.created_at, EligibilityRosterEntry.id)
    )
    rows, total = paginate(session, statement, page=page, page_size=page_size)
    items = [
        RosterEntryResponse(
            normalized_urn=row[0].normalized_urn,
            created_at=row[0].created_at,
        )
        for row in rows
    ]
    return Page(items=items, page=page, page_size=page_size, total=total)


def log_ineligible_outcome(*, event_id: UUID) -> None:
    """Log only non-sensitive eligibility metadata for operations monitoring."""

    log_event(
        logger,
        logging.INFO,
        "eligibility_check",
        event_id=str(event_id),
        outcome="ineligible",
    )
