"""Make meeting google_calendar_event_id unique per (user_id, event_id).

Revision ID: 20260806_0005
Revises: 20260806_0004
Create Date: 2026-08-06

The global unique index on meetings.google_calendar_event_id allowed only one
user to import a given calendar event. Users sharing a calendar (team/shared
calendars) hit an unhandled IntegrityError -> raw 500. Uniqueness now applies
per (user_id, google_calendar_event_id): each user may import an event once,
while different users may each import the same shared event.
"""

from __future__ import annotations

from alembic import op

revision = "20260806_0005"
down_revision = "20260806_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the global unique index on google_calendar_event_id
    op.drop_index("ix_meetings_google_calendar_event_id", table_name="meetings")
    # Composite unique index: one import per (user_id, google_calendar_event_id)
    op.create_index(
        "uq_meetings_user_google_calendar_event",
        "meetings",
        ["user_id", "google_calendar_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_meetings_user_google_calendar_event", table_name="meetings"
    )
    op.create_index(
        "ix_meetings_google_calendar_event_id",
        "meetings",
        ["google_calendar_event_id"],
        unique=True,
    )
