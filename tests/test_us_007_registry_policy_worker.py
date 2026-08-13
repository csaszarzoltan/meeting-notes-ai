import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from meeting_notes_ai.db.models import Base, Meeting, Team, User
from meeting_notes_ai.services.governance.repository import ArtifactRegistry


@pytest.mark.asyncio
async def test_us_007_ac_1_registry_is_idempotent_with_parent_edge():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    f = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with f() as db:
        u = User(id="u", email="u@example.com", hashed_password="x")
        t = Team(id="t", name="T", owner_id="u")
        m = Meeting(id="m", title="M", user_id="u", team_id="t", filename="a.wav")
        db.add_all([u, t, m])
        await db.flush()
        r = ArtifactRegistry(db)
        root = await r.register(
            team_id="t",
            meeting_id="m",
            kind="audio",
            source_key="audio:m",
            location_class="database",
        )
        child = await r.register(
            team_id="t",
            meeting_id="m",
            kind="transcript",
            source_key="transcript:m:1",
            location_class="database",
            parent_id=root.id,
        )
        again = await r.register(
            team_id="t",
            meeting_id="m",
            kind="transcript",
            source_key="transcript:m:1",
            location_class="database",
            parent_id=root.id,
        )
        assert child.id == again.id
    await engine.dispose()
