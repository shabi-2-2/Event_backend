"""Transactional outbox for ticket emails."""

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
from app.db.models.common import (
    EmailDeliveryStatus,
    EmailPurpose,
    native_enum,
    utc_now,
)

if TYPE_CHECKING:
    from app.db.models.registration import Registration
    from app.db.models.ticket import Ticket


class EmailDelivery(Base):
    """One queued email job for a ticket."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "purpose",
            "resend_sequence",
            name="uq_email_deliveries_ticket_purpose_sequence",
        ),
        Index("ix_email_deliveries_registration_id", "registration_id"),
        Index("ix_email_deliveries_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    registration_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registrations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purpose: Mapped[EmailPurpose] = mapped_column(
        native_enum(EmailPurpose, "email_purpose"),
        nullable=False,
    )
    # 0 is the original issuance job. Higher values are explicit resend/retry
    # jobs, allowing legitimate repeats without overwriting delivery history.
    resend_sequence: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    status: Mapped[EmailDeliveryStatus] = mapped_column(
        native_enum(EmailDeliveryStatus, "email_delivery_status"),
        default=EmailDeliveryStatus.PENDING,
        server_default=EmailDeliveryStatus.PENDING.value,
        nullable=False,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    registration: Mapped[Registration] = relationship(
        back_populates="email_deliveries",
        foreign_keys=[registration_id],
        cascade="save-update, merge",
    )
    ticket: Mapped[Ticket] = relationship(
        foreign_keys=[ticket_id],
        cascade="save-update, merge",
    )
