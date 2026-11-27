"""Ticket entity holding only hashed QR credentials."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TicketStatus, native_enum, utc_now

if TYPE_CHECKING:
    from app.db.models.checkin import Checkin
    from app.db.models.registration import Registration


class Ticket(Base):
    """A hashed ticket credential issued for a registration."""

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("registration_id", name="uq_tickets_registration_id"),
        UniqueConstraint("token_hash", name="uq_tickets_token_hash"),
        UniqueConstraint("ticket_code", name="uq_tickets_ticket_code"),
        Index("ix_tickets_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    registration_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registrations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ticket_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        native_enum(TicketStatus, "ticket_status"),
        default=TicketStatus.ACTIVE,
        server_default=TicketStatus.ACTIVE.value,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    registration: Mapped[Registration] = relationship(
        back_populates="ticket",
        foreign_keys=[registration_id],
        cascade="save-update, merge",
    )
    checkin: Mapped[Checkin | None] = relationship(
        back_populates="ticket",
        uselist=False,
        cascade="save-update, merge",
        passive_deletes=False,
    )
