"""rate limit counters

Revision ID: 20261127_0002
Revises: 20261127_0001
Create Date: 2026-11-27

Adds the shared fixed-window counter table used by the Phase 3 rate-limiting
primitives. No Redis service is required.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261127_0002"
down_revision = "20261127_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scope", "subject", "window_start"),
    )
    op.create_index(
        "ix_rate_limit_counters_scope_subject_window",
        "rate_limit_counters",
        ["scope", "subject", "window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_scope_subject_window", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
