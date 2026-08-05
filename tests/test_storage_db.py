"""Pre-development tests for the StoredFile DB model + retention column.

Interface tests verify the storage_files table schema (columns, FKs, enums)
and Team.retention_days (nullable, no default). Behavioral tests exercise
CRUD through a real in-memory SQLite session. RED phase: model tests skip
until the developer adds StoredFile/StorageFileKind/StorageEncryption to
meeting_notes_ai/db/models.py.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.quick

try:
    from meeting_notes_ai.db.models import StorageEncryption, StorageFileKind, StoredFile, Team

    _HAS_STORAGE_MODELS = True
except (ImportError, AttributeError):  # pragma: no cover - pre-impl
    StoredFile = StorageEncryption = StorageFileKind = None
    Team = None
    _HAS_STORAGE_MODELS = False


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorageEnums:
    """StorageFileKind / StorageEncryption enum values (brief Section 6.2)."""

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: storage enums")
    def test_storage_file_kind_values(self):
        assert StorageFileKind.AUDIO.value == "audio"
        assert StorageFileKind.TRANSCRIPT.value == "transcript"

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: storage enums")
    def test_storage_encryption_values(self):
        assert StorageEncryption.NONE.value == "none"
        assert StorageEncryption.AES256GCM.value == "aes256gcm"


class TestStoredFileModel:
    """storage_files table contract (brief Section 6.2)."""

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_tablename(self):
        assert StoredFile.__tablename__ == "storage_files"

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_columns(self):
        cols = {c.name for c in StoredFile.__table__.columns}
        expected = {
            "id",
            "meeting_id",
            "team_id",
            "uploaded_by",
            "kind",
            "object_key",
            "bucket",
            "size_bytes",
            "sha256",
            "content_type",
            "encryption",
            "expires_at",
            "deleted_at",
        }
        assert expected <= cols, f"missing columns: {expected - cols}"

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_id_is_primary_key(self):
        assert StoredFile.__table__.columns["id"].primary_key is True

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_meeting_id_is_foreign_key(self):
        fks = list(StoredFile.__table__.columns["meeting_id"].foreign_keys)
        assert any("meetings.id" in str(fk.target_fullname) for fk in fks)

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_uploaded_by_is_foreign_key(self):
        fks = list(StoredFile.__table__.columns["uploaded_by"].foreign_keys)
        assert any("users.id" in str(fk.target_fullname) for fk in fks)

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_team_id_nullable(self):
        assert StoredFile.__table__.columns["team_id"].nullable is True

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_expires_at_and_deleted_at_nullable(self):
        assert StoredFile.__table__.columns["expires_at"].nullable is True
        assert StoredFile.__table__.columns["deleted_at"].nullable is True

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_sha256_length_64(self):
        col = StoredFile.__table__.columns["sha256"]
        assert getattr(col.type, "length", None) == 64

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_meeting_id_indexed(self):
        assert StoredFile.__table__.columns["meeting_id"].index is True


class TestTeamRetentionDays:
    """Team.retention_days must be nullable with no default (NULL = inherit)."""

    _HAS_RETENTION = bool(
        Team is not None and "retention_days" in (Team.__table__.columns if Team else {})
    )

    @pytest.mark.skipif(not _HAS_RETENTION, reason="implementation pending: Team.retention_days")
    def test_retention_days_column_exists(self):
        assert "retention_days" in Team.__table__.columns

    @pytest.mark.skipif(not _HAS_RETENTION, reason="implementation pending: Team.retention_days")
    def test_retention_days_nullable(self):
        assert Team.__table__.columns["retention_days"].nullable is True

    @pytest.mark.skipif(not _HAS_RETENTION, reason="implementation pending: Team.retention_days")
    def test_retention_days_default_is_null(self):
        col = Team.__table__.columns["retention_days"]
        assert col.default is None or col.default.arg is None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (real in-memory SQLite)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStoredFileCrud:
    """CRUD + FK constraint behavior against a live session."""

    @pytest.fixture
    def engine_factory(self):
        from sqlalchemy import event

        from meeting_notes_ai.db.engine import (
            create_db_engine,
            create_session_factory,
            init_db,
        )

        engine = create_db_engine("sqlite+aiosqlite://", echo=False)

        # SQLite does not enforce FKs unless the pragma is set per-connection.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_fk(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async def _setup():
            await init_db(engine)
            factory = create_session_factory(engine)
            async with factory() as session:
                # Fresh engine has no seeded users/meetings; add minimal FK
                # targets so valid StoredFile rows resolve.
                from meeting_notes_ai.db.models import Meeting, User

                session.add(
                    User(
                        id="test-user-id",
                        email="storage-crud@example.com",
                        hashed_password="hash",
                        display_name="CRUD User",
                    )
                )
                session.add(
                    Meeting(
                        id="test-meeting",
                        title="CRUD Meeting",
                        user_id="test-user-id",
                        filename="crud.wav",
                        mode="general",
                    )
                )
                await session.commit()
            return factory

        factory = asyncio.run(_setup())

        yield factory

        asyncio.run(engine.dispose())

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_create_read_update_delete(self, engine_factory):
        async def _run():
            async with engine_factory() as session:
                row = StoredFile(
                    id="crud-file-1",
                    meeting_id="test-meeting",
                    team_id=None,
                    uploaded_by="test-user-id",
                    kind=StorageFileKind.AUDIO,
                    object_key="audio/crud-file-1",
                    bucket="local",
                    size_bytes=5,
                    sha256="0" * 64,
                    content_type="audio/wav",
                    encryption=StorageEncryption.NONE,
                    expires_at=None,
                )
                session.add(row)
                await session.commit()

            async with engine_factory() as session:
                result = await session.execute(
                    select(StoredFile).where(StoredFile.id == "crud-file-1")
                )
                loaded = result.scalar_one_or_none()
                assert loaded is not None
                assert loaded.meeting_id == "test-meeting"
                assert loaded.kind == StorageFileKind.AUDIO
                assert loaded.size_bytes == 5

                loaded.size_bytes = 99
                await session.commit()

            async with engine_factory() as session:
                result = await session.execute(
                    select(StoredFile).where(StoredFile.id == "crud-file-1")
                )
                loaded = result.scalar_one()
                assert loaded.size_bytes == 99

                await session.delete(loaded)
                await session.commit()

            async with engine_factory() as session:
                result = await session.execute(
                    select(StoredFile).where(StoredFile.id == "crud-file-1")
                )
                assert result.scalar_one_or_none() is None

        asyncio.run(_run())

    @pytest.mark.skipif(not _HAS_STORAGE_MODELS, reason="implementation pending: StoredFile model")
    def test_meeting_id_fk_constraint_enforced(self, engine_factory):
        async def _run():
            async with engine_factory() as session:
                bad = StoredFile(
                    id="bad-fk-file",
                    meeting_id="no-such-meeting",
                    uploaded_by="no-such-user",
                    kind=StorageFileKind.AUDIO,
                    object_key="audio/bad",
                    bucket="local",
                    size_bytes=1,
                    sha256="0" * 64,
                    content_type="audio/wav",
                    encryption=StorageEncryption.NONE,
                )
                session.add(bad)
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()

        asyncio.run(_run())
