"""Add storage_files table and teams.retention_days.

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01

Non-destructive: adds a nullable column to ``teams`` and a brand-new
``storage_files`` table (secure file storage, v0.7.0). Safe to run on
any existing v0.6.2 database.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0002"
down_revision = "20260801_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # teams.retention_days — NULL means "inherit" (DEFAULT_RETENTION_DAYS).
    with op.batch_alter_table("teams") as batch:
        batch.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))

    op.create_table(
        "storage_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_by",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.Enum("AUDIO", "TRANSCRIPT", name="storagefilekind"), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("bucket", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column(
            "encryption",
            sa.Enum("NONE", "AES256GCM", name="storageencryption"),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_storage_files_meeting_id", "storage_files", ["meeting_id"])
    op.create_index("ix_storage_files_team_id", "storage_files", ["team_id"])
    op.create_index("ix_storage_files_expires_at", "storage_files", ["expires_at"])
    op.create_index("ix_storage_files_deleted_at", "storage_files", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_storage_files_deleted_at", table_name="storage_files")
    op.drop_index("ix_storage_files_expires_at", table_name="storage_files")
    op.drop_index("ix_storage_files_team_id", table_name="storage_files")
    op.drop_index("ix_storage_files_meeting_id", table_name="storage_files")
    op.drop_table("storage_files")
    with op.batch_alter_table("teams") as batch:
        batch.drop_column("retention_days")
