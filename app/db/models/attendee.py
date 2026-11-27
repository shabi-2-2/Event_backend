"""Attendee entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.db.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.registration import Registration


class Attendee(TimestampMixin, Base):
    """A person who may register for one or more events."""

    __tablename__ = "attendees"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    urn: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("uq_attendees_email_lower", func.lower(email), unique=True),
        # Values are normalized by _normalize_urn before they reach the database,
        # so a partial unique index on the stored column is sufficient.
        Index(
            "uq_attendees_urn",
            "urn",
            unique=True,
            postgresql_where=urn.is_not(None),
            sqlite_where=urn.is_not(None),
        ),
        Index("ix_attendees_full_name", "full_name"),
    )

    registrations: Mapped[list[Registration]] = relationship(
        back_populates="attendee",
        cascade="save-update, merge",
        passive_deletes=False,
    )

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        return value.strip().lower()

    @validates("urn")
    def _normalize_urn(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()
