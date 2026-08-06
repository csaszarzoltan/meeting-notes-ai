"""Google Calendar OAuth2 integration endpoints.

Provides the full OAuth2 flow (auth URL generation, callback handling),
event listing, event import, connection status, and disconnect.
All endpoints require JWT/API-key authentication and are tenant-scoped.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.config import settings
from meeting_notes_ai.db.models import (
    GoogleCalendarToken,
    Meeting,
    OAuthState,
)
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.google_calendar import (
    GoogleCalendarError,
    GoogleCalendarService,
    TokenExpiredError,
)
from meeting_notes_ai.services.token_encryption import TokenEncryptor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/google-calendar",
    tags=["integrations", "google-calendar"],
)

# ── OAuth state TTL (10 minutes) ────────────────────────────────────────────

_OAUTH_STATE_TTL_MINUTES = 10


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class CalendarAuthResponse(BaseModel):
    """Response from POST /auth — Google OAuth2 authorization URL."""

    authorization_url: str = Field(..., description="Google OAuth2 consent URL")
    state: str = Field(..., description="CSRF state token for callback verification")


class CalendarCallbackResponse(BaseModel):
    """Response from GET /callback — OAuth2 exchange result."""

    connected: bool = Field(default=True)
    calendar_id: str = Field(default="primary")
    expires_at: str | None = Field(default=None)


class CalendarAttendee(BaseModel):
    """Calendar event attendee."""

    email: str
    display_name: str = ""
    response_status: str = ""


class CalendarOrganizer(BaseModel):
    """Calendar event organizer."""

    email: str = ""
    display_name: str = ""


class CalendarEvent(BaseModel):
    """Normalized calendar event."""

    id: str
    summary: str
    description: str = ""
    start: str
    end: str
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    location: str = ""
    meet_link: str | None = None
    organizer: CalendarOrganizer = Field(default_factory=CalendarOrganizer)
    calendar_id: str = "primary"
    html_link: str = ""
    imported: bool = False


class CalendarEventsResponse(BaseModel):
    """Response from GET /events — list of upcoming events."""

    events: list[CalendarEvent]
    calendar_id: str = "primary"
    days: int = 7


class CalendarContext(BaseModel):
    """Context from a calendar event for import."""

    attendees: list[str] = Field(default_factory=list)
    location: str = ""
    meet_link: str | None = None
    description: str = ""


class CalendarImportResponse(BaseModel):
    """Response from POST /import/{event_id} — created meeting record."""

    meeting: dict[str, Any]


class CalendarStatusResponse(BaseModel):
    """Response from GET /status — connection status."""

    connected: bool
    calendar_id: str = "primary"
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
    needs_reauth: bool = False


# ── Internal helpers ─────────────────────────────────────────────────────────


def _get_calendar_service() -> GoogleCalendarService:
    """Create a GoogleCalendarService from app settings."""
    return GoogleCalendarService(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        redirect_uri=settings.google_calendar_redirect_uri,
        encryptor=TokenEncryptor(),
    )


async def _store_oauth_state(state: str, user_id: str, db: AsyncSession) -> None:
    """Store an OAuth state token with a 10-minute TTL."""
    record = OAuthState(
        state_token=state,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=_OAUTH_STATE_TTL_MINUTES),
    )
    db.add(record)
    await db.flush()


async def _verify_oauth_state(state: str, db: AsyncSession) -> str | None:
    """Verify and consume an OAuth state token. Returns user_id or None."""
    result = await db.execute(
        select(OAuthState).where(
            OAuthState.state_token == state,
            OAuthState.used.is_(False),
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    if record.expires_at <= datetime.now(timezone.utc):
        return None
    record.used = True
    await db.flush()
    return record.user_id


async def _load_user_token(
    db: AsyncSession, user_id: str
) -> GoogleCalendarToken | None:
    """Load the active Google Calendar token for a user."""
    result = await db.execute(
        select(GoogleCalendarToken).where(
            GoogleCalendarToken.user_id == user_id,
            GoogleCalendarToken.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _get_imported_event_ids(db: AsyncSession, user_id: str) -> set[str]:
    """Return the set of Google Calendar event IDs already imported by this user."""
    result = await db.execute(
        select(Meeting.google_calendar_event_id).where(
            Meeting.user_id == user_id,
            Meeting.google_calendar_event_id.isnot(None),
        )
    )
    return {row[0] for row in result.all() if row[0]}


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/auth", response_model=CalendarAuthResponse)
async def google_calendar_auth(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CalendarAuthResponse:
    """Generate Google OAuth2 authorization URL with calendar.readonly scope.

    Returns a URL the frontend should redirect the user to for consent.
    The state token is stored for CSRF verification on callback.
    """
    state = secrets.token_urlsafe(32)
    service = _get_calendar_service()
    url = service.get_authorization_url(state=state)
    await _store_oauth_state(state, user["user_id"], db)
    return CalendarAuthResponse(authorization_url=url, state=state)


@router.get("/callback", response_model=CalendarCallbackResponse)
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> CalendarCallbackResponse:
    """Handle Google OAuth2 callback: exchange code, store encrypted tokens."""
    user_id = await _verify_oauth_state(state, db)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    service = _get_calendar_service()
    try:
        tokens = await service.exchange_code(code)
    except Exception as exc:
        logger.warning("Google code exchange failed: %s", exc)
        raise HTTPException(
            status_code=400, detail="Failed to exchange authorization code"
        ) from exc

    encrypted_at = TokenEncryptor().encrypt(tokens["access_token"])
    encrypted_rt = TokenEncryptor().encrypt(tokens["refresh_token"])
    expires_at = tokens.get("expires_at")

    # Parse expires_at string to datetime if present
    token_expires_at = None
    if expires_at:
        try:
            token_expires_at = datetime.fromisoformat(expires_at)
        except (ValueError, TypeError):
            pass

    # Upsert: if user already has a token, update it
    existing = await db.execute(
        select(GoogleCalendarToken).where(
            GoogleCalendarToken.user_id == user_id,
            GoogleCalendarToken.is_active.is_(True),
        )
    )
    record = existing.scalar_one_or_none()
    if record:
        record.encrypted_access_token = encrypted_at
        record.encrypted_refresh_token = encrypted_rt
        record.token_expires_at = token_expires_at
        record.scope = ",".join(tokens.get("scope", []))
        record.is_active = True
        record.disconnected_at = None
    else:
        token_record = GoogleCalendarToken(
            user_id=user_id,
            encrypted_access_token=encrypted_at,
            encrypted_refresh_token=encrypted_rt,
            token_expires_at=token_expires_at,
            scope=",".join(tokens.get("scope", [])),
            is_active=True,
        )
        db.add(token_record)

    await db.flush()
    return CalendarCallbackResponse(
        connected=True,
        calendar_id="primary",
        expires_at=expires_at,
    )


@router.get("/events", response_model=CalendarEventsResponse)
async def list_calendar_events(
    days: int = Query(default=7, ge=1, le=30),
    calendar_id: str = Query(default="primary"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CalendarEventsResponse:
    """List upcoming calendar events for the next N days.

    Automatically refreshes expired tokens. Events already imported
    are marked with ``imported=true``.
    """
    token_record = await _load_user_token(db, user["user_id"])
    if not token_record:
        raise HTTPException(
            status_code=409, detail="Google Calendar not connected"
        )

    service = _get_calendar_service()
    encryptor = service.encryptor
    access_token = encryptor.decrypt(token_record.encrypted_access_token)
    refresh_token = encryptor.decrypt(token_record.encrypted_refresh_token)

    # Auto-refresh if token is expired
    if (
        token_record.token_expires_at
        and token_record.token_expires_at <= datetime.now(timezone.utc)
    ):
        try:
            refreshed = await service.refresh_token(refresh_token)
            access_token = refreshed["access_token"]
            token_record.encrypted_access_token = encryptor.encrypt(access_token)
            if refreshed.get("expires_at"):
                token_record.token_expires_at = datetime.fromisoformat(
                    refreshed["expires_at"]
                )
            await db.flush()
        except TokenExpiredError:
            raise HTTPException(
                status_code=401,
                detail="Google token expired. Please re-authorize.",
            )

    events = await service.list_events(
        access_token=access_token,
        refresh_token=refresh_token,
        calendar_id=calendar_id,
        days_ahead=days,
    )

    # Mark already-imported events
    imported_ids = await _get_imported_event_ids(db, user["user_id"])
    for event in events:
        event["imported"] = event["id"] in imported_ids

    return CalendarEventsResponse(
        events=[CalendarEvent(**e) for e in events],
        calendar_id=calendar_id,
        days=days,
    )


@router.post("/import/{event_id}", response_model=CalendarImportResponse, status_code=201)
async def import_calendar_event(
    event_id: str,
    calendar_id: str = Query(default="primary"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CalendarImportResponse:
    """Create a meeting record from a Google Calendar event.

    Returns 409 if the event has already been imported or the user
    has no connected Google Calendar.
    """
    # Check for duplicate import using the helper
    imported_ids = await _get_imported_event_ids(db, user["user_id"])
    if event_id in imported_ids:
        raise HTTPException(
            status_code=409, detail="This event has already been imported"
        )

    # Load tokens and fetch event
    token_record = await _load_user_token(db, user["user_id"])
    if not token_record:
        raise HTTPException(
            status_code=409, detail="Google Calendar not connected"
        )

    service = _get_calendar_service()
    encryptor = service.encryptor
    access_token = encryptor.decrypt(token_record.encrypted_access_token)
    refresh_token = encryptor.decrypt(token_record.encrypted_refresh_token)

    try:
        event = await service.get_event(
            access_token=access_token,
            refresh_token=refresh_token,
            calendar_id=calendar_id,
            event_id=event_id,
        )
    except GoogleCalendarError as exc:
        raise HTTPException(
            status_code=404, detail=f"Calendar event not found: {exc}"
        )

    # Build meeting record
    attendees = [a["email"] for a in event.get("attendees", []) if a.get("email")]

    meeting = Meeting(
        title=event.get("summary", "Imported meeting"),
        user_id=user["user_id"],
        filename=f"calendar_{event_id}.txt",
        mode="general",
        transcript="",
        action_items=json.dumps([]),
        decisions=json.dumps([]),
        key_points=json.dumps([]),
        metadata_json=json.dumps(
            {
                "calendar_import": True,
                "original_event": event,
            }
        ),
        google_calendar_event_id=event_id,
        google_calendar_id=calendar_id,
        source="calendar_import",
    )

    db.add(meeting)
    await db.flush()

    # Build duration string
    duration = ""
    if event.get("start") and event.get("end"):
        try:
            start_dt = datetime.fromisoformat(event["start"])
            end_dt = datetime.fromisoformat(event["end"])
            delta = end_dt - start_dt
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            duration = f"{hours}h {mins}m" if mins else f"{hours}h"
        except (ValueError, TypeError):
            pass

    return CalendarImportResponse(
        meeting={
            "id": meeting.id,
            "title": meeting.title,
            "source": meeting.source,
            "google_calendar_event_id": event_id,
            "date": event.get("start", ""),
            "duration": duration,
            "participants": len(attendees),
            "review_status": "needs_review",
            "calendar_context": {
                "attendees": attendees,
                "location": event.get("location", ""),
                "meet_link": event.get("meet_link"),
                "description": event.get("description", ""),
            },
        }
    )


@router.get("/status", response_model=CalendarStatusResponse)
async def google_calendar_status(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CalendarStatusResponse:
    """Check Google Calendar connection status for the current user."""
    token_record = await _load_user_token(db, user["user_id"])
    if not token_record:
        return CalendarStatusResponse(connected=False)

    needs_reauth = False
    if (
        token_record.token_expires_at
        and token_record.token_expires_at <= datetime.now(timezone.utc)
    ):
        needs_reauth = True

    return CalendarStatusResponse(
        connected=True,
        calendar_id=token_record.calendar_id,
        connected_at=token_record.created_at,
        token_expires_at=token_record.token_expires_at,
        needs_reauth=needs_reauth,
    )


@router.delete("/disconnect", status_code=204)
async def disconnect_google_calendar(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Disconnect Google Calendar (soft-delete tokens).

    Idempotent: returns 204 even when not connected.
    """
    token_record = await _load_user_token(db, user["user_id"])
    if token_record:
        token_record.is_active = False
        token_record.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
