"""Event-scoped staff role assignment."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import StaffRole, native_enum, utc_now

if TYPE_CHECKING:
    from app.db.models.event import Event


class StaffMembership(Base):
    """Links a Supabase Auth user to an event with an explicit role."""

    __tablename__ = "staff_memberships"
    __table_args__ = (Index("ix_staff_memberships_user_id", "user_id"),)

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[StaffRole] = mapped_column(
        native_enum(StaffRole, "staff_role"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event] = relationship(
        back_populates="staff_memberships",
        foreign_keys=[event_id],
        cascade="save-update, merge",
    )
