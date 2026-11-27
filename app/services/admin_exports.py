"""Streaming CSV and XLSX exports with formula-injection protection."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator, Sequence
from datetime import datetime
from uuid import UUID

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Attendee, Checkin, Registration, Ticket
from app.schemas.admin import ExportFormat
from app.services.admin_common import add_audit, as_utc, mutation_transaction

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FORMULA_PREFIXES = {"=", "+", "-", "@"}


def _safe_cell(value: object) -> str:
    """Convert a value to a spreadsheet-safe string cell."""

    if value is None:
        return ""
    text = as_utc(value).isoformat() if isinstance(value, datetime) else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return f"'{text}"
    return text


def _format_filename(kind: str, event_slug: str, extension: str) -> str:
    safe_slug = re.sub(r"[^a-z0-9-]", "-", event_slug.lower())[:60]
    return f"{kind}-{safe_slug}.{extension}"


def _csv_response(
    *,
    header: Sequence[str],
    rows: Iterator[Sequence[object]],
    filename: str,
) -> StreamingResponse:
    def generate() -> Iterator[bytes]:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([_safe_cell(value) for value in header])
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        for row in rows:
            writer.writerow([_safe_cell(value) for value in row])
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(
    *,
    header: Sequence[str],
    rows: Iterator[Sequence[object]],
    filename: str,
) -> StreamingResponse:
    def generate() -> Iterator[bytes]:
        from openpyxl import Workbook

        workbook = Workbook(write_only=True)
        worksheet = workbook.create_sheet(title="Export")
        worksheet.append([_safe_cell(value) for value in header])
        for row in rows:
            worksheet.append([_safe_cell(value) for value in row])
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        yield output.getvalue()

    return StreamingResponse(
        generate(),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _attendee_rows(session: Session, event_id: UUID) -> Iterator[tuple[object, ...]]:
    statement = (
        select(Attendee, Registration, Ticket, Checkin)
        .join(Registration, Registration.attendee_id == Attendee.id)
        .outerjoin(Ticket, Ticket.registration_id == Registration.id)
        .outerjoin(Checkin, Checkin.ticket_id == Ticket.id)
        .where(Registration.event_id == event_id)
        .order_by(Registration.registered_at.asc(), Registration.id.asc())
    )
    result = session.execute(statement).yield_per(500)
    for attendee, registration, ticket, checkin in result:
        yield (
            attendee.full_name,
            attendee.urn,
            attendee.email,
            attendee.phone,
            registration.status.value,
            ticket.status.value if ticket else None,
            registration.registered_at,
            checkin.checked_in_at if checkin else registration.checked_in_at,
            checkin.station if checkin else None,
        )


def _checkin_rows(session: Session, event_id: UUID) -> Iterator[tuple[object, ...]]:
    statement = (
        select(Attendee, Registration, Ticket, Checkin)
        .join(Registration, Registration.id == Checkin.registration_id)
        .join(Attendee, Attendee.id == Registration.attendee_id)
        .join(Ticket, Ticket.id == Checkin.ticket_id)
        .where(Checkin.event_id == event_id)
        .order_by(Checkin.checked_in_at.asc(), Checkin.id.asc())
    )
    result = session.execute(statement).yield_per(500)
    for attendee, registration, ticket, checkin in result:
        yield (
            attendee.full_name,
            attendee.urn,
            attendee.email,
            attendee.phone,
            registration.status.value,
            ticket.status.value,
            checkin.checked_in_at,
            checkin.station,
            checkin.source.value,
        )


_ATTENDEE_HEADER = (
    "name",
    "urn",
    "email",
    "phone",
    "registration_status",
    "ticket_status",
    "registered_at",
    "checked_in_at",
    "station",
)
_CHECKIN_HEADER = (
    "name",
    "urn",
    "email",
    "phone",
    "registration_status",
    "ticket_status",
    "checked_in_at",
    "station",
    "source",
)


def _audit_export(
    session: Session,
    *,
    event_id: UUID,
    actor_user_id: UUID,
    action: str,
    export_format: str,
) -> None:
    with mutation_transaction(session):
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="export",
            target_id=None,
            context={"format": export_format},
        )


def export_attendees(
    session: Session,
    *,
    event_id: UUID,
    event_slug: str,
    export_format: ExportFormat,
    actor_user_id: UUID,
) -> StreamingResponse:
    """Stream the attendee export after recording a non-content audit entry."""

    _audit_export(
        session,
        event_id=event_id,
        actor_user_id=actor_user_id,
        action="export.attendees",
        export_format=export_format.value,
    )
    rows = _attendee_rows(session, event_id)
    if export_format == ExportFormat.CSV:
        return _csv_response(
            header=_ATTENDEE_HEADER,
            rows=rows,
            filename=_format_filename("attendees", event_slug, "csv"),
        )
    if export_format == ExportFormat.XLSX:
        return _xlsx_response(
            header=_ATTENDEE_HEADER,
            rows=rows,
            filename=_format_filename("attendees", event_slug, "xlsx"),
        )
    raise AppError(status_code=422, code="VALIDATION_ERROR", message="Unsupported export format.")


def export_checkins(
    session: Session,
    *,
    event_id: UUID,
    event_slug: str,
    export_format: ExportFormat,
    actor_user_id: UUID,
) -> StreamingResponse:
    """Stream the check-in export after recording a non-content audit entry."""

    _audit_export(
        session,
        event_id=event_id,
        actor_user_id=actor_user_id,
        action="export.checkins",
        export_format=export_format.value,
    )
    rows = _checkin_rows(session, event_id)
    if export_format == ExportFormat.CSV:
        return _csv_response(
            header=_CHECKIN_HEADER,
            rows=rows,
            filename=_format_filename("checkins", event_slug, "csv"),
        )
    if export_format == ExportFormat.XLSX:
        return _xlsx_response(
            header=_CHECKIN_HEADER,
            rows=rows,
            filename=_format_filename("checkins", event_slug, "xlsx"),
        )
    raise AppError(status_code=422, code="VALIDATION_ERROR", message="Unsupported export format.")
