"""admin operations

Revision ID: 20261127_0003
Revises: 20261127_0002
Create Date: 2026-11-27

Adds an explicit resend sequence to the email outbox so administrative resends
and retries can create new jobs without modifying historical delivery records.
The original one-job-per-ticket-and-purpose uniqueness rule is replaced by a
sequence-scoped rule. Also adds the aggregate index used by analytics.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261127_0003"
down_revision = "20261127_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_deliveries",
        sa.Column("resend_sequence", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.drop_constraint(
        "uq_email_deliveries_ticket_purpose",
        "email_deliveries",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_email_deliveries_ticket_purpose_sequence",
        "email_deliveries",
        ["ticket_id", "purpose", "resend_sequence"],
    )
    op.create_index(
        "ix_webhook_events_event_slug_outcome",
        "webhook_events",
        ["event_slug", "outcome"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_events_event_slug_outcome", table_name="webhook_events")
    op.drop_constraint(
        "uq_email_deliveries_ticket_purpose_sequence",
        "email_deliveries",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_email_deliveries_ticket_purpose",
        "email_deliveries",
        ["ticket_id", "purpose"],
    )
    op.drop_column("email_deliveries", "resend_sequence")
