"""Add Google Calendar integration tables and meeting source tracking.

Revision ID: 20260806_0004
Revises: 20260803_0003
Create Date: 2026-08-06

Adds google_calendar_tokens table, oauth_states table, and meeting source
tracking columns for Google Calendar integration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260806_0004"
down_revision = "20260803_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GoogleCalendarToken table
    op.create_table(
        "google_calendar_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            unique=True,
            nullable=False,
            index=True,
        ),
        sa.Column("encrypted_access_token", sa.Text, nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text, nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "calendar_id", sa.String(255), nullable=False, server_default="primary"
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # OAuthState table
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "state_token", sa.String(100), unique=True, nullable=False, index=True
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "used", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Meeting source tracking columns
    op.add_column(
        "meetings",
        sa.Column("google_calendar_event_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "meetings",
        sa.Column("google_calendar_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "meetings",
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
    )
    op.create_index(
        "ix_meetings_google_calendar_event_id",
        "meetings",
        ["google_calendar_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_meetings_google_calendar_event_id", table_name="meetings")
    op.drop_column("meetings", "source")
    op.drop_column("meetings", "google_calendar_id")
    op.drop_column("meetings", "google_calendar_event_id")
    op.drop_table("oauth_states")
    op.drop_table("google_calendar_tokens")
