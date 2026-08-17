"""Add provider and code_verifier columns to oauth_states for PKCE flows.

Revision ID: 20260817_0009
Revises: 20260813_0008
Create Date: 2026-08-17

PM tool OAuth2 flows (Jira, Linear, Asana, Todoist) need to store the
PKCE code_verifier alongside the CSRF state token so it can be retrieved
during the callback exchange.  The ``provider`` column identifies which
OAuth2 flow the state belongs to.  Both columns are nullable so existing
Google Calendar OAuth states (which don't use PKCE) are unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260817_0009"
down_revision = "20260813_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oauth_states", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("oauth_states", sa.Column("code_verifier", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_states", "code_verifier")
    op.drop_column("oauth_states", "provider")
