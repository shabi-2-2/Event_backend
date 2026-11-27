"""Event analytics built from efficient database aggregate queries."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Checkin, EmailDelivery, Registration, Ticket, WebhookEvent
from app.db.models.common import (
    EmailDeliveryStatus,
    RegistrationStatus,
    TicketStatus,
    WebhookOutcome,
)
from app.schemas.admin import (
    AnalyticsGranularity,
    AttendanceAnalyticsResponse,
    EmailAnalyticsResponse,
    OverviewAnalyticsResponse,
    RegistrationAnalyticsResponse,
    TimeBucket,
)
from app.services.admin_common import as_utc, require_aware

_MAX_RANGE_DAYS = 3660


def _validate_range(from_date: datetime | None, to_date: datetime | None) -> None:
    require_aware(from_date, field="from_date")
    require_aware(to_date, field="to_date")
    if from_date is not None and to_date is not None:
        if to_date < from_date:
            raise AppError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="to_date must not be before from_date.",
            )
        if to_date - from_date > timedelta(days=_MAX_RANGE_DAYS):
            raise AppError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Date range cannot exceed 10 years.",
            )


def _granularity(from_date: datetime | None, to_date: datetime | None) -> AnalyticsGranularity:
    if from_date is None or to_date is None:
        return AnalyticsGranularity.MONTH
    span_days = (to_date - from_date).days
    if span_days <= 31:
        return AnalyticsGranularity.DAY
    if span_days <= 180:
        return AnalyticsGranularity.WEEK
    return AnalyticsGranularity.MONTH


def _bucket_expression(
    column: Any,
    granularity: AnalyticsGranularity,
    *,
    dialect: str,
) -> Any:
    if dialect == "postgresql":
        return func.date_trunc(granularity.value, column)
    # Portable fallback for local SQLite tests. PostgreSQL uses true
    # day/week/month truncation as documented.
    if granularity == AnalyticsGranularity.MONTH:
        pattern = "%Y-%m-01T00:00:00+00:00"
    else:
        pattern = "%Y-%m-%dT00:00:00+00:00"
    return func.strftime(pattern, column)


def _parse_bucket(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise AppError(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="Unexpected aggregation value.",
        )
    return as_utc(parsed)


def _count(session: Session, statement: Select[Any]) -> int:
    return int(session.scalar(statement) or 0)


def overview(session: Session, *, event_id: UUID, event_slug: str) -> OverviewAnalyticsResponse:
    """Return aggregate counts for the operational dashboard."""

    total = _count(
        session,
        select(func.count()).select_from(Registration).where(Registration.event_id == event_id),
    )
    cancelled = _count(
        session,
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.CANCELLED,
        ),
    )
    checked_in = _count(
        session,
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.CHECKED_IN,
        ),
    )
    declined = _count(
        session,
        select(func.count(func.distinct(WebhookEvent.submission_id))).where(
            WebhookEvent.event_slug == event_slug,
            WebhookEvent.outcome == WebhookOutcome.IGNORED_DECLINED,
        ),
    )

    ticket_counts = dict(
        session.execute(
            select(Ticket.status, func.count())
            .join(Registration, Registration.id == Ticket.registration_id)
            .where(Registration.event_id == event_id)
            .group_by(Ticket.status)
        ).all()
    )
    email_counts = dict(
        session.execute(
            select(EmailDelivery.status, func.count())
            .join(Registration, Registration.id == EmailDelivery.registration_id)
            .where(Registration.event_id == event_id)
            .group_by(EmailDelivery.status)
        ).all()
    )
    confirmed = total - cancelled
    return OverviewAnalyticsResponse(
        total_registrations=total,
        confirmed_registrations=confirmed,
        cancelled_registrations=cancelled,
        declined_rsvps=declined,
        checked_in_attendees=checked_in,
        not_checked_in_attendees=max(confirmed - checked_in, 0),
        active_tickets=int(ticket_counts.get(TicketStatus.ACTIVE, 0)),
        used_tickets=int(ticket_counts.get(TicketStatus.USED, 0)),
        revoked_tickets=int(ticket_counts.get(TicketStatus.REVOKED, 0)),
        expired_tickets=int(ticket_counts.get(TicketStatus.EXPIRED, 0)),
        pending_email_deliveries=int(email_counts.get(EmailDeliveryStatus.PENDING, 0)),
        sent_email_deliveries=int(email_counts.get(EmailDeliveryStatus.SENT, 0)),
        failed_email_deliveries=int(email_counts.get(EmailDeliveryStatus.FAILED, 0)),
        dead_letter_email_deliveries=int(email_counts.get(EmailDeliveryStatus.DEAD_LETTER, 0)),
    )


def registrations(
    session: Session,
    *,
    event_id: UUID,
    from_date: datetime | None,
    to_date: datetime | None,
) -> RegistrationAnalyticsResponse:
    """Return registration counts over time for a configurable date range."""

    _validate_range(from_date, to_date)
    granularity = _granularity(from_date, to_date)
    conditions = [Registration.event_id == event_id]
    if from_date is not None:
        conditions.append(Registration.registered_at >= from_date)
    if to_date is not None:
        conditions.append(Registration.registered_at <= to_date)

    bucket = _bucket_expression(
        Registration.registered_at,
        granularity,
        dialect=session.get_bind().dialect.name,
    ).label("period_start")
    rows = session.execute(
        select(bucket, func.count().label("count"))
        .where(*conditions)
        .group_by(bucket)
        .order_by(bucket.asc())
    ).all()
    buckets = [
        TimeBucket(
            period_start=_parse_bucket(row[0]),
            period=granularity,
            count=cast(int, row[1]),
        )
        for row in rows
    ]
    return RegistrationAnalyticsResponse(
        granularity=granularity,
        from_date=as_utc(from_date) if from_date else None,
        to_date=as_utc(to_date) if to_date else None,
        buckets=buckets,
        total_in_range=sum(bucket.count for bucket in buckets),
    )


def attendance(
    session: Session,
    *,
    event_id: UUID,
    from_date: datetime | None,
    to_date: datetime | None,
) -> AttendanceAnalyticsResponse:
    """Return attendance totals and check-in counts over time."""

    _validate_range(from_date, to_date)
    confirmed = _count(
        session,
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.status != RegistrationStatus.CANCELLED,
        ),
    )
    checked_in = _count(
        session,
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.CHECKED_IN,
        ),
    )
    conditions = [Checkin.event_id == event_id]
    if from_date is not None:
        conditions.append(Checkin.checked_in_at >= from_date)
    if to_date is not None:
        conditions.append(Checkin.checked_in_at <= to_date)
    granularity = _granularity(from_date, to_date)
    bucket = _bucket_expression(
        Checkin.checked_in_at, granularity, dialect=session.get_bind().dialect.name
    ).label("period_start")
    rows = session.execute(
        select(bucket, func.count().label("count"))
        .where(*conditions)
        .group_by(bucket)
        .order_by(bucket.asc())
    ).all()
    percentage = round((checked_in / confirmed) * 100, 2) if confirmed else 0.0
    return AttendanceAnalyticsResponse(
        confirmed_registrations=confirmed,
        checked_in_attendees=checked_in,
        not_checked_in_attendees=max(confirmed - checked_in, 0),
        attendance_percentage=percentage,
        buckets=[
            TimeBucket(
                period_start=_parse_bucket(row[0]),
                period=granularity,
                count=cast(int, row[1]),
            )
            for row in rows
        ],
    )


def email_deliveries(session: Session, *, event_id: UUID) -> EmailAnalyticsResponse:
    """Return outbox status counts and safe aggregate attempt statistics."""

    status_rows = session.execute(
        select(EmailDelivery.status, func.count())
        .join(Registration, Registration.id == EmailDelivery.registration_id)
        .where(Registration.event_id == event_id)
        .group_by(EmailDelivery.status)
    ).all()
    status_counts = {status.value: cast(int, count) for status, count in status_rows}
    for status in EmailDeliveryStatus:
        status_counts.setdefault(status.value, 0)

    total, attempts_sum, attempts_max, attempts_avg, retried = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(EmailDelivery.attempts), 0),
            func.coalesce(func.max(EmailDelivery.attempts), 0),
            func.coalesce(func.avg(EmailDelivery.attempts), 0.0),
            func.count().filter(EmailDelivery.attempts > 1),
        )
        .join(Registration, Registration.id == EmailDelivery.registration_id)
        .where(Registration.event_id == event_id)
    ).one()
    return EmailAnalyticsResponse(
        total_deliveries=cast(int, total),
        status_counts=status_counts,
        attempt_summary={
            "total_attempts": cast(int, attempts_sum),
            "max_attempts": cast(int, attempts_max),
            "average_attempts": round(cast(float, attempts_avg), 2),
            "retried_deliveries": cast(int, retried),
        },
    )
