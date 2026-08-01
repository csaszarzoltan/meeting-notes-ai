"""Self-service API key creation, listing, and revocation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import ApiKey
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)


class CreateApiKeyResponse(BaseModel):
    id: str
    key: str
    key_prefix: str
    name: str | None = None
    tier: str
    created_at: datetime | None = None


class ApiKeyItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key_prefix: str
    name: str | None = None
    tier: str
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyItemResponse] = Field(default_factory=list)


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@router.post("", response_model=CreateApiKeyResponse, status_code=201)
async def create_api_key(
    request: CreateApiKeyRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CreateApiKeyResponse:
    plaintext = secrets.token_urlsafe(32)
    record = ApiKey(
        user_id=user["user_id"],
        key_prefix=plaintext[:8],
        hashed_key=_hash_api_key(plaintext),
        tier=user.get("tier", "free"),
        name=request.name,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return CreateApiKeyResponse(
        id=record.id,
        key=plaintext,
        key_prefix=record.key_prefix,
        name=record.name,
        tier=record.tier,
        created_at=record.created_at,
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiKeyListResponse:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user["user_id"], ApiKey.is_active.is_(True))
        .order_by(ApiKey.created_at.desc())
    )
    return ApiKeyListResponse(
        api_keys=[ApiKeyItemResponse.model_validate(item) for item in result.scalars()]
    )


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    record = result.scalar_one_or_none()
    if record is None or record.user_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="API key not found")
    record.is_active = False
    await db.commit()
