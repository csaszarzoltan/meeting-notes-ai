"""Webhook subscription management endpoints for MeetingNotesAI v0.2.0.

Endpoints:
    POST   /api/v1/webhooks              — Register webhook URL
    GET    /api/v1/webhooks              — List registered webhooks
    DELETE /api/v1/webhooks/{webhook_id} — Remove webhook
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.webhooks import (
    WebhookSubscriptionCreate as ServiceWebhookCreate,
    WebhookSubscriptionResponse,
)
from meeting_notes_ai.services import webhooks as wh_service

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.post("", response_model=WebhookSubscriptionResponse, status_code=201)
async def create_webhook(
    request: ServiceWebhookCreate,
    team_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookSubscriptionResponse:
    """Register a new webhook URL for batch completion notifications.

    Args:
        request: Webhook creation payload (url, events, optional secret).
        team_id: Team to register the webhook for.

    Returns:
        WebhookSubscriptionResponse with the created subscription.
    """
    return await wh_service.register_webhook(
        team_id=team_id,
        url=request.url,
        events=request.events,
        secret=request.secret,
        db=db,
    )


@router.get("", response_model=list[WebhookSubscriptionResponse])
async def list_webhooks(
    team_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[WebhookSubscriptionResponse]:
    """List all webhook subscriptions for a team."""
    return await wh_service.list_webhooks(team_id, db=db)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove a webhook subscription by ID."""
    deleted = await wh_service.delete_webhook(webhook_id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
