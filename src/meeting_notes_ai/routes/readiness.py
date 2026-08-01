"""Operational readiness probe with a real database round trip."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.session import get_db_session

router = APIRouter(tags=["health"])


@router.get("/readyz", include_in_schema=False)
async def readiness_check(db: AsyncSession = Depends(get_db_session)):
    """Return ready only when the application can execute a database query."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"database": "down"}},
        )
    return {"status": "ready", "checks": {"database": "up"}}
