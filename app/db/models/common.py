"""Shared enums, timestamp mixins, and portable JSONB types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class RegistrationStatus(StrEnum):
    REGISTERED = "registered"
    CHECKED_IN = "checked_in"
    CANCELLED = "cancelled"


class TicketStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CheckinSource(StrEnum):
    MOBILE = "mobile"
    ADMIN = "admin"


class EmailPurpose(StrEnum):
    TICKET_ISSUED = "ticket_issued"
    TICKET_REISSUED = "ticket_reissued"


class EmailDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class WebhookOutcome(StrEnum):
    REGISTERED = "registered"
    DUPLICATE = "duplicate"
    IGNORED_DECLINED = "ignored_declined"
    REJECTED = "rejected"


class StaffRole(StrEnum):
    ADMIN = "admin"
    CHECKIN = "checkin"
    VIEWER = "viewer"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


def native_enum(enum_type: type[Enum], name: str) -> SAEnum:
    """Create a PostgreSQL native enum with a portable SQLite fallback."""
    return SAEnum(
        enum_type,
        name=name,
        native_enum=True,
        values_callable=_enum_values,
        create_constraint=True,
    )


JSONBType: Any = JSONB().with_variant(JSON(), "sqlite")
MutableJSONBType: Any = MutableDict.as_mutable(JSONBType)


class TimestampMixin:
    """Created/updated timestamps shared by mutable entities."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
