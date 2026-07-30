"""Public meeting sharing endpoint for MeetingNotesAI v0.3.0.

Endpoints:
    GET /public/shares/{token} — Public meeting summary (no auth required)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from meeting_notes_ai.db.models import Meeting, SharedLink
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/public", tags=["public"])


# ── Response Schemas ────────────────────────────────────────────────────────────


class PublicShareResponse(BaseModel):
    title: str | None = None
    transcript: str | None = None
    action_items: str | None = None
    decisions: str | None = None
    key_points: str | None = None
    mode: str | None = None
    metadata: str | None = None


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.get("/shares/{token}", response_model=PublicShareResponse)
async def get_share_by_token(
    token: str,
    db: AsyncSession = Depends(get_db_session),
) -> PublicShareResponse:
    """Get a meeting summary via a public share token.

    No authentication required. Returns 404 if the token is invalid,
    expired, or revoked.
    """
    # Look up the share by token, eagerly loading the meeting
    result = await db.execute(
        select(SharedLink)
        .where(SharedLink.token == token)
        .options(selectinload(SharedLink.meeting))
    )
    share = result.scalar_one_or_none()

    if share is None:
        raise HTTPException(status_code=404, detail="Share link not found")

    # Check if the share has been revoked
    if not share.is_active:
        raise HTTPException(status_code=404, detail="Share link has been revoked")

    # Check if the share has expired
    if share.expires_at is not None and share.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=404, detail="Share link has expired")

    # Return meeting summary
    meeting = share.meeting
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return PublicShareResponse(
        title=meeting.title,
        transcript=meeting.transcript,
        action_items=meeting.action_items,
        decisions=meeting.decisions,
        key_points=meeting.key_points,
        mode=meeting.mode,
        metadata=meeting.metadata_json,
    )
