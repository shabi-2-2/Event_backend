"""Check-in entity with one successful record per ticket."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
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
    CheckinSource,
    MutableJSONBType,
    native_enum,
    utc_now,
)

if TYPE_CHECKING:
    from app.db.models.event import Event
    from app.db.models.registration import Registration
    from app.db.models.ticket import Ticket


class Checkin(Base):
    """A successful check-in event for a ticket."""

    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_checkins_ticket_id"),
        Index("ix_checkins_event_checked_in_at", "event_id", "checked_in_at"),
        Index("ix_checkins_registration_id", "registration_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    registration_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registrations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    scanned_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    station: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[CheckinSource] = mapped_column(
        native_enum(CheckinSource, "checkin_source"),
        default=CheckinSource.MOBILE,
        server_default=CheckinSource.MOBILE.value,
        nullable=False,
    )
    # Mapped as metadata_ because `metadata` is reserved by DeclarativeBase.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        MutableJSONBType,
        default=dict,
        nullable=False,
    )

    ticket: Mapped[Ticket] = relationship(
        back_populates="checkin",
        foreign_keys=[ticket_id],
        cascade="save-update, merge",
    )
    registration: Mapped[Registration] = relationship(
        foreign_keys=[registration_id],
        cascade="save-update, merge",
    )
    event: Mapped[Event] = relationship(
        foreign_keys=[event_id],
        cascade="save-update, merge",
    )
