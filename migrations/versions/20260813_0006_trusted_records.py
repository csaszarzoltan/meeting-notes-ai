"""Add trusted meeting record tables.

Revision ID: 20260813_0006
Revises: 20260806_0005
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0006"
down_revision = "20260806_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("start_ms", sa.Integer, nullable=False),
        sa.Column("end_ms", sa.Integer, nullable=False),
        sa.Column("raw_speaker_label", sa.String(120), nullable=False),
        sa.Column("speaker_id", sa.String(36)),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column(
            "segment_id", sa.String(36), sa.ForeignKey("transcript_segments.id"), nullable=False
        ),
        sa.Column("start_ms", sa.Integer, nullable=False),
        sa.Column("end_ms", sa.Integer, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("claim_evidence")
    op.drop_table("claims")
    op.drop_table("transcript_segments")
