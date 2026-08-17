"""OAuth2 authorization routes for PM tool integrations.

Provides POST /{name}/oauth2/start and GET /{name}/oauth2/callback
for Jira, Linear, Asana, and Todoist OAuth2 flows with PKCE.

All endpoints require JWT/API-key authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.integrations.base import PM_PROVIDERS
from meeting_notes_ai.services.oauth2 import (
    OAUTH2_CONFIGS,
    handle_callback,
    refresh_token,
    start_authorization,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspace/integrations",
    tags=["oauth2"],
)


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class OAuth2StartResponse(BaseModel):
    """Response from POST /{name}/oauth2/start."""

    authorization_url: str = Field(..., description="OAuth2 consent URL to redirect the user to")
    state: str = Field(..., description="CSRF state token")


class OAuth2CallbackResponse(BaseModel):
    """Response from GET /{name}/oauth2/callback."""

    status: str = Field(..., description="Result status")
    provider: str = Field(..., description="Provider name")
    account_email: str = Field("", description="Connected account email")


class OAuth2RefreshResponse(BaseModel):
    """Response from POST /{name}/oauth2/refresh."""

    refreshed: bool = Field(..., description="Whether the token was successfully refreshed")


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/{name}/oauth2/start", response_model=OAuth2StartResponse)
async def oauth2_start(
    name: str,
    redirect_uri: str = Query(..., description="OAuth2 callback URL"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OAuth2StartResponse:
    """Generate an OAuth2 authorization URL with PKCE for a PM provider.

    Stores the CSRF state + PKCE code_verifier in the database.
    The frontend should redirect the user to the returned authorization_url.
    """
    provider = name.lower()
    if provider not in PM_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if provider not in OAUTH2_CONFIGS:
        raise HTTPException(
            status_code=422,
            detail=f"Provider '{provider}' does not support OAuth2",
        )

    try:
        authorization_url, state = await start_authorization(
            provider=provider,
            redirect_uri=redirect_uri,
            user_id=user["user_id"],
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return OAuth2StartResponse(authorization_url=authorization_url, state=state)


@router.get("/{name}/oauth2/callback", response_model=OAuth2CallbackResponse)
async def oauth2_callback(
    name: str,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="CSRF state token"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OAuth2CallbackResponse:
    """Handle OAuth2 callback: exchange code for tokens, store credentials.

    The frontend calls this endpoint after redirecting back from the provider.
    Credentials are encrypted and stored in the pm_integration_tokens table.
    """
    provider = name.lower()
    if provider not in PM_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if provider not in OAUTH2_CONFIGS:
        raise HTTPException(
            status_code=422,
            detail=f"Provider '{provider}' does not support OAuth2",
        )

    try:
        auth = await handle_callback(
            provider=provider,
            code=code,
            state_token=state,
            user_id=user["user_id"],
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return OAuth2CallbackResponse(
        status="connected",
        provider=provider,
        account_email=auth.email,
    )


@router.post("/{name}/oauth2/refresh", response_model=OAuth2RefreshResponse)
async def oauth2_refresh(
    name: str,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OAuth2RefreshResponse:
    """Attempt to refresh an expired OAuth2 token.

    Returns refreshed=True if the token was updated, or refreshed=False
    if re-authorization is required.
    """
    provider = name.lower()
    if provider not in PM_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    refreshed = await refresh_token(
        provider=provider,
        user_id=user["user_id"],
        db=db,
    )

    return OAuth2RefreshResponse(refreshed=refreshed)
