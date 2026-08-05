"""Team workspace CRUD endpoints for MeetingNotesAI v0.2.0.

Endpoints:
    POST   /api/v1/teams                          — Create team (admin)
    GET    /api/v1/teams                          — List user's teams
    GET    /api/v1/teams/{team_id}                — Get team details
    POST   /api/v1/teams/{team_id}/members        — Invite member
    PATCH  /api/v1/teams/{team_id}/members/{user_id} — Change member role
    DELETE /api/v1/teams/{team_id}/members/{user_id} — Remove member
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import Team, TeamMember, TeamRole, User
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


# ── Request/Response Schemas ────────────────────────────────────────────────────


class TeamCreateRequest(BaseModel):
    name: str
    description: str | None = None


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    owner_id: str
    member_count: int = 0
    created_at: datetime | None = None


class TeamListResponse(BaseModel):
    teams: list[TeamResponse] = []


class MemberResponse(BaseModel):
    user_id: str
    email: str = ""
    display_name: str | None = None
    role: TeamRole = TeamRole.MEMBER
    joined_at: datetime | None = None


class InviteMemberRequest(BaseModel):
    email: str
    role: TeamRole = TeamRole.MEMBER


class ChangeRoleRequest(BaseModel):
    role: TeamRole


# ── Route Handlers ──────────────────────────────────────────────────────────────


def _team_to_response(team: Team, member_count: int = 0) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        owner_id=team.owner_id,
        member_count=member_count,
        created_at=team.created_at,
    )


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    request: TeamCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> TeamResponse:
    """Create a new team. The creator becomes the admin."""
    team = Team(
        name=request.name,
        description=request.description,
        owner_id=user["user_id"],
    )
    db.add(team)
    await db.flush()

    # Add creator as admin member
    member = TeamMember(
        team_id=team.id,
        user_id=user["user_id"],
        role=TeamRole.ADMIN,
    )
    db.add(member)
    await db.flush()

    return _team_to_response(team, member_count=1)


@router.get("", response_model=TeamListResponse)
async def list_teams(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> TeamListResponse:
    """List all teams the current user belongs to."""
    result = await db.execute(select(TeamMember).where(TeamMember.user_id == user["user_id"]))
    memberships = result.scalars().all()
    team_ids = [m.team_id for m in memberships]

    teams = []
    for tid in team_ids:
        team_result = await db.execute(select(Team).where(Team.id == tid))
        team = team_result.scalar_one_or_none()
        if team:
            count_result = await db.execute(select(TeamMember).where(TeamMember.team_id == tid))
            count = len(count_result.scalars().all())
            teams.append(_team_to_response(team, member_count=count))

    return TeamListResponse(teams=teams)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> TeamResponse:
    """Get team details including member list."""
    # Verify membership
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user["user_id"],
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    count_result = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id))
    member_count = len(count_result.scalars().all())

    return _team_to_response(team, member_count=member_count)


async def _require_admin(team_id: str, user_id: str, db: AsyncSession) -> None:
    """Check that user is admin of the given team."""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.role == TeamRole.ADMIN,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/{team_id}/members", response_model=MemberResponse, status_code=201)
async def invite_member(
    team_id: str,
    request: InviteMemberRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Invite a user to the team by email."""
    await _require_admin(team_id, user["user_id"], db)

    # Find user by email
    user_result = await db.execute(select(User).where(User.email == request.email))
    invited_user = user_result.scalar_one_or_none()
    if invited_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already a member
    existing_result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == invited_user.id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User is already a member")

    member = TeamMember(
        team_id=team_id,
        user_id=invited_user.id,
        role=request.role,
    )
    db.add(member)
    await db.flush()

    return MemberResponse(
        user_id=invited_user.id,
        email=invited_user.email,
        display_name=invited_user.display_name,
        role=member.role,
        joined_at=member.created_at,
    )


@router.patch("/{team_id}/members/{member_id}", response_model=MemberResponse)
async def change_member_role(
    team_id: str,
    member_id: str,
    request: ChangeRoleRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Change a team member's role (admin only)."""
    await _require_admin(team_id, user["user_id"], db)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == member_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    member.role = request.role
    await db.flush()

    # Get user details for response
    user_result = await db.execute(select(User).where(User.id == member_id))
    team_user = user_result.scalar_one_or_none()

    return MemberResponse(
        user_id=member.user_id,
        email=team_user.email if team_user else "",
        display_name=team_user.display_name if team_user else None,
        role=member.role,
        joined_at=member.created_at,
    )


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_member(
    team_id: str,
    member_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove a member from the team (admin only)."""
    await _require_admin(team_id, user["user_id"], db)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == member_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    await db.flush()
