"""Enforce trusted sharing and durable governance jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0008"
down_revision = "20260813_0007"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shared_links") as b:
        b.add_column(sa.Column("snapshot_id", sa.String(36), nullable=True))
        b.add_column(sa.Column("policy_version_id", sa.String(36), nullable=True))
        b.create_foreign_key("fk_share_snapshot", "published_snapshots", ["snapshot_id"], ["id"])
        b.create_foreign_key("fk_share_policy", "policy_versions", ["policy_version_id"], ["id"])
    with op.batch_alter_table("meetings") as b:
        b.add_column(sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("quarantine_job_id", sa.String(36), nullable=True))
    with op.batch_alter_table("artifacts") as b:
        b.add_column(sa.Column("status", sa.String(24), nullable=False, server_default="active"))
        b.add_column(sa.Column("error_code", sa.String(100), nullable=True))
    with op.batch_alter_table("deletion_jobs") as b:
        b.add_column(sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("receipt_json", sa.Text, nullable=True))


def downgrade():
    with op.batch_alter_table("deletion_jobs") as b:
        b.drop_column("receipt_json")
        b.drop_column("attempts")
    with op.batch_alter_table("artifacts") as b:
        b.drop_column("error_code")
        b.drop_column("status")
    with op.batch_alter_table("meetings") as b:
        b.drop_column("quarantine_job_id")
        b.drop_column("quarantined_at")
    with op.batch_alter_table("shared_links") as b:
        b.drop_constraint("fk_share_policy", type_="foreignkey")
        b.drop_constraint("fk_share_snapshot", type_="foreignkey")
        b.drop_column("policy_version_id")
        b.drop_column("snapshot_id")
