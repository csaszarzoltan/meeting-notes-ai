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

    # ── Secure file storage (v0.7.0) — guarded: only seed once the model exists ──
    # StoredFile/StorageFileKind/StorageEncryption are added by the developer
    # task; until then this block no-ops so the existing suite stays green.
    try:
        from meeting_notes_ai.db.models import StorageEncryption, StorageFileKind, StoredFile
    except (ImportError, AttributeError):
        StoredFile = None

    if StoredFile is not None:
        import hashlib

        now = datetime.now(timezone.utc)
        session.add(
            StoredFile(
                id="stored-file-id",
                meeting_id="test-meeting",
                team_id=None,
                uploaded_by="test-user-id",
                kind=StorageFileKind.AUDIO,
                object_key="audio/test-meeting/stored-file-id",
                bucket="local",
                size_bytes=18,
                sha256=hashlib.sha256(b"stored-file-payload").hexdigest(),
                content_type="audio/wav",
                encryption=StorageEncryption.NONE,
                expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            StoredFile(
                id="expired-stored-file-id",
                meeting_id="test-meeting",
                team_id=None,
                uploaded_by="test-user-id",
                kind=StorageFileKind.AUDIO,
                object_key="audio/test-meeting/expired-stored-file-id",
                bucket="local",
                size_bytes=18,
                sha256=hashlib.sha256(b"expired-stored-payload").hexdigest(),
                content_type="audio/wav",
                encryption=StorageEncryption.NONE,
                expires_at=now - timedelta(days=1),
            )
        )


# ── HIPAA test fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def hipaa_config():
    """Provide a default HIPAAConfig for HIPAA module tests."""
    from meeting_notes_ai.hipaa.config import HIPAAConfig

    return HIPAAConfig()


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


# ── Secure file storage fixtures (v0.7.0) ──────────────────────────────────────
# These fixtures are guarded: they skip with a clear "implementation pending"
# reason until the storage backend / StoredFile model are implemented. Once the
# developer task lands, the fixtures activate and provide live objects.


@pytest.fixture
def storage_local_backend(tmp_path):
    """LocalStorageBackend rooted at a temp dir (skips until implemented)."""
    pytest.importorskip(
        "meeting_notes_ai.storage.local",
        reason="implementation pending: meeting_notes_ai/storage/local.py",
    )
    from meeting_notes_ai.storage.local import LocalStorageBackend

    return LocalStorageBackend(str(tmp_path / "storage"))


@pytest.fixture
def storage_encryptor(monkeypatch):
    """FileEncryptor with a deterministic key (skips until implemented)."""
    pytest.importorskip(
        "meeting_notes_ai.storage.encryption",
        reason="implementation pending: meeting_notes_ai/storage/encryption.py",
    )
    monkeypatch.setenv("STORAGE_ENCRYPTION", "aes256gcm")
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", "test-storage-encryption-key")
    from meeting_notes_ai.storage.encryption import FileEncryptor

    return FileEncryptor(mode="aes256gcm")


@pytest.fixture
def stored_file(_setup_test_db, tmp_path):
    """A live StoredFile row (audio) whose bytes live on disk in a temp backend.

    The row belongs to a freshly created meeting owned by test-user-id (no
    team), so tests using it never collide with the conftest-seeded rows.

    Returns a SimpleNamespace(backend, meeting_id, row_id, key, payload).
    Skips until the LocalStorageBackend and StoredFile model are implemented.
    """
    return _make_stored_file(_setup_test_db, tmp_path, team_meeting=False)


@pytest.fixture
def stored_team_file(_setup_test_db, tmp_path):
    """Like stored_file but attached to team-meeting (test-team).

    team-meeting belongs to test-team where viewer-user-id has VIEWER role,
    so it exercises the "viewer may download" RBAC path (AC3).
    """
    return _make_stored_file(_setup_test_db, tmp_path, team_meeting=True)


def _make_stored_file(_setup_test_db, tmp_path, team_meeting: bool):
    """Shared implementation behind the stored_file fixtures."""
    import asyncio
    import hashlib
    from types import SimpleNamespace
    from uuid import uuid4

    pytest.importorskip(
        "meeting_notes_ai.storage.local",
        reason="implementation pending: meeting_notes_ai/storage/local.py",
    )
    try:
        from meeting_notes_ai.storage.local import LocalStorageBackend

        from meeting_notes_ai.db.models import (
            Meeting,
            StorageEncryption,
            StorageFileKind,
            StoredFile,
        )
        from meeting_notes_ai.db.session import get_db_session
    except (ImportError, AttributeError) as exc:  # pragma: no cover - pre-impl
        pytest.skip(f"implementation pending: StoredFile model ({exc})")

    backend_dir = tmp_path / "storage"
    backend = LocalStorageBackend(str(backend_dir))
    meeting_id = "team-meeting" if team_meeting else f"storage-{uuid4().hex[:12]}"
    key = f"audio/{meeting_id}/{uuid4().hex}"
    payload = b"stored-file-payload"
    row_id = str(uuid4())

    async def _seed() -> None:
        await backend.put(key, payload, "audio/wav")
        async for session in get_db_session():
            if not team_meeting:
                session.add(
                    Meeting(
                        id=meeting_id,
                        title="Storage Test Meeting",
                        user_id="test-user-id",
                        filename="storage_test.wav",
                        mode="general",
                        transcript="storage test transcript",
                    )
                )
                await session.flush()
            session.add(
                StoredFile(
                    id=row_id,
                    meeting_id=meeting_id,
                    team_id="test-team" if team_meeting else None,
                    uploaded_by="test-user-id",
                    kind=StorageFileKind.AUDIO,
                    object_key=key,
                    bucket="local",
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    content_type="audio/wav",
                    encryption=StorageEncryption.NONE,
                    expires_at=None,
                )
            )
            await session.commit()

    asyncio.run(_seed())
    return SimpleNamespace(
        backend=backend,
        meeting_id=meeting_id,
        row_id=row_id,
        key=key,
        payload=payload,
    )
