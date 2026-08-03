"""Add live_sessions table for resumable live transcription.

Revision ID: 20260803_0003
Revises: 20260801_0002
Create Date: 2026-08-03

Adds a brand-new ``live_sessions`` table (streaming STT, v0.7.0) that keeps
the durable state of a live transcription session (chunks, partials, status,
HIPAA retention fields) so a session survives client disconnects and can be
resumed. Non-destructive: no existing columns are modified.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260803_0003"
down_revision = "20260801_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id"),
            nullable=True,
        ),
        sa.Column("room_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("chunks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("partials_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("hipaa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("phi_classification", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_live_sessions_meeting_id", "live_sessions", ["meeting_id"])
    op.create_index("ix_live_sessions_user_id", "live_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_live_sessions_user_id", table_name="live_sessions")
    op.drop_index("ix_live_sessions_meeting_id", table_name="live_sessions")
    op.drop_table("live_sessions")
