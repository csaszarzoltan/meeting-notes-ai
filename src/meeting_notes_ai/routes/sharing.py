"""Meeting sharing route handlers for MeetingNotesAI v0.3.0.

Endpoints:
    POST   /api/v1/meetings/{meeting_id}/share           — Generate share link
    GET    /api/v1/meetings/{meeting_id}/shares           — List active shares
    DELETE /api/v1/meetings/{meeting_id}/shares/{share_id} — Revoke a share link
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import Meeting, SharedLink, TeamMember, TeamRole
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/api/v1/meetings", tags=["sharing"])

# ── Request/Response Schemas ────────────────────────────────────────────────────

ALLOWED_EXPIRY = {"1h", "24h", "7d", "never"}

EXPIRY_DELTAS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "never": None,  # permanent
}


class ShareRequest(BaseModel):
    expires_in: str | None = None

    @field_validator("expires_in")
    @classmethod
    def validate_expires_in(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_EXPIRY:
            raise ValueError(f"expires_in must be one of {ALLOWED_EXPIRY}")
        return v


class ShareResponse(BaseModel):
    id: str
    token: str
    url: str
    expires_at: datetime | None = None
    is_active: bool = True
    created_at: datetime | None = None


class ShareListResponse(BaseModel):
    shares: list[ShareResponse] = []


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _generate_share_url(token: str) -> str:
    """Generate the public share URL from a token."""
    # Match the public endpoint path
    return f"/public/shares/{token}"


def _compute_expires_at(expires_in: str | None) -> datetime | None:
    """Compute the expiration datetime from an expires_in string."""
    if expires_in is None or expires_in == "never":
        return None
    delta = EXPIRY_DELTAS.get(expires_in)
    if delta is None:
        return None
    return datetime.now(timezone.utc) + delta


async def _verify_meeting_access(
    meeting_id: str,
    user: dict[str, Any],
    db: AsyncSession,
    require_write: bool = False,
) -> Meeting:
    """Verify the user has access to the meeting.

    Access rules:
    - Meeting owner always has access.
    - Team members with admin/member role can access team meetings.
    - If require_write is True, viewers cannot share (only admin/member).

    Returns the Meeting object on success.

    Raises HTTPException on failure.
    """
    # Look up meeting
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    user_id = user["user_id"]

    # Owner always has access
    if meeting.user_id == user_id:
        return meeting

    # Check team membership
    if meeting.team_id is not None:
        team_result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == meeting.team_id,
                TeamMember.user_id == user_id,
            )
        )
        membership = team_result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=403,
                detail="Not a member of the team that owns this meeting",
            )
        if require_write and membership.role == TeamRole.VIEWER:
            raise HTTPException(
                status_code=403,
                detail="Viewers cannot create share links",
            )
        return meeting

    # No team and not the owner
    raise HTTPException(
        status_code=403,
        detail="You do not have access to this meeting",
    )


async def _verify_share_access(
    meeting_id: str,
    share_id: str,
    user: dict[str, Any],
    db: AsyncSession,
) -> SharedLink:
    """Verify access to a specific share link for revocation.

    Rules:
    - The share's creator can always revoke.
    - Team admins can revoke any share in their team's meeting.

    Returns the SharedLink on success.
    """
    # Verify meeting access first
    await _verify_meeting_access(meeting_id, user, db)

    # Look up the share
    result = await db.execute(
        select(SharedLink).where(
            SharedLink.id == share_id,
            SharedLink.meeting_id == meeting_id,
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=404, detail="Share link not found")

    user_id = user["user_id"]

    # Creator can always revoke
    if share.created_by == user_id:
        return share

    # Team admin can revoke any share
    if share.team_id is not None:
        team_result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == share.team_id,
                TeamMember.user_id == user_id,
                TeamMember.role == TeamRole.ADMIN,
            )
        )
        if team_result.scalar_one_or_none() is not None:
            return share

    raise HTTPException(
        status_code=403,
        detail="Only the creator or a team admin can revoke this share link",
    )


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.post("/{meeting_id}/share", response_model=ShareResponse, status_code=201)
async def create_share_link(
    meeting_id: str,
    request: ShareRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ShareResponse:
    """Generate a share link for a meeting."""
    meeting = await _verify_meeting_access(meeting_id, user, db, require_write=True)
    from meeting_notes_ai.services.share_policy import eligible_snapshot

    snapshot = await eligible_snapshot(db, meeting)

    token = secrets.token_urlsafe(32)
    expires_at = _compute_expires_at(request.expires_in)

    share = SharedLink(
        meeting_id=meeting.id,
        team_id=meeting.team_id,
        created_by=user["user_id"],
        token=token,
        expires_at=expires_at,
        snapshot_id=snapshot.id if snapshot else None,
        policy_version_id=snapshot.policy_version_id if snapshot else None,
    )
    db.add(share)
    await db.flush()
    if snapshot is not None and meeting.team_id:
        from meeting_notes_ai.services.governance.repository import ArtifactRegistry

        await ArtifactRegistry(db).register(
            team_id=meeting.team_id,
            meeting_id=meeting.id,
            kind="share",
            source_key=f"share:{share.id}",
            location_class="database",
            policy_version_id=share.policy_version_id,
            relation_type="shared_as",
        )

    return ShareResponse(
        id=share.id,
        token=token,
        url=_generate_share_url(token),
        expires_at=expires_at,
        is_active=True,
        created_at=share.created_at,
    )


@router.get("/{meeting_id}/shares", response_model=ShareListResponse)
async def list_shares(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ShareListResponse:
    """List active shares for a meeting."""
    await _verify_meeting_access(meeting_id, user, db)

    result = await db.execute(
        select(SharedLink).where(
            SharedLink.meeting_id == meeting_id,
            SharedLink.is_active.is_(True),
        )
    )
    shares = result.scalars().all()

    share_responses = [
        ShareResponse(
            id=s.id,
            token=s.token,
            url=_generate_share_url(s.token),
            expires_at=s.expires_at,
            is_active=s.is_active,
            created_at=s.created_at,
        )
        for s in shares
    ]

    return ShareListResponse(shares=share_responses)


@router.delete("/{meeting_id}/shares/{share_id}", status_code=204)
async def revoke_share_link(
    meeting_id: str,
    share_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Revoke a share link (set is_active=False)."""
    share = await _verify_share_access(meeting_id, share_id, user, db)
    share.is_active = False
    await db.flush()
    return None
