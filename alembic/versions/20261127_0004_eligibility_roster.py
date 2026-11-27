"""eligibility roster

Revision ID: 20261127_0004
Revises: 20261127_0003
Create Date: 2026-11-27

Adds an event-scoped roster of normalized URNs used for first-year eligibility.
Only the event identifier and normalized URN are stored; no student PII is
persisted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261127_0004"
down_revision = "20261127_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eligibility_rosters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("normalized_urn", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eligibility_rosters"),
    )
    op.create_index(
        "uq_eligibility_rosters_event_urn",
        "eligibility_rosters",
        ["event_id", "normalized_urn"],
        unique=True,
    )
    op.create_index(
        "ix_eligibility_rosters_event_created_at",
        "eligibility_rosters",
        ["event_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eligibility_rosters_event_created_at",
        table_name="eligibility_rosters",
    )
    op.drop_index("uq_eligibility_rosters_event_urn", table_name="eligibility_rosters")
    op.drop_table("eligibility_rosters")
