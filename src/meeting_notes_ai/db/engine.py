"""Database engine and async session factory for MeetingNotesAI v0.2.0."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meeting_notes_ai.db.models import Base


def create_db_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: Database URL (e.g. sqlite+aiosqlite:///./test.db)
        echo: If True, log all SQL statements.

    Returns:
        Configured AsyncEngine instance.
    """
    return create_async_engine(database_url, echo=echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory from an engine.

    Args:
        engine: The SQLAlchemy AsyncEngine.

    Returns:
        Configured async_sessionmaker.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables defined in Base metadata.

    Args:
        engine: The SQLAlchemy AsyncEngine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db(engine: AsyncEngine) -> None:
    """Dispose the engine, releasing all connections.

    Args:
        engine: The SQLAlchemy AsyncEngine.
    """
    await engine.dispose()
