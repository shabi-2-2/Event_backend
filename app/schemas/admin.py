"""Request and whitelisted response schemas for administrative APIs."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.common import (
    EmailDeliveryStatus,
    EmailPurpose,
    EventStatus,
    RegistrationStatus,
    StaffRole,
    TicketStatus,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

T = TypeVar("T")


class CheckinFilterStatus(StrEnum):
    PENDING = "pending"
    CHECKED_IN = "checked_in"


class AttendeeSortField(StrEnum):
    REGISTERED_AT = "registered_at"
    NAME = "name"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class AnalyticsGranularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone offset")
    return value


def validate_event_times(
    starts_at: datetime,
    ends_at: datetime,
    registration_opens_at: datetime | None,
    registration_closes_at: datetime | None,
) -> None:
    """Validate event and registration-window consistency."""

    for value in (starts_at, ends_at, registration_opens_at, registration_closes_at):
        if value is not None:
            _require_aware(value)
    if ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")
    if registration_opens_at is not None and registration_opens_at >= starts_at:
        raise ValueError("registration_opens_at must be before starts_at")
    if registration_closes_at is not None and registration_closes_at > starts_at:
        raise ValueError("registration_closes_at must not be after starts_at")
    if (
        registration_opens_at is not None
        and registration_closes_at is not None
        and registration_closes_at <= registration_opens_at
    ):
        raise ValueError("registration_closes_at must be after registration_opens_at")


class Page(BaseModel, Generic[T]):  # noqa: UP046
    """Stable pagination envelope for collection endpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[T]
    page: int
    page_size: int
    total: int


class EventCreate(BaseModel):
    """Payload for creating an event in draft status."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=3, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    venue: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, ge=1, le=1_000_000)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("slug must be lowercase alphanumeric with single hyphens")
        return normalized

    @field_validator("name", mode="before")
    @classmethod
    def _trim_required_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("venue", mode="before")
    @classmethod
    def _trim_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        return trimmed or None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized

    @model_validator(mode="after")
    def _validate_timeline(self) -> EventCreate:
        validate_event_times(
            self.starts_at,
            self.ends_at,
            self.registration_opens_at,
            self.registration_closes_at,
        )
        return self


class EventUpdate(BaseModel):
    """Partial event update. Status and slug are intentionally immutable."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    venue: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, ge=1, le=1_000_000)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim_required_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("venue", mode="before")
    @classmethod
    def _trim_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        return trimmed or None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized


class EventResponse(BaseModel):
    """Event representation without internal identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str
    name: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    venue: str | None
    capacity: int | None
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    status: EventStatus
    created_at: datetime
    updated_at: datetime


class AdminAttendeeResponse(BaseModel):
    """Admin attendee view, including PII needed for event administration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attendee_reference: str
    full_name: str
    urn: str
    email: str
    phone: str | None
    registration_reference: str
    registration_status: RegistrationStatus
    registered_at: datetime
    checked_in_at: datetime | None
    cancelled_at: datetime | None
    ticket_reference: str | None
    ticket_status: TicketStatus | None
    ticket_expires_at: datetime | None
    ticket_used_at: datetime | None
    check_in_status: CheckinFilterStatus
    check_in_at: datetime | None
    station: str | None


class ViewerAttendeeResponse(BaseModel):
    """Restricted attendee view for read-only staff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attendee_reference: str
    full_name: str
    urn: str
    registration_status: RegistrationStatus
    ticket_status: TicketStatus | None
    check_in_status: CheckinFilterStatus
    checked_in_at: datetime | None


class RegistrationResponse(BaseModel):
    """Admin registration view with role-appropriate linked information."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_reference: str
    attendee_reference: str
    attendee_name: str
    email: str
    phone: str | None
    registration_status: RegistrationStatus
    registered_at: datetime
    checked_in_at: datetime | None
    cancelled_at: datetime | None
    ticket_reference: str | None
    ticket_status: TicketStatus | None
    check_in_status: CheckinFilterStatus
    check_in_at: datetime | None
    station: str | None


class TicketResponse(BaseModel):
    """Ticket representation containing only public references and status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_reference: str
    attendee_reference: str
    attendee_name: str
    registration_status: RegistrationStatus
    ticket_status: TicketStatus
    issued_at: datetime
    expires_at: datetime | None
    used_at: datetime | None
    revoked_at: datetime | None
    check_in_at: datetime | None


class TicketResendResponse(BaseModel):
    """Confirmation that a resend job was queued without sending directly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_reference: str
    delivery_reference: UUID
    status: EmailDeliveryStatus
    resend_sequence: int
    message: str


class StaffCreateRequest(BaseModel):
    """Role assignment for an existing Supabase Auth user."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: StaffRole


class StaffRoleUpdate(BaseModel):
    """Role-only payload for changing an existing membership."""

    model_config = ConfigDict(extra="forbid")

    role: StaffRole


class StaffResponse(BaseModel):
    """Staff membership representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    role: StaffRole
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Redacted audit-log entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reference: UUID
    action: str
    target_type: str
    target_id: str | None
    context: dict[str, Any]
    actor_user_id: UUID | None
    created_at: datetime


class EmailDeliveryResponse(BaseModel):
    """Safe outbox-job representation for operational monitoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery_reference: UUID
    registration_reference: str
    ticket_reference: str
    purpose: EmailPurpose
    status: EmailDeliveryStatus
    attempts: int
    resend_sequence: int
    error_code: str | None
    next_attempt_at: datetime | None
    created_at: datetime
    sent_at: datetime | None


class EmailRetryResponse(BaseModel):
    """Confirmation that a fresh retry job replaced an old failed job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery_reference: UUID
    registration_reference: str
    ticket_reference: str
    status: EmailDeliveryStatus
    resend_sequence: int
    previous_status: EmailDeliveryStatus
    message: str


class OverviewAnalyticsResponse(BaseModel):
    """Aggregate operational counts; no attendee PII is included."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_registrations: int
    confirmed_registrations: int
    cancelled_registrations: int
    declined_rsvps: int
    checked_in_attendees: int
    not_checked_in_attendees: int
    active_tickets: int
    used_tickets: int
    revoked_tickets: int
    expired_tickets: int
    pending_email_deliveries: int
    sent_email_deliveries: int
    failed_email_deliveries: int
    dead_letter_email_deliveries: int


class TimeBucket(BaseModel):
    """One aggregated time bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period_start: datetime
    period: AnalyticsGranularity
    count: int


class RegistrationAnalyticsResponse(BaseModel):
    """Registration counts grouped by day, week, or month."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    granularity: AnalyticsGranularity
    from_date: datetime | None
    to_date: datetime | None
    buckets: list[TimeBucket]
    total_in_range: int


class AttendanceAnalyticsResponse(BaseModel):
    """Attendance totals and check-in counts over time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmed_registrations: int
    checked_in_attendees: int
    not_checked_in_attendees: int
    attendance_percentage: float
    buckets: list[TimeBucket]


class EmailAnalyticsResponse(BaseModel):
    """Outbox status counts and safe delivery-attempt statistics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_deliveries: int
    status_counts: dict[str, int]
    attempt_summary: dict[str, int | float]
