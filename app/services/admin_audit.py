"""Read-only administrative audit-log queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AuditLog
from app.schemas.admin import AuditLogResponse, Page, SortOrder
from app.services.admin_common import as_utc, like_term, paginate, redact_context, require_aware


def _response(entry: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        audit_reference=entry.id,
        action=entry.action,
        target_type=entry.target_type,
        target_id=entry.target_id,
        context=redact_context(entry.context),
        actor_user_id=entry.actor_user_id,
        created_at=as_utc(entry.created_at),
    )


def list_audit_logs(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
    action: str | None,
    actor_user_id: UUID | None,
    from_date: datetime | None,
    to_date: datetime | None,
    sort_order: SortOrder,
) -> Page[AuditLogResponse]:
    """Return a filtered audit-log page with redacted context metadata."""

    require_aware(from_date, field="from_date")
    require_aware(to_date, field="to_date")
    if from_date and to_date and to_date < from_date:
        raise AppError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="to_date must not be before from_date.",
        )

    statement: Any = select(AuditLog).where(AuditLog.event_id == event_id)
    if action:
        statement = statement.where(AuditLog.action.ilike(like_term(action), escape="\\"))
    if actor_user_id is not None:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)
    if from_date is not None:
        statement = statement.where(AuditLog.created_at >= from_date)
    if to_date is not None:
        statement = statement.where(AuditLog.created_at <= to_date)

    ordering = (
        AuditLog.created_at.asc() if sort_order == SortOrder.ASC else AuditLog.created_at.desc()
    )
    statement = statement.order_by(ordering, AuditLog.id.asc())
    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[AuditLogResponse](
        items=[_response(row[0]) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )
