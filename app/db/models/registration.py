"""Registration entity linking attendees to events."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    RegistrationStatus,
    TimestampMixin,
    native_enum,
    utc_now,
)

if TYPE_CHECKING:
    from app.db.models.attendee import Attendee
    from app.db.models.email_delivery import EmailDelivery
    from app.db.models.event import Event
    from app.db.models.ticket import Ticket


class Registration(TimestampMixin, Base):
    """One attendee's registration for one event."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "attendee_id", name="uq_registrations_event_attendee"),
        UniqueConstraint(
            "event_id",
            "source_submission_id",
            name="uq_registrations_event_submission",
        ),
        Index("ix_registrations_event_status", "event_id", "status"),
        Index("ix_registrations_event_created_at", "event_id", "created_at"),
        Index("ix_registrations_attendee_id", "attendee_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attendee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("attendees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_submission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        native_enum(RegistrationStatus, "registration_status"),
        default=RegistrationStatus.REGISTERED,
        server_default=RegistrationStatus.REGISTERED.value,
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[Event] = relationship(
        back_populates="registrations",
        foreign_keys=[event_id],
        cascade="save-update, merge",
    )
    attendee: Mapped[Attendee] = relationship(
        back_populates="registrations",
        foreign_keys=[attendee_id],
        cascade="save-update, merge",
    )
    ticket: Mapped[Ticket | None] = relationship(
        back_populates="registration",
        uselist=False,
        cascade="save-update, merge",
        passive_deletes=False,
    )
    email_deliveries: Mapped[list[EmailDelivery]] = relationship(
        back_populates="registration",
        cascade="save-update, merge",
        passive_deletes=False,
    )
