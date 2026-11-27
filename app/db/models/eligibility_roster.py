"""Event-specific eligibility roster entry."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import utc_now


class EligibilityRosterEntry(Base):
    """A normalized URN admitted to one event's eligibility roster.

    No student name, email, or other personally identifying field is stored.
    """

    __tablename__ = "eligibility_rosters"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    normalized_urn: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_eligibility_rosters_event_urn",
            "event_id",
            "normalized_urn",
            unique=True,
        ),
        Index("ix_eligibility_rosters_event_created_at", "event_id", "created_at"),
    )
