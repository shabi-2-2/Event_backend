"""Webhook delivery audit and idempotency ledger."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import WebhookOutcome, native_enum, utc_now

if TYPE_CHECKING:
    from app.db.models.event import Event


class WebhookEvent(Base):
    """Metadata for a webhook delivery; raw payloads are never stored."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "event_slug",
            "submission_id",
            name="uq_webhook_events_source_event_submission",
        ),
        Index(
            "uq_webhook_events_source_request",
            "source",
            "request_id",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
            sqlite_where=text("request_id IS NOT NULL"),
        ),
        Index("ix_webhook_events_event_slug", "event_slug"),
        Index("ix_webhook_events_event_slug_outcome", "event_slug", "outcome"),
        Index("ix_webhook_events_source_received_at", "source", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    event_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    submission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[WebhookOutcome] = mapped_column(
        native_enum(WebhookOutcome, "webhook_outcome"),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event | None] = relationship(
        primaryjoin="WebhookEvent.event_slug == foreign(Event.slug)",
        viewonly=True,
        uselist=False,
    )
