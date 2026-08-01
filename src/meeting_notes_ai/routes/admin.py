"""Administrative user-tier endpoints.

Production deployments should replace the bootstrap token with an identity-provider
admin claim. The explicit environment token keeps the endpoint closed by default.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import User
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class TierChangeRequest(BaseModel):
    tier: Literal["free", "pro", "enterprise"]


class TierUserResponse(BaseModel):
    id: str
    email: str
    tier: str


async def require_admin(authorization: str | None = Header(None)) -> None:
    expected = os.getenv("ADMIN_API_TOKEN")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not supplied or supplied != expected:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.patch("/users/{user_id}/tier", response_model=TierUserResponse)
async def change_user_tier(
    user_id: str,
    request: TierChangeRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> TierUserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.tier = request.tier
    await db.commit()
    return TierUserResponse(id=user.id, email=user.email, tier=user.tier)


@router.get("/users/{user_id}", response_model=TierUserResponse)
async def get_user_admin(
    user_id: str,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> TierUserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return TierUserResponse(id=user.id, email=user.email, tier=user.tier)
