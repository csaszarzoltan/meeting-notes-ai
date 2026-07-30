"""Shared pytest fixtures for MeetingNotesAI tests.

This conftest provides:
- Sample data fixtures (transcripts, filenames, audiobytes, etc.)
- Database setup (in-memory SQLite) for tests that need a real DB
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.engine import create_db_engine, create_session_factory, init_db
from meeting_notes_ai.db.models import (
    Meeting,
    SharedLink,
    Team,
    TeamMember,
    TeamRole,
    User,
)
from meeting_notes_ai.db.session import set_session_factory

# ── Test DB setup (auto-used for all tests) ─────────────────────────────────────


@pytest.fixture(scope="session")
def _setup_test_db():
    """Set up an in-memory SQLite database for testing.

    Creates the session factory, all tables, and seeds test data
    needed by the sharing behavioral tests.
    """
    import asyncio

    async def _setup():
        engine = create_db_engine("sqlite+aiosqlite://", echo=False)
        factory = create_session_factory(engine)
        set_session_factory(factory)

        await init_db(engine)

        # Seed test data
        async with factory() as session:
            await _seed_test_data(session)
            await session.commit()

        return engine

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    engine = loop.run_until_complete(_setup())
    loop.close()

    yield

    # Teardown
    async def _teardown():
        await engine.dispose()

    loop2 = asyncio.new_event_loop()
    asyncio.set_event_loop(loop2)
    loop2.run_until_complete(_teardown())
    loop2.close()


async def _seed_test_data(session: AsyncSession):
    """Seed the test database with data needed by behavioral tests."""

    # ── Users ──────────────────────────────────────────────────────────────
    users = {
        "test-user-id": User(
            id="test-user-id",
            email="test@example.com",
            hashed_password="hashed_placeholder",
            display_name="Test User",
            is_active=True,
        ),
        "other-user-id": User(
            id="other-user-id",
            email="other@example.com",
            hashed_password="hashed_placeholder",
            display_name="Other User",
            is_active=True,
        ),
        "viewer-user-id": User(
            id="viewer-user-id",
            email="viewer@example.com",
            hashed_password="hashed_placeholder",
            display_name="Viewer User",
            is_active=True,
        ),
        "admin-user-id": User(
            id="admin-user-id",
            email="admin@example.com",
            hashed_password="hashed_placeholder",
            display_name="Admin User",
            is_active=True,
        ),
        "team-owner-id": User(
            id="team-owner-id",
            email="teamowner@example.com",
            hashed_password="hashed_placeholder",
            display_name="Team Owner",
            is_active=True,
        ),
        "restricted-id": User(
            id="restricted-id",
            email="restricted@example.com",
            hashed_password="hashed_placeholder",
            display_name="Restricted User",
            is_active=True,
        ),
    }
    for user in users.values():
        session.add(user)

    # ── Teams ──────────────────────────────────────────────────────────────
    test_team = Team(
        id="test-team",
        name="Test Team",
        description="A test team for unit tests",
        owner_id="team-owner-id",
    )
    session.add(test_team)

    # ── Team Memberships ───────────────────────────────────────────────────
    memberships = [
        TeamMember(team_id="test-team", user_id="team-owner-id", role=TeamRole.ADMIN),
        TeamMember(team_id="test-team", user_id="test-user-id", role=TeamRole.ADMIN),
        TeamMember(team_id="test-team", user_id="viewer-user-id", role=TeamRole.VIEWER),
        TeamMember(team_id="test-team", user_id="admin-user-id", role=TeamRole.ADMIN),
    ]
    for m in memberships:
        session.add(m)

    # ── Meetings ───────────────────────────────────────────────────────────
    meetings = {
        "test-meeting": Meeting(
            id="test-meeting",
            title="Test Meeting",
            user_id="test-user-id",
            team_id=None,
            filename="test_audio.wav",
            mode="general",
            transcript="This is a test meeting transcript.",
            action_items='[{"task": "Do X", "owner": "test-user"}]',
            decisions='["Decision 1"]',
            key_points='["Key point 1"]',
            metadata_json='{"source": "test"}',
        ),
        "team-meeting": Meeting(
            id="team-meeting",
            title="Team Meeting",
            user_id="team-owner-id",
            team_id="test-team",
            filename="team_audio.wav",
            mode="general",
            transcript="Team meeting transcript.",
            action_items='[{"task": "Team task"}]',
            decisions='["Team decision"]',
            key_points='["Team key point"]',
            metadata_json='{"source": "team"}',
        ),
        "empty-meeting": Meeting(
            id="empty-meeting",
            title="Empty Meeting",
            user_id="test-user-id",
            team_id=None,
            filename="empty_audio.wav",
            mode="general",
            transcript="Empty meeting transcript.",
        ),
        "restricted-meeting": Meeting(
            id="restricted-meeting",
            title="Restricted Meeting",
            user_id="restricted-id",
            team_id=None,
            filename="restricted_audio.wav",
            mode="general",
            transcript="Restricted content.",
        ),
        "other-teams-meeting": Meeting(
            id="other-teams-meeting",
            title="Other Meeting",
            user_id="other-user-id",
            team_id=None,
            filename="other_audio.wav",
            mode="general",
            transcript="Other user's meeting.",
        ),
    }
    for meeting in meetings.values():
        session.add(meeting)

    await session.flush()

    # ── Shared Links ───────────────────────────────────────────────────────
    future = datetime.now(timezone.utc) + timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(days=1)

    shared_links = [
        # Active valid link
        SharedLink(
            id="valid-share-id",
            meeting_id="test-meeting",
            team_id=None,
            created_by="test-user-id",
            token="valid-test-token",
            expires_at=future,
            is_active=True,
        ),
        # Token owned by test-user on team meeting
        SharedLink(
            id="creator-owned-share",
            meeting_id="team-meeting",
            team_id="test-team",
            created_by="test-user-id",
            token="creator-owned-token",
            expires_at=future,
            is_active=True,
        ),
        # Share owned by someone else on team meeting (admin can revoke)
        SharedLink(
            id="other-creator-share",
            meeting_id="team-meeting",
            team_id="test-team",
            created_by="other-user-id",
            token="other-creator-token",
            expires_at=future,
            is_active=True,
        ),
        # Share on test-meeting owned by test-user (creator can revoke)
        SharedLink(
            id="test-share-id",
            meeting_id="test-meeting",
            team_id=None,
            created_by="test-user-id",
            token="test-share-token",
            expires_at=future,
            is_active=True,
        ),
        # Expired token
        SharedLink(
            id="expired-share-id",
            meeting_id="test-meeting",
            team_id=None,
            created_by="test-user-id",
            token="expired-test-token",
            expires_at=past,
            is_active=True,
        ),
        # Revoked token
        SharedLink(
            id="revoked-share-id",
            meeting_id="test-meeting",
            team_id=None,
            created_by="test-user-id",
            token="revoked-test-token",
            expires_at=future,
            is_active=False,
        ),
    ]
    for link in shared_links:
        session.add(link)


# ── Existing Sample Data Fixtures ────────────────────────────────────────────────


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """Short valid WAV audio bytes (silence)."""
    return b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"  # noqa: E501


@pytest.fixture
def sample_transcript() -> str:
    """Sample meeting transcript."""
    return (
        "John: Let's discuss the Q3 roadmap.\n"
        "Sarah: I think we should focus on the API integration first.\n"
        "John: Agreed. Mike, can you handle that?\n"
        "Mike: Sure, I'll start next week.\n"
        "Sarah: Great. We also need to decide on the deployment timeline.\n"
        "John: Let's target October 1st for the initial release.\n"
        "Sarah: Works for me.\n"
        "John: OK, action items: Mike owns the API integration, "
        "Sarah owns documentation, I'll handle deployment.\n"
    )


@pytest.fixture
def sample_filename() -> str:
    """Sample audio filename."""
    return "meeting_recording.wav"


@pytest.fixture
def sample_language() -> str:
    """Sample language code."""
    return "en"


@pytest.fixture
def empty_transcript() -> str:
    """Empty transcript edge case."""
    return ""


@pytest.fixture
def sample_patient_id() -> str:
    """Sample patient ID for healthcare tests."""
    return "PAT-2026-0042"


@pytest.fixture
def sample_case_metadata_dict() -> dict:
    """Sample case metadata dict for legal tests."""
    return {
        "case_number": "2026-CV-0042",
        "parties": ["Plaintiff Corp.", "Defendant LLC"],
        "date": "2026-07-15",
        "jurisdiction": "Southern District of New York",
    }


# ── Async helpers ─────────────────────────────────────────────────────────────


@pytest.fixture
def event_loop():
    """Provide an event loop for async tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
