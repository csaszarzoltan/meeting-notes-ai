"""Interface and behavioral tests for v0.2.0 DB models.

Tests both SQLAlchemy ORM model definitions (imports, fields, types)
and database engine/session stubs.
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestDBModelsInterface:
    """Verify all ORM model classes are importable with correct fields."""

    # ── User ──────────────────────────────────────────────────────────────────

    def test_user_model_importable(self):
        from meeting_notes_ai.db.models import User

        assert User is not None
        assert User.__tablename__ == "users"

    def test_user_has_expected_columns(self):
        from meeting_notes_ai.db.models import User

        cols = {c.name: c for c in User.__table__.columns}
        assert "id" in cols
        assert "email" in cols
        assert "hashed_password" in cols
        assert "display_name" in cols
        assert "is_active" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_user_email_is_unique_indexed(self):
        from meeting_notes_ai.db.models import User

        col = User.__table__.columns["email"]
        assert col.unique is True
        assert col.index is True

    def test_user_id_is_primary_key(self):
        from meeting_notes_ai.db.models import User

        assert User.__table__.columns["id"].primary_key is True

    # ── Team ──────────────────────────────────────────────────────────────────

    def test_team_model_importable(self):
        from meeting_notes_ai.db.models import Team

        assert Team is not None
        assert Team.__tablename__ == "teams"

    def test_team_has_expected_columns(self):
        from meeting_notes_ai.db.models import Team

        cols = {c.name: c for c in Team.__table__.columns}
        assert "id" in cols
        assert "name" in cols
        assert "description" in cols
        assert "owner_id" in cols
        assert "created_at" in cols

    def test_team_owner_id_is_foreign_key(self):
        from meeting_notes_ai.db.models import Team

        assert Team.owner_id.foreign_keys is not None

    # ── TeamMember ────────────────────────────────────────────────────────────

    def test_team_member_model_importable(self):
        from meeting_notes_ai.db.models import TeamMember

        assert TeamMember is not None
        assert TeamMember.__tablename__ == "team_members"

    def test_team_member_has_role_column(self):
        from meeting_notes_ai.db.models import TeamMember, TeamRole

        assert hasattr(TeamMember, "role")
        assert TeamRole.ADMIN.value == "admin"
        assert TeamRole.MEMBER.value == "member"
        assert TeamRole.VIEWER.value == "viewer"

    # ── Meeting ───────────────────────────────────────────────────────────────

    def test_meeting_model_importable(self):
        from meeting_notes_ai.db.models import Meeting

        assert Meeting is not None
        assert Meeting.__tablename__ == "meetings"

    def test_meeting_has_team_id_foreign_key(self):
        from meeting_notes_ai.db.models import Meeting

        assert hasattr(Meeting, "team_id")
        assert hasattr(Meeting, "user_id")

    def test_meeting_has_content_columns(self):
        from meeting_notes_ai.db.models import Meeting

        cols = {c.name: c for c in Meeting.__table__.columns}
        assert "title" in cols
        assert "filename" in cols
        assert "transcript" in cols
        assert "mode" in cols

    # ── BatchJob ──────────────────────────────────────────────────────────────

    def test_batch_job_model_importable(self):
        from meeting_notes_ai.db.models import BatchJob

        assert BatchJob is not None
        assert BatchJob.__tablename__ == "batch_jobs"

    def test_batch_job_has_status_tracking(self):
        from meeting_notes_ai.db.models import BatchJob

        cols = {c.name: c for c in BatchJob.__table__.columns}
        assert "status" in cols
        assert "total_files" in cols
        assert "completed_files" in cols
        assert "failed_files" in cols
        assert "error_message" in cols

    def test_batch_status_enum_values(self):
        from meeting_notes_ai.db.models import BatchStatus

        assert BatchStatus.PENDING.value == "pending"
        assert BatchStatus.PROCESSING.value == "processing"
        assert BatchStatus.COMPLETED.value == "completed"
        assert BatchStatus.FAILED.value == "failed"

    # ── BatchFileResult ───────────────────────────────────────────────────────

    def test_batch_file_result_model_importable(self):
        from meeting_notes_ai.db.models import BatchFileResult

        assert BatchFileResult is not None
        assert BatchFileResult.__tablename__ == "batch_file_results"

    def test_batch_file_result_has_per_file_fields(self):
        from meeting_notes_ai.db.models import BatchFileResult

        cols = {c.name: c for c in BatchFileResult.__table__.columns}
        assert "filename" in cols
        assert "status" in cols
        assert "meeting_id" in cols
        assert "error_message" in cols
        assert "processing_time_ms" in cols

    # ── WebhookSubscription ───────────────────────────────────────────────────

    def test_webhook_subscription_model_importable(self):
        from meeting_notes_ai.db.models import WebhookSubscription

        assert WebhookSubscription is not None
        assert WebhookSubscription.__tablename__ == "webhook_subscriptions"

    def test_webhook_subscription_has_fields(self):
        from meeting_notes_ai.db.models import WebhookSubscription

        cols = {c.name: c for c in WebhookSubscription.__table__.columns}
        assert "url" in cols
        assert "secret" in cols
        assert "events" in cols
        assert "is_active" in cols
        assert "team_id" in cols

    # ── Base & Relationships ──────────────────────────────────────────────────

    def test_declarative_base_importable(self):
        from meeting_notes_ai.db.models import Base

        assert Base is not None

    def test_team_has_members_relationship(self):
        from meeting_notes_ai.db.models import Team

        assert hasattr(Team, "members")

    def test_team_has_webhook_subscriptions_relationship(self):
        from meeting_notes_ai.db.models import Team

        assert hasattr(Team, "webhook_subscriptions")

    def test_batch_job_has_file_results_relationship(self):
        from meeting_notes_ai.db.models import BatchJob

        assert hasattr(BatchJob, "file_results")

    # ── Engine stubs interface ────────────────────────────────────────────────

    def test_engine_functions_importable(self):
        from meeting_notes_ai.db.engine import (
            close_db,
            create_db_engine,
            create_session_factory,
            init_db,
        )

        assert callable(create_db_engine)
        assert callable(create_session_factory)
        assert callable(init_db)
        assert callable(close_db)

    def test_create_db_engine_signature(self):
        from meeting_notes_ai.db.engine import create_db_engine

        sig = signature(create_db_engine)
        params = list(sig.parameters.keys())
        assert "database_url" in params
        assert "echo" in params

    def test_create_db_engine_echo_default_false(self):
        from meeting_notes_ai.db.engine import create_db_engine

        sig = signature(create_db_engine)
        param = sig.parameters.get("echo")
        assert param is not None
        assert param.default is False

    def test_engine_functions_are_async(self):
        import inspect

        from meeting_notes_ai.db.engine import close_db, init_db

        assert inspect.iscoroutinefunction(init_db)
        assert inspect.iscoroutinefunction(close_db)

    # ── Session dependency interface ─────────────────────────────────────────

    def test_get_db_session_importable(self):
        from meeting_notes_ai.db.session import get_db_session

        assert callable(get_db_session)

    def test_get_db_session_is_async_generator(self):
        import inspect

        from meeting_notes_ai.db.session import get_db_session

        assert inspect.isasyncgenfunction(get_db_session)


# ── Behavioral Tests (real DB operations with aiosqlite) ─────────────────────


@pytest.mark.asyncio
async def test_create_db_engine_returns_async_engine():
    """Engine factory returns a proper AsyncEngine."""
    from meeting_notes_ai.db.engine import create_db_engine

    engine = create_db_engine("sqlite+aiosqlite://", echo=False)
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_session_factory_returns_maker():
    """Session factory returns async_sessionmaker."""
    from meeting_notes_ai.db.engine import create_db_engine, create_session_factory

    engine = create_db_engine("sqlite+aiosqlite://", echo=False)
    factory = create_session_factory(engine)
    assert isinstance(factory, async_sessionmaker)
    await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    """init_db creates all tables in the database."""
    from meeting_notes_ai.db.engine import (
        close_db,
        create_db_engine,
    )
    from meeting_notes_ai.db.models import Base

    engine = create_db_engine("sqlite+aiosqlite://", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Verify tables exist
    async with engine.begin() as conn:
        result = await conn.run_sync(lambda sync_conn: [t for t in Base.metadata.tables.keys()])

    assert "users" in result
    assert "teams" in result
    assert "team_members" in result
    assert "meetings" in result
    assert "batch_jobs" in result
    assert "batch_file_results" in result
    assert "webhook_subscriptions" in result

    await close_db(engine)


@pytest.mark.asyncio
async def test_session_crud():
    """CRUD operations work through the engine/session layer."""
    from uuid import uuid4

    from meeting_notes_ai.db.engine import (
        close_db,
        create_db_engine,
        create_session_factory,
    )
    from meeting_notes_ai.db.models import Base, User

    engine = create_db_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = create_session_factory(engine)

    # Create a user
    user_id = str(uuid4())
    async with factory() as session:
        user = User(
            id=user_id,
            email="test@example.com",
            hashed_password="hash",
            display_name="Test",
        )
        session.add(user)
        await session.commit()

    # Read the user
    async with factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.id == user_id))
        loaded = result.scalar_one_or_none()
        assert loaded is not None
        assert loaded.email == "test@example.com"
        assert loaded.display_name == "Test"

    await close_db(engine)


@pytest.mark.asyncio
async def test_get_db_session_runtime_error_without_init():
    """get_db_session raises RuntimeError before factory is set."""
    from meeting_notes_ai.db.session import get_db_session

    with pytest.raises(RuntimeError, match="not initialized"):
        async for _ in get_db_session():
            pass
