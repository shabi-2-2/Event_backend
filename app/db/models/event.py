"""Event entity."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import EventStatus, TimestampMixin, native_enum, utc_now

if TYPE_CHECKING:
    from app.db.models.audit_log import AuditLog
    from app.db.models.registration import Registration
    from app.db.models.staff_membership import StaffMembership
    from app.db.models.webhook_event import WebhookEvent


class Event(TimestampMixin, Base):
    """A single event that registrations and tickets belong to."""

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_events_slug"),
        Index("ix_events_status", "status"),
        Index("ix_events_starts_at", "starts_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_opens_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registration_closes_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[EventStatus] = mapped_column(
        native_enum(EventStatus, "event_status"),
        default=EventStatus.DRAFT,
        server_default=EventStatus.DRAFT.value,
        nullable=False,
    )

    registrations: Mapped[list[Registration]] = relationship(
        back_populates="event",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    staff_memberships: Mapped[list[StaffMembership]] = relationship(
        back_populates="event",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="event",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    webhook_events: Mapped[list[WebhookEvent]] = relationship(
        primaryjoin="Event.slug == foreign(WebhookEvent.event_slug)",
        viewonly=True,
        uselist=True,
    )
