"""Webhook notification service for MeetingNotesAI v0.2.0.

Handles registering, listing, deleting webhook subscriptions and
firing webhooks on batch completion with retry logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import WebhookEvent, WebhookSubscription
from meeting_notes_ai.db.session import get_db_session


# ── Request/Response Schemas ────────────────────────────────────────────────────


class WebhookSubscriptionCreate(BaseModel):
    url: str
    events: list[WebhookEvent] = [WebhookEvent.BATCH_COMPLETED]
    secret: str | None = None


class WebhookSubscriptionResponse(BaseModel):
    id: str
    team_id: str
    url: str
    events: list[str] = []
    is_active: bool = True
    created_at: datetime | None = None


class WebhookDeliveryResult(BaseModel):
    success: bool
    status_code: int | None = None
    attempts: int = 0
    error: str | None = None


# ── Service Layer ───────────────────────────────────────────────────────────────

# Retry delays in seconds
_RETRY_DELAYS = [5, 15, 30]


async def register_webhook(
    team_id: str,
    url: str,
    events: list[WebhookEvent] | None = None,
    secret: str | None = None,
    db: AsyncSession | None = None,
) -> WebhookSubscriptionResponse:
    """Register a new webhook subscription for a team.

    Args:
        team_id: Team to register the webhook for.
        url: Callback URL to receive webhook payloads.
        events: List of events to subscribe to (default: batch.completed).
        secret: Optional HMAC secret for payload signing.

    Returns:
        WebhookSubscriptionResponse with the created subscription.
    """
    if events is None:
        events = [WebhookEvent.BATCH_COMPLETED]

    events_str = ",".join(e.value for e in events)

    subscription = WebhookSubscription(
        team_id=team_id,
        url=url,
        secret=secret,
        events=events_str,
        is_active=True,
    )

    if db is not None:
        db.add(subscription)
        await db.flush()

    return WebhookSubscriptionResponse(
        id=subscription.id,
        team_id=subscription.team_id,
        url=subscription.url,
        events=[e.strip() for e in subscription.events.split(",")],
        is_active=subscription.is_active,
        created_at=subscription.created_at,
    )


async def list_webhooks(
    team_id: str,
    db: AsyncSession | None = None,
) -> list[WebhookSubscriptionResponse]:
    """List all webhook subscriptions for a team.

    Args:
        team_id: Team identifier.

    Returns:
        List of webhook subscription responses.
    """
    if db is None:
        return []

    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.team_id == team_id)
    )
    subscriptions = result.scalars().all()

    return [
        WebhookSubscriptionResponse(
            id=s.id,
            team_id=s.team_id,
            url=s.url,
            events=[e.strip() for e in s.events.split(",")],
            is_active=s.is_active,
            created_at=s.created_at,
        )
        for s in subscriptions
    ]


async def delete_webhook(
    webhook_id: str,
    db: AsyncSession | None = None,
) -> bool:
    """Delete a webhook subscription.

    Args:
        webhook_id: ID of the webhook to delete.

    Returns:
        True if deleted successfully.
    """
    if db is None:
        return False

    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return False

    await db.delete(subscription)
    await db.flush()
    return True


async def fire_webhook(
    webhook_id: str,
    event: WebhookEvent,
    payload: dict[str, Any],
    db: AsyncSession | None = None,
) -> WebhookDeliveryResult:
    """Fire a webhook with retry logic (3 attempts, exponential backoff).

    Sends a POST request to the webhook URL with the event payload.
    Retries on failure with 5s, 15s, 30s backoff.

    Args:
        webhook_id: Webhook subscription ID.
        event: The event type being fired.
        payload: JSON-serializable payload dict.

    Returns:
        WebhookDeliveryResult with delivery outcome.
    """
    if db is None:
        return WebhookDeliveryResult(success=False, error="No database session")

    # Get webhook subscription
    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return WebhookDeliveryResult(
            success=False,
            error="Webhook subscription not found",
        )

    if not subscription.is_active:
        return WebhookDeliveryResult(success=False, error="Webhook is inactive")

    # Build payload
    body = {
        "event": event.value,
        "data": payload,
    }
    body_bytes = json.dumps(body).encode("utf-8")

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if subscription.secret:
        signature = sign_payload(payload, subscription.secret)
        headers["X-Webhook-Signature"] = signature

    # Send with retries
    last_error = None
    last_status = None

    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    subscription.url,
                    content=body_bytes,
                    headers=headers,
                )
                last_status = response.status_code
                if response.is_success:
                    return WebhookDeliveryResult(
                        success=True,
                        status_code=response.status_code,
                        attempts=attempt + 1,
                    )
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as e:
            last_error = str(e)

        if attempt < len(_RETRY_DELAYS) - 1:
            await asyncio.sleep(delay)

    return WebhookDeliveryResult(
        success=False,
        status_code=last_status,
        attempts=len(_RETRY_DELAYS),
        error=last_error,
    )


async def fire_batch_completed_webhooks(
    batch_id: str,
    team_id: str,
    batch_summary: dict[str, Any],
    db: AsyncSession | None = None,
) -> list[WebhookDeliveryResult]:
    """Fire 'batch.completed' webhooks for all active subscriptions on a team.

    Args:
        batch_id: Completed batch ID.
        team_id: Team that owns the batch.
        batch_summary: Summary payload to send.

    Returns:
        List of delivery results for each subscription.
    """
    if db is None:
        return []

    subscriptions = await list_webhooks(team_id, db=db)
    results = []

    for sub in subscriptions:
        if sub.is_active and WebhookEvent.BATCH_COMPLETED.value in sub.events:
            result = await fire_webhook(
                webhook_id=sub.id,
                event=WebhookEvent.BATCH_COMPLETED,
                payload={"batch_id": batch_id, **batch_summary},
                db=db,
            )
            results.append(result)

    return results


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """Sign a webhook payload with HMAC-SHA256.

    Args:
        payload: The JSON payload to sign.
        secret: HMAC secret key.

    Returns:
        Hex-encoded HMAC-SHA256 signature string.
    """
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return signature
