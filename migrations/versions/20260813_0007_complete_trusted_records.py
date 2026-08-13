"""Complete trusted-record governance schema."""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0007"
down_revision = "20260813_0006"
branch_labels = None
depends_on = None


def stamp():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    ]


def upgrade():
    op.create_table(
        "speaker_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("raw_label", sa.String(120), nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("user_id", sa.String(36)),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        *stamp(),
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("claim_version", sa.Integer, nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("policy_version_id", sa.String(36)),
        *stamp(),
    )
    op.create_table(
        "published_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("policy_version_id", sa.String(36)),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.UniqueConstraint("meeting_id", "version"),
        *stamp(),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("approval_json", sa.Text, nullable=False),
        sa.Column("provider_json", sa.Text, nullable=False),
        sa.Column("storage_json", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("team_id", "version"),
        *stamp(),
    )
    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column(
            "policy_version_id", sa.String(36), sa.ForeignKey("policy_versions.id"), nullable=False
        ),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reasons_json", sa.Text, nullable=False),
        *stamp(),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("location_class", sa.String(32), nullable=False),
        sa.Column("location_ref_encrypted", sa.Text, nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("retention_state", sa.String(32), nullable=False),
        sa.Column("policy_version_id", sa.String(36), sa.ForeignKey("policy_versions.id")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("team_id", "source_key"),
        *stamp(),
    )
    op.create_table(
        "artifact_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False),
        sa.Column("child_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.UniqueConstraint("parent_id", "child_id", "relation_type"),
        *stamp(),
    )
    op.create_table(
        "deletion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("policy_version_id", sa.String(36), sa.ForeignKey("policy_versions.id")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.Text),
        *stamp(),
    )
    op.create_table(
        "deletion_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("deletion_jobs.id"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False),
        sa.Column("outcome", sa.String(48), nullable=False),
        sa.Column("detail_code", sa.String(100)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *stamp(),
    )
    op.create_table(
        "audit_chain_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        *stamp(),
    )
    op.create_table(
        "audit_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("filters_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("terminal_hash", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *stamp(),
    )


def downgrade():
    for name in [
        "audit_exports",
        "audit_chain_events",
        "deletion_results",
        "deletion_jobs",
        "artifact_edges",
        "artifacts",
        "policy_decisions",
        "policy_versions",
        "published_snapshots",
        "review_decisions",
        "speaker_mappings",
    ]:
        op.drop_table(name)
