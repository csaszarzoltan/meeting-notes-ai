"""Async database session dependency for FastAPI."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_notes_ai.db.engine import create_session_factory

# Will be set during app startup
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def set_session_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    """Set the global session factory (called during app startup)."""
    global _session_factory
    _session_factory = factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage in routes:
        @router.post("/items")
        async def create_item(db: AsyncSession = Depends(get_db_session)):
            ...

    Yields:
        An AsyncSession that is committed/rolled back on exit.
    """
    if _session_factory is None:
        raise RuntimeError("Database session factory not initialized. Call init_db first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
