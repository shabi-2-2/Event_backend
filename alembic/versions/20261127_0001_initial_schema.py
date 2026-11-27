"""initial schema

Revision ID: 20261127_0001
Revises: None
Create Date: 2026-11-27

Creates all domain tables, PostgreSQL native enums, indexes, and constraints
for the event management backend. Raw ticket tokens and webhook payloads are
not stored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261127_0001"
down_revision = None
branch_labels = None
depends_on = None

JSONB_TYPE = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")

event_status = sa.Enum(
    "draft",
    "published",
    "archived",
    "cancelled",
    name="event_status",
    native_enum=True,
    create_constraint=True,
)
registration_status = sa.Enum(
    "registered",
    "checked_in",
    "cancelled",
    name="registration_status",
    native_enum=True,
    create_constraint=True,
)
ticket_status = sa.Enum(
    "active",
    "used",
    "revoked",
    "expired",
    name="ticket_status",
    native_enum=True,
    create_constraint=True,
)
checkin_source = sa.Enum(
    "mobile",
    "admin",
    name="checkin_source",
    native_enum=True,
    create_constraint=True,
)
email_purpose = sa.Enum(
    "ticket_issued",
    "ticket_reissued",
    name="email_purpose",
    native_enum=True,
    create_constraint=True,
)
email_delivery_status = sa.Enum(
    "pending",
    "sent",
    "failed",
    "dead_letter",
    name="email_delivery_status",
    native_enum=True,
    create_constraint=True,
)
webhook_outcome = sa.Enum(
    "registered",
    "duplicate",
    "ignored_declined",
    "rejected",
    name="webhook_outcome",
    native_enum=True,
    create_constraint=True,
)
staff_role = sa.Enum(
    "admin",
    "checkin",
    "viewer",
    name="staff_role",
    native_enum=True,
    create_constraint=True,
)

_ENUM_NAMES = [
    "event_status",
    "registration_status",
    "ticket_status",
    "checkin_source",
    "email_purpose",
    "email_delivery_status",
    "webhook_outcome",
    "staff_role",
]


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("venue", sa.String(200), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            event_status,
            server_default="draft",
            nullable=False,
        ),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("slug", name="uq_events_slug"),
    )
    op.create_index("ix_events_status", "events", ["status"])
    op.create_index("ix_events_starts_at", "events", ["starts_at"])

    op.create_table(
        "attendees",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("urn", sa.String(64), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    op.create_index(
        "uq_attendees_email_lower",
        "attendees",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.create_index(
        "uq_attendees_urn",
        "attendees",
        ["urn"],
        unique=True,
        postgresql_where=sa.text("urn IS NOT NULL"),
        sqlite_where=sa.text("urn IS NOT NULL"),
    )
    op.create_index("ix_attendees_full_name", "attendees", ["full_name"])

    op.create_table(
        "registrations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attendee_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("attendees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_submission_id", sa.String(128), nullable=False),
        sa.Column(
            "status",
            registration_status,
            server_default="registered",
            nullable=False,
        ),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("event_id", "attendee_id", name="uq_registrations_event_attendee"),
        sa.UniqueConstraint(
            "event_id",
            "source_submission_id",
            name="uq_registrations_event_submission",
        ),
    )
    op.create_index("ix_registrations_event_status", "registrations", ["event_id", "status"])
    op.create_index(
        "ix_registrations_event_created_at",
        "registrations",
        ["event_id", "created_at"],
    )
    op.create_index("ix_registrations_attendee_id", "registrations", ["attendee_id"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "registration_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("registrations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("ticket_code", sa.String(64), nullable=False),
        sa.Column("status", ticket_status, server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("registration_id", name="uq_tickets_registration_id"),
        sa.UniqueConstraint("token_hash", name="uq_tickets_token_hash"),
        sa.UniqueConstraint("ticket_code", name="uq_tickets_ticket_code"),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "checkins",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "registration_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("registrations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "checked_in_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("scanned_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("station", sa.String(100), nullable=True),
        sa.Column("source", checkin_source, server_default="mobile", nullable=False),
        sa.Column("metadata", JSONB_TYPE, nullable=False),
        sa.UniqueConstraint("ticket_id", name="uq_checkins_ticket_id"),
    )
    op.create_index("ix_checkins_event_checked_in_at", "checkins", ["event_id", "checked_in_at"])
    op.create_index("ix_checkins_registration_id", "checkins", ["registration_id"])

    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "registration_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("registrations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("purpose", email_purpose, nullable=False),
        sa.Column(
            "status",
            email_delivery_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ticket_id", "purpose", name="uq_email_deliveries_ticket_purpose"),
    )
    op.create_index("ix_email_deliveries_registration_id", "email_deliveries", ["registration_id"])
    op.create_index(
        "ix_email_deliveries_status_next_attempt",
        "email_deliveries",
        ["status", "next_attempt_at"],
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("event_slug", sa.String(100), nullable=False),
        sa.Column("submission_id", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("outcome", webhook_outcome, nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "source",
            "event_slug",
            "submission_id",
            name="uq_webhook_events_source_event_submission",
        ),
    )
    op.create_index(
        "uq_webhook_events_source_request",
        "webhook_events",
        ["source", "request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
        sqlite_where=sa.text("request_id IS NOT NULL"),
    )
    op.create_index("ix_webhook_events_event_slug", "webhook_events", ["event_slug"])
    op.create_index(
        "ix_webhook_events_source_received_at",
        "webhook_events",
        ["source", "received_at"],
    )

    op.create_table(
        "staff_memberships",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", staff_role, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", "event_id"),
    )
    op.create_index("ix_staff_memberships_user_id", "staff_memberships", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=True),
        sa.Column("context", JSONB_TYPE, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_logs_event_created_at", "audit_logs", ["event_id", "created_at"])
    op.create_index(
        "ix_audit_logs_actor_created_at",
        "audit_logs",
        ["actor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_actor_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_staff_memberships_user_id", table_name="staff_memberships")
    op.drop_table("staff_memberships")

    op.drop_index("ix_webhook_events_source_received_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_slug", table_name="webhook_events")
    op.drop_index("uq_webhook_events_source_request", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_email_deliveries_status_next_attempt", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_registration_id", table_name="email_deliveries")
    op.drop_table("email_deliveries")

    op.drop_index("ix_checkins_registration_id", table_name="checkins")
    op.drop_index("ix_checkins_event_checked_in_at", table_name="checkins")
    op.drop_table("checkins")

    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_table("tickets")

    op.drop_index("ix_registrations_attendee_id", table_name="registrations")
    op.drop_index("ix_registrations_event_created_at", table_name="registrations")
    op.drop_index("ix_registrations_event_status", table_name="registrations")
    op.drop_table("registrations")

    op.drop_index("ix_attendees_full_name", table_name="attendees")
    op.drop_index("uq_attendees_urn", table_name="attendees")
    op.drop_index("uq_attendees_email_lower", table_name="attendees")
    op.drop_table("attendees")

    op.drop_index("ix_events_starts_at", table_name="events")
    op.drop_index("ix_events_status", table_name="events")
    op.drop_table("events")

    if op.get_bind().dialect.name == "postgresql":
        for enum_name in reversed(_ENUM_NAMES):
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")
