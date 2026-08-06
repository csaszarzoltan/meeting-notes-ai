# Google Calendar OAuth2 Integration — Architecture Spec

**Version**: 1.0  
**Date**: 2026-08-06  
**Status**: Draft  
**Project**: MeetingNotesAI v1.1.2  

---

## Table of Contents

1. [Overview](#1-overview)
2. [Service Layer Design](#2-service-layer-design)
3. [Data Model](#3-data-model)
4. [API Contract](#4-api-contract)
5. [Security Design](#5-security-design)
6. [Frontend Integration Points](#6-frontend-integration-points)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Overview

This spec designs a Google Calendar integration for MeetingNotesAI that lets
users connect their Google account, browse upcoming meetings, and import
calendar events as meeting records. The integration follows every existing
pattern in the codebase: JWT/API-key auth via `get_current_user`, async
SQLAlchemy models with UUID string PKs, `TimestampMixin`, AES-256-GCM token
encryption, `SSRFProtector` for outbound URLs, and the `workspaceRequest`
client on the frontend.

### Scope

- OAuth2 authorization code flow (Google)
- Encrypted token storage per user (reusing `FileEncryptor` DEK/KEK pattern)
- Automatic token refresh (Google access tokens expire in 1 hour)
- Calendar event listing (next 7 days, default calendar)
- One-click import of a calendar event as a meeting record

### Out of scope (future work)

- Webhook-based real-time event sync
- Multi-calendar support (beyond primary)
- Google Meet link auto-join / live transcription
- Calendar write-back (create/update events from MeetingNotesAI)

---

## 2. Service Layer Design

### New files

```
src/meeting_notes_ai/services/google_calendar.py   # OAuth2 + Calendar API
src/meeting_notes_ai/services/token_encryption.py  # Generic token encrypt/decrypt
```

### 2.1 Token Encryption Service

**File**: `src/meeting_notes_ai/services/token_encryption.py`

Reuses the DEK/KEK envelope pattern from `storage/encryption.py` but
targets short strings (OAuth tokens) rather than large file blobs.

```python
"""Token-level AES-256-GCM envelope encryption.

Lightweight wrapper around the same DEK/KEK pattern used by
FileEncryptor (storage/encryption.py) but designed for short strings
(OAuth access/refresh tokens). Each encrypt() call generates a fresh
DEK, so compromised ciphertexts do not expose other tokens.

Layout (base64-encoded):
    MAGIC(b"MNAT1") || wrapped_dek_len(1B) || wrapped_dek || nonce(12B) || ciphertext
"""

import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from meeting_notes_ai.config import settings

MAGIC = b"MNAT1"
_MAGIC_LEN = 5
_NONCE_LEN = 12
_DEK_LEN = 32
_DEK_AAD = b"MNAT1-DEK"
_PAYLOAD_AAD = b"MNAT1-PAYLOAD"


def _derive_kek(seed: str) -> bytes:
    return hashlib.sha256(seed.encode("utf-8")).digest()


class TokenEncryptor:
    """AES-256-GCM envelope encryptor for OAuth tokens.

    Uses STORAGE_ENCRYPTION_KEY (or HIPAA_MASTER_KEY) as KEK seed,
    matching FileEncryptor's key derivation. Tokens are base64-encoded
    after encryption so they fit cleanly in DB text columns.
    """

    def __init__(self, key: str | None = None) -> None:
        seed = key or settings.storage_encryption_key or os.getenv("HIPAA_MASTER_KEY", "")
        if not seed:
            raise ValueError(
                "TokenEncryptor requires STORAGE_ENCRYPTION_KEY or HIPAA_MASTER_KEY"
            )
        self._kek = _derive_kek(seed)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a token string. Returns base64-encoded ciphertext."""
        dek = os.urandom(_DEK_LEN)
        nonce = os.urandom(_NONCE_LEN)
        cipher = AESGCM(dek)
        wrapped_dek = AESGCM(self._kek).encrypt(nonce, dek, _DEK_AAD)
        ciphertext = cipher.encrypt(nonce, plaintext.encode("utf-8"), _PAYLOAD_AAD)
        raw = MAGIC + bytes([len(wrapped_dek)]) + wrapped_dek + nonce + ciphertext
        return base64.b64encode(raw).decode("ascii")

    def decrypt(self, token_b64: str) -> str:
        """Decrypt a base64-encoded ciphertext. Returns plaintext string."""
        raw = base64.b64decode(token_b64)
        if len(raw) < _MAGIC_LEN + 1 + _NONCE_LEN + 1:
            raise ValueError("token blob too short")
        if raw[:_MAGIC_LEN] != MAGIC:
            raise ValueError("invalid token blob magic")
        dek_len = raw[_MAGIC_LEN]
        nonce_start = _MAGIC_LEN + 1 + dek_len
        wrapped_dek = raw[_MAGIC_LEN + 1 : nonce_start]
        nonce = raw[nonce_start : nonce_start + _NONCE_LEN]
        ciphertext = raw[nonce_start + _NONCE_LEN:]
        dek = AESGCM(self._kek).decrypt(nonce, wrapped_dek, _DEK_AAD)
        return AESGCM(dek).decrypt(nonce, ciphertext, _PAYLOAD_AAD).decode("utf-8")
```

**Design rationale**: Separate from `FileEncryptor` because:
1. Token encryptor returns strings (base64), not bytes
2. Different magic (`MNAT1` vs `MNAS1`) for domain separation
3. Independent lifecycle — token expiry/rotation is independent of file retention

### 2.2 Google Calendar Service

**File**: `src/meeting_notes_ai/services/google_calendar.py`

```python
"""Google Calendar OAuth2 integration service.

Handles the full lifecycle: authorization URL generation, token exchange,
token refresh, event listing, and meeting import. All methods are async
and tenant-scoped via the user_id parameter.

Dependencies:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from meeting_notes_ai.config import settings
from meeting_notes_ai.services.token_encryption import TokenEncryptor

logger = logging.getLogger(__name__)

# Google OAuth2 scopes — minimal for calendar read + event import
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Token lifetime safety margin — refresh 5 minutes before expiry
REFRESH_MARGIN_SECONDS = 300


class GoogleCalendarError(Exception):
    """Base exception for Google Calendar operations."""


class TokenExpiredError(GoogleCalendarError):
    """Raised when tokens cannot be refreshed (user must re-authorize)."""


class GoogleCalendarService:
    """OAuth2 + Calendar API integration for a single user.

    Args:
        client_id: Google OAuth2 client ID.
        client_secret: Google OAuth2 client secret.
        redirect_uri: OAuth2 callback URL.
        encryptor: TokenEncryptor instance for credential storage.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        encryptor: TokenEncryptor,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.encryptor = encryptor

    # ── OAuth2 Flow ────────────────────────────────────────────────────────

    def get_authorization_url(self, state: str) -> str:
        """Generate the Google OAuth2 authorization URL.

        Args:
            state: CSRF protection token (opaque string, stored in session).

        Returns:
            Full Google authorization URL with redirect_uri, scopes, and state.
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=SCOPES,
            state=state,
        )
        flow.redirect_uri = self.redirect_uri
        authorization_url, _ = flow.authorization_url(
            access_type="offline",       # request refresh_token
            prompt="consent",             # force consent to get refresh_token
            include_granted_scopes="true",
        )
        return authorization_url

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for access + refresh tokens.

        Args:
            code: The authorization code from Google's callback.

        Returns:
            Dict with keys: access_token, refresh_token, expires_at, token_type, scope.
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        flow.fetch_token(code=code)

        creds = flow.credentials
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at": creds.expiry.isoformat() if creds.expiry else None,
            "token_type": "Bearer",
            "scope": creds.scopes or SCOPES,
        }

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token.

        Args:
            refresh_token: The stored refresh token.

        Returns:
            Dict with keys: access_token, expires_at, token_type.

        Raises:
            TokenExpiredError: If refresh fails (token revoked or invalid).
        """
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        try:
            from google.auth.transport.requests import Request as AuthRequest
            import asyncio
            # google-auth transport is sync; run in thread to avoid blocking
            await asyncio.to_thread(creds.refresh, AuthRequest())
        except Exception as exc:
            logger.warning("Google token refresh failed: %s", exc)
            raise TokenExpiredError(
                "Could not refresh Google token. Please re-authorize."
            ) from exc

        return {
            "access_token": creds.token,
            "expires_at": creds.expiry.isoformat() if creds.expiry else None,
            "token_type": "Bearer",
        }

    # ── Calendar API ───────────────────────────────────────────────────────

    async def list_events(
        self,
        access_token: str,
        refresh_token: str,
        calendar_id: str = "primary",
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:
        """List upcoming calendar events for the next N days.

        Automatically refreshes the token if expired.

        Args:
            access_token: Current access token.
            refresh_token: Refresh token for automatic renewal.
            calendar_id: Google Calendar ID (default: "primary").
            days_ahead: How many days ahead to look (default: 7).

        Returns:
            List of event dicts with: id, summary, description, start, end,
            attendees, location, meet_link, organizer, calendar_id.
        """
        creds = self._build_credentials(access_token, refresh_token)

        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=days_ahead)

        try:
            service = await asyncio.to_thread(
                lambda: build("calendar", "v3", credentials=creds)
            )
            result = await asyncio.to_thread(
                lambda: service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now.isoformat(),
                    timeMax=time_max.isoformat(),
                    maxResults=100,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 401:
                # Token might need refresh — caller should retry after refresh
                raise TokenExpiredError("Calendar API returned 401") from exc
            raise GoogleCalendarError(f"Calendar API error: {exc}") from exc

        events = result.get("items", [])
        return [self._normalize_event(e) for e in events]

    async def get_event(
        self,
        access_token: str,
        refresh_token: str,
        calendar_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        """Fetch a single calendar event by ID.

        Args:
            access_token: Current access token.
            refresh_token: Refresh token.
            calendar_id: Google Calendar ID.
            event_id: Google Calendar event ID.

        Returns:
            Normalized event dict.
        """
        creds = self._build_credentials(access_token, refresh_token)

        try:
            service = await asyncio.to_thread(
                lambda: build("calendar", "v3", credentials=creds)
            )
            event = await asyncio.to_thread(
                lambda: service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 401:
                raise TokenExpiredError("Calendar API returned 401") from exc
            raise GoogleCalendarError(f"Calendar API error: {exc}") from exc

        return self._normalize_event(event)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _build_credentials(
        self, access_token: str, refresh_token: str
    ) -> Credentials:
        """Build a Google Credentials object from stored tokens."""
        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    def _normalize_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a Google Calendar event into a flat dict."""
        start = raw.get("start", {})
        end = raw.get("end", {})
        # Extract Google Meet link from conferenceData
        meet_link = None
        conf = raw.get("conferenceData", {})
        if conf:
            for entry in conf.get("entryPoints", []):
                if entry.get("entryPointType") == "video":
                    meet_link = entry.get("uri")
                    break

        return {
            "id": raw.get("id", ""),
            "summary": raw.get("summary", "Untitled"),
            "description": raw.get("description", ""),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "attendees": [
                {
                    "email": a.get("email", ""),
                    "displayName": a.get("displayName", ""),
                    "responseStatus": a.get("responseStatus", ""),
                }
                for a in raw.get("attendees", [])
            ],
            "location": raw.get("location", ""),
            "meet_link": meet_link,
            "organizer": {
                "email": raw.get("organizer", {}).get("email", ""),
                "displayName": raw.get("organizer", {}).get("displayName", ""),
            },
            "calendar_id": raw.get("organizer", {}).get("calendarId", "primary"),
            "html_link": raw.get("htmlLink", ""),
        }
```

**Key design decisions**:

1. **`asyncio.to_thread` for Google SDK calls** — The google-api-python-client is
   synchronous. All calls are wrapped in `to_thread` to avoid blocking the FastAPI
   event loop, matching the pattern in `auth.py` (`hash_password`).

2. **Automatic token refresh** — The `list_events` / `get_event` methods accept
   both access and refresh tokens. If the access token is expired, `Credentials`
   handles refresh transparently. If refresh fails, `TokenExpiredError` is raised
   so the caller can prompt re-authorization.

3. **`_normalize_event`** — Flattens Google's nested event structure into a clean
   dict that maps directly to Pydantic response models.

4. **Client config as dict** — Rather than using `client_secrets.json` file, we
   pass the config as a dict built from environment variables. This avoids
   filesystem dependency and matches the app's env-var config pattern.

---

## 3. Data Model

### New model: `GoogleCalendarToken`

**File**: `src/meeting_notes_ai/db/models.py` (append to existing file)

```python
class GoogleCalendarToken(Base, TimestampMixin):
    """Encrypted OAuth2 tokens for Google Calendar integration.

    One row per user. Tokens are encrypted with AES-256-GCM via
    TokenEncryptor before storage. The refresh_token is encrypted
    separately because it's the long-lived credential.

    Access tokens expire after 1 hour; the service layer handles
    transparent refresh using the stored refresh_token.
    """
    __tablename__ = "google_calendar_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    calendar_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="primary"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship()
```

**Design notes**:

- `unique=True` on `user_id` — one Google account per user (matches the 1:1
  pattern of OAuth integrations). To support multiple Google accounts, remove
  unique constraint and add a `provider_account_id` column.
- `encrypted_access_token` and `encrypted_refresh_token` — stored as base64
  strings from `TokenEncryptor.encrypt()`.
- `token_expires_at` — cached from the token exchange response for fast
  "is token expired?" checks without decrypting.
- `is_active` / `disconnected_at` — soft-delete when user disconnects, preserving
  audit trail. A disconnected integration won't appear in event queries.

### Modified model: `Meeting`

Add columns to the existing `Meeting` model to link imported calendar events:

```python
# Add to Meeting class:
google_calendar_event_id: Mapped[Optional[str]] = mapped_column(
    String(255), nullable=True, index=True, unique=True
)
google_calendar_id: Mapped[Optional[str]] = mapped_column(
    String(255), nullable=True
)
source: Mapped[str] = mapped_column(
    String(50), nullable=False, default="upload"
    # Values: "upload", "live", "calendar_import"
)
```

**Design rationale**:

- `google_calendar_event_id` with `unique=True` prevents duplicate imports of
  the same event.
- `source` field on all meetings enables the UI to show where a meeting came
  from. Existing rows default to `"upload"`.

### Alembic Migration

```python
# alembic/versions/0xx_add_google_calendar_integration.py

"""Add Google Calendar integration tables and meeting source tracking.

Revision ID: 0xx
Revises: <previous>
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0xx"
down_revision = "<previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GoogleCalendarToken table
    op.create_table(
        "google_calendar_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"),
                  unique=True, nullable=False, index=True),
        sa.Column("encrypted_access_token", sa.Text, nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text, nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(500), nullable=False, server_default=""),
        sa.Column("calendar_id", sa.String(255), nullable=False, server_default="primary"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Meeting source tracking columns
    op.add_column(
        "meetings",
        sa.Column("google_calendar_event_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "meetings",
        sa.Column("google_calendar_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "meetings",
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
    )
    op.create_index(
        "ix_meetings_google_calendar_event_id",
        "meetings",
        ["google_calendar_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_meetings_google_calendar_event_id", table_name="meetings")
    op.drop_column("meetings", "source")
    op.drop_column("meetings", "google_calendar_id")
    op.drop_column("meetings", "google_calendar_event_id")
    op.drop_table("google_calendar_tokens")
```

---

## 4. API Contract

### New router

**File**: `src/meeting_notes_ai/routes/google_calendar.py`

```
POST   /api/v1/integrations/google-calendar/auth
GET    /api/v1/integrations/google-calendar/callback
GET    /api/v1/integrations/google-calendar/events
POST   /api/v1/integrations/google-calendar/import/{event_id}
GET    /api/v1/integrations/google-calendar/status
DELETE /api/v1/integrations/google-calendar/disconnect
```

All endpoints require `get_current_user` (JWT or API key) and are
tenant-scoped via `user["user_id"]`.

### 4.1 POST /api/v1/integrations/google-calendar/auth

**Purpose**: Generate Google OAuth2 authorization URL.

**Request body**: None (token in header)

**Response** (200):

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&state=...",
  "state": "csrf-token-abc123"
}
```

**Pydantic models**:

```python
class CalendarAuthResponse(BaseModel):
    authorization_url: str = Field(..., description="Google OAuth2 consent URL")
    state: str = Field(..., description="CSRF state token for callback verification")
```

**Implementation**:

```python
@router.post("/auth", response_model=CalendarAuthResponse)
async def google_calendar_auth(user: dict[str, Any] = Depends(get_current_user)):
    state = secrets.token_urlsafe(32)
    # Store state in session/DB for callback verification
    service = _get_calendar_service()
    url = service.get_authorization_url(state=state)
    # Persist state → user_id mapping (short-lived, 10 min TTL)
    await _store_oauth_state(state, user["user_id"])
    return CalendarAuthResponse(authorization_url=url, state=state)
```

### 4.2 GET /api/v1/integrations/google-calendar/callback

**Purpose**: Handle Google OAuth2 callback, exchange code, store tokens.

**Query parameters**:
- `code` (string): Authorization code from Google
- `state` (string): CSRF state token

**Response** (200):

```json
{
  "connected": true,
  "calendar_id": "primary",
  "expires_at": "2026-08-06T15:30:00Z"
}
```

**Pydantic models**:

```python
class CalendarCallbackResponse(BaseModel):
    connected: bool = Field(default=True)
    calendar_id: str = Field(default="primary")
    expires_at: datetime | None = Field(default=None)
```

**Error responses**:
- `400`: Invalid or expired state token
- `400`: Code exchange failed
- `500`: Token storage failed

**Implementation**:

```python
@router.get("/callback", response_model=CalendarCallbackResponse)
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    # 1. Verify state token
    user_id = await _verify_oauth_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # 2. Exchange code for tokens
    service = _get_calendar_service()
    tokens = await service.exchange_code(code)

    # 3. Encrypt and store tokens
    encryptor = TokenEncryptor()
    token_data = GoogleCalendarToken(
        user_id=user_id,
        encrypted_access_token=encryptor.encrypt(tokens["access_token"]),
        encrypted_refresh_token=encryptor.encrypt(tokens["refresh_token"]),
        token_expires_at=tokens["expires_at"],
        scope=",".join(tokens.get("scope", [])),
        is_active=True,
    )

    # Upsert: if user already has a token, update it
    existing = await db.execute(
        select(GoogleCalendarToken).where(
            GoogleCalendarToken.user_id == user_id,
            GoogleCalendarToken.is_active.is_(True),
        )
    )
    record = existing.scalar_one_or_none()
    if record:
        record.encrypted_access_token = token_data.encrypted_access_token
        record.encrypted_refresh_token = token_data.encrypted_refresh_token
        record.token_expires_at = token_data.token_expires_at
        record.scope = token_data.scope
        record.is_active = True
        record.disconnected_at = None
    else:
        db.add(token_data)

    await db.flush()
    return CalendarCallbackResponse(
        connected=True,
        calendar_id="primary",
        expires_at=tokens.get("expires_at"),
    )
```

### 4.3 GET /api/v1/integrations/google-calendar/events

**Purpose**: List upcoming events (next 7 days).

**Query parameters**:
- `days` (int, optional, default=7): Days ahead to look
- `calendar_id` (string, optional, default="primary"): Calendar to query

**Response** (200):

```json
{
  "events": [
    {
      "id": "abc123",
      "summary": "Q3 Planning",
      "description": "Review quarterly goals",
      "start": "2026-08-07T10:00:00+02:00",
      "end": "2026-08-07T11:00:00+02:00",
      "attendees": [
        {
          "email": "alice@example.com",
          "displayName": "Alice",
          "responseStatus": "accepted"
        }
      ],
      "location": "Conference Room A",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "organizer": {
        "email": "bob@example.com",
        "displayName": "Bob"
      },
      "calendar_id": "primary",
      "html_link": "https://calendar.google.com/calendar/event?eid=...",
      "imported": false
    }
  ],
  "calendar_id": "primary",
  "days": 7
}
```

**Pydantic models**:

```python
class CalendarAttendee(BaseModel):
    email: str
    display_name: str = ""
    response_status: str = ""

class CalendarOrganizer(BaseModel):
    email: str = ""
    display_name: str = ""

class CalendarEvent(BaseModel):
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
    imported: bool = False  # True if this event already has a meeting record

class CalendarEventsResponse(BaseModel):
    events: list[CalendarEvent]
    calendar_id: str = "primary"
    days: int = 7
```

**Implementation**:

```python
@router.get("/events", response_model=CalendarEventsResponse)
async def list_calendar_events(
    days: int = Query(default=7, ge=1, le=30),
    calendar_id: str = Query(default="primary"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # 1. Load and decrypt tokens
    token_record = await _load_user_token(db, user["user_id"])
    if not token_record:
        raise HTTPException(status_code=409, detail="Google Calendar not connected")

    encryptor = TokenEncryptor()
    access_token = encryptor.decrypt(token_record.encrypted_access_token)
    refresh_token = encryptor.encrypt(token_record.encrypted_refresh_token)

    # 2. Auto-refresh if expired
    if token_record.token_expires_at and token_record.token_expires_at <= datetime.now(timezone.utc):
        service = _get_calendar_service()
        refreshed = await service.refresh_token(refresh_token)
        access_token = refreshed["access_token"]
        token_record.encrypted_access_token = encryptor.encrypt(access_token)
        token_record.token_expires_at = datetime.fromisoformat(refreshed["expires_at"])
        await db.flush()

    # 3. Fetch events
    service = _get_calendar_service()
    events = await service.list_events(
        access_token=access_token,
        refresh_token=refresh_token,
        calendar_id=calendar_id,
        days_ahead=days,
    )

    # 4. Mark already-imported events
    imported_ids = await _get_imported_event_ids(db, user["user_id"])
    for event in events:
        event["imported"] = event["id"] in imported_ids

    return CalendarEventsResponse(
        events=[CalendarEvent(**e) for e in events],
        calendar_id=calendar_id,
        days=days,
    )
```

### 4.4 POST /api/v1/integrations/google-calendar/import/{event_id}

**Purpose**: Create a meeting record from a calendar event.

**Path parameters**:
- `event_id` (string): Google Calendar event ID

**Request body**: None (optional `calendar_id` in query)

**Query parameters**:
- `calendar_id` (string, optional, default="primary")

**Response** (201):

```json
{
  "meeting": {
    "id": "uuid-uuid-uuid",
    "title": "Q3 Planning",
    "source": "calendar_import",
    "google_calendar_event_id": "abc123",
    "date": "2026-08-07T10:00:00+02:00",
    "duration": "1h",
    "participants": 3,
    "review_status": "needs_review",
    "calendar_context": {
      "attendees": ["alice@example.com", "bob@example.com"],
      "location": "Conference Room A",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "description": "Review quarterly goals"
    }
  }
}
```

**Pydantic models**:

```python
class CalendarContext(BaseModel):
    attendees: list[str] = Field(default_factory=list)
    location: str = ""
    meet_link: str | None = None
    description: str = ""

class CalendarImportResponse(BaseModel):
    meeting: dict[str, Any]  # Full meeting record
```

**Error responses**:
- `404`: Event not found in Google Calendar
- `409`: Event already imported (`google_calendar_event_id` already exists)
- `409`: Google Calendar not connected

**Implementation**:

```python
@router.post("/import/{event_id}", response_model=CalendarImportResponse, status_code=201)
async def import_calendar_event(
    event_id: str,
    calendar_id: str = Query(default="primary"),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # 1. Check for duplicate import
    existing = await db.execute(
        select(Meeting).where(
            Meeting.google_calendar_event_id == event_id,
            Meeting.user_id == user["user_id"],
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This event has already been imported")

    # 2. Load tokens and fetch event
    token_record = await _load_user_token(db, user["user_id"])
    if not token_record:
        raise HTTPException(status_code=409, detail="Google Calendar not connected")

    encryptor = TokenEncryptor()
    access_token = encryptor.decrypt(token_record.encrypted_access_token)
    refresh_token = encryptor.decrypt(token_record.encrypted_refresh_token)

    service = _get_calendar_service()
    event = await service.get_event(
        access_token=access_token,
        refresh_token=refresh_token,
        calendar_id=calendar_id,
        event_id=event_id,
    )

    # 3. Build meeting record
    start_dt = datetime.fromisoformat(event["start"]) if event["start"] else datetime.now(timezone.utc)
    attendees = [a["email"] for a in event.get("attendees", []) if a.get("email")]

    meeting = Meeting(
        title=event.get("summary", "Imported meeting"),
        user_id=user["user_id"],
        filename=f"calendar_{event_id}.txt",
        mode="general",
        transcript="",  # No transcript yet — this is a pre-meeting import
        action_items=json.dumps([]),
        decisions=json.dumps([]),
        key_points=json.dumps([]),
        metadata_json=json.dumps({
            "calendar_import": True,
            "original_event": event,
        }),
        google_calendar_event_id=event_id,
        google_calendar_id=calendar_id,
        source="calendar_import",
        filename=f"calendar_{event_id}.txt",
    )

    db.add(meeting)
    await db.flush()

    # 4. Build response
    duration = ""
    if event.get("start") and event.get("end"):
        start = datetime.fromisoformat(event["start"])
        end = datetime.fromisoformat(event["end"])
        delta = end - start
        hours = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        duration = f"{hours}h {mins}m" if mins else f"{hours}h"

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
```

### 4.5 GET /api/v1/integrations/google-calendar/status

**Purpose**: Check connection status for the current user.

**Response** (200):

```json
{
  "connected": true,
  "calendar_id": "primary",
  "connected_at": "2026-08-06T12:00:00Z",
  "token_expires_at": "2026-08-06T13:00:00Z",
  "needs_reauth": false
}
```

```python
class CalendarStatusResponse(BaseModel):
    connected: bool
    calendar_id: str = "primary"
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
    needs_reauth: bool = False  # True if refresh token is invalid
```

### 4.6 DELETE /api/v1/integrations/google-calendar/disconnect

**Purpose**: Disconnect Google Calendar (soft-delete tokens).

**Response** (204): No content

**Implementation**:

```python
@router.delete("/disconnect", status_code=204)
async def disconnect_google_calendar(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(GoogleCalendarToken).where(
            GoogleCalendarToken.user_id == user["user_id"],
            GoogleCalendarToken.is_active.is_(True),
        )
    )
    record = result.scalar_one_or_none()
    if record:
        record.is_active = False
        record.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
```

### Router registration

In `src/meeting_notes_ai/main.py`, add:

```python
from meeting_notes_ai.routes import google_calendar
app.include_router(google_calendar.router)
```

---

## 5. Security Design

### 5.1 Token Encryption at Rest

- Access and refresh tokens are encrypted with AES-256-GCM before DB storage
- Uses the same `STORAGE_ENCRYPTION_KEY` / `HIPAA_MASTER_KEY` as file encryption
- Each token gets a fresh random DEK (compromised ciphertext ≠ compromised key)
- Domain-separated magic (`MNAT1` vs `MNAS1`) prevents cross-domain decryption
- Base64 encoding keeps encrypted tokens in text-safe DB columns

### 5.2 OAuth2 CSRF Protection

- `state` parameter is a `secrets.token_urlsafe(32)` value
- Stored with the user's ID and a 10-minute TTL in a `oauth_states` table
- Verified on callback; invalid/expired state returns `400`
- State is single-use: deleted after successful exchange

### 5.3 SSRF Protection

Google API URLs are validated via `SSRFProtector` (existing `security.py`):

```python
from meeting_notes_ai.security import SSRFProtector

_protector = SSRFProtector()

# Before any API call to Google:
# 1. Validate token endpoint URL
assert _protector.validate_url("https://oauth2.googleapis.com/token")

# 2. Validate calendar API base URL
assert _protector.validate_url("https://www.googleapis.com/calendar/v3")
```

Google's official endpoints (`*.googleapis.com`) are HTTPS-only, which
passes the `ALLOWED_SCHEMES` check. The SSRF protector blocks any
user-supplied calendar_id or URL that resolves to private ranges.

### 5.4 Tenant Isolation

All calendar operations are scoped to `user["user_id"]`:

- Token lookup: `WHERE user_id = :user_id`
- Event import: `WHERE user_id = :user_id AND google_calendar_event_id = :event_id`
- Status check: `WHERE user_id = :user_id AND is_active = true`
- No cross-user calendar access is possible — the OAuth tokens belong to
  one user and the DB enforces ownership

### 5.5 Google API Security

- **Minimal scopes**: Only `calendar.readonly` is requested — no write access
- **Offline access**: `access_type="offline"` + `prompt="consent"` ensures
  we get a refresh_token on first auth
- **Token refresh**: Handled server-side, never exposed to the frontend
- **HTTPS only**: All Google API calls use HTTPS (enforced by google-api-python-client)

### 5.6 State Management

OAuth states are stored in a lightweight table to support concurrent users:

```python
class OAuthState(Base, TimestampMixin):
    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    state_token: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False)
```

States expire after 10 minutes and are cleaned up by a periodic sweep
(or lazily on read).

---

## 6. Frontend Integration Points

### 6.1 API Client Extensions

**File**: `frontend/src/api/googleCalendar.ts` (new file)

```typescript
/** Google Calendar integration API client. */
import { workspaceRequest } from './workspace';

export interface CalendarEvent {
  id: string;
  summary: string;
  description: string;
  start: string;
  end: string;
  attendees: Array<{ email: string; display_name: string; response_status: string }>;
  location: string;
  meet_link: string | null;
  organizer: { email: string; display_name: string };
  calendar_id: string;
  html_link: string;
  imported: boolean;
}

export interface CalendarStatus {
  connected: boolean;
  calendar_id: string;
  connected_at: string | null;
  token_expires_at: string | null;
  needs_reauth: boolean;
}

export interface ImportResult {
  meeting: {
    id: string;
    title: string;
    source: string;
    google_calendar_event_id: string;
    date: string;
    duration: string;
    participants: number;
    review_status: string;
    calendar_context: {
      attendees: string[];
      location: string;
      meet_link: string | null;
      description: string;
    };
  };
}

const CALENDAR_BASE = '/api/v1/integrations/google-calendar';

/** Get authorization URL to start OAuth flow. */
export async function getAuthUrl(): Promise<{ authorization_url: string; state: string }> {
  const response = await fetch(`${CALENDAR_BASE}/auth`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${sessionStorage.getItem('workspace_token') ?? ''}`,
    },
  });
  if (!response.ok) throw new Error('Failed to start Google Calendar authorization');
  return response.json();
}

/** Get connection status. */
export async function getCalendarStatus(): Promise<CalendarStatus> {
  return workspaceRequest<CalendarStatus>('/integrations/google-calendar/status');
}

/** List upcoming events. */
export async function listEvents(days = 7): Promise<{ events: CalendarEvent[]; calendar_id: string }> {
  return workspaceRequest(`/integrations/google-calendar/events?days=${days}`);
}

/** Import a calendar event as a meeting. */
export async function importEvent(eventId: string, calendarId = 'primary'): Promise<ImportResult> {
  return workspaceRequest(`/integrations/google-calendar/import/${eventId}?calendar_id=${calendarId}`, {
    method: 'POST',
  });
}

/** Disconnect Google Calendar. */
export async function disconnectCalendar(): Promise<void> {
  await workspaceRequest('/integrations/google-calendar/disconnect', { method: 'DELETE' });
}
```

### 6.2 MeetingSetup.tsx Changes

The existing `CAPTURE` array already includes `'Import calendar meeting'`.
The current implementation disables it. Changes:

1. **Enable the calendar import capture option** — When selected, show a
   calendar event picker instead of the file upload form.

2. **Add calendar event picker component**:

```typescript
// In MeetingSetup.tsx, replace the disabled state with:

if (capture === 'Import calendar meeting') {
  return <CalendarEventPicker onComplete={onComplete} />;
}
```

3. **New component**: `CalendarEventPicker.tsx` (in `frontend/src/workspace/`)

```typescript
/** Calendar event selection and import flow. */
export function CalendarEventPicker({ onComplete }: { onComplete: (result: MeetingResult) => void }) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState<string | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    getCalendarStatus()
      .then(status => {
        setConnected(status.connected);
        if (status.connected) return listEvents(7);
        return null;
      })
      .then(data => {
        if (data) setEvents(data.events);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const handleConnect = async () => {
    const { authorization_url } = await getAuthUrl();
    window.location.href = authorization_url;
  };

  const handleImport = async (eventId: string) => {
    setImporting(eventId);
    try {
      const result = await importEvent(eventId);
      onComplete(result.meeting as MeetingResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setImporting(null);
    }
  };

  if (connected === false) {
    return (
      <section className="calendar-connect">
        <div className="page-heading centered">
          <span className="eyebrow">Calendar integration</span>
          <h2>Connect your Google Calendar</h2>
          <p>Browse upcoming meetings and import them with one click.</p>
        </div>
        <button className="primary large" onClick={handleConnect}>
          Connect Google Calendar →
        </button>
      </section>
    );
  }

  return (
    <section className="calendar-events">
      <div className="page-heading">
        <span className="eyebrow">Calendar import</span>
        <h2>Upcoming meetings (7 days)</h2>
      </div>
      {loading && <SkeletonGrid />}
      {error && <div className="error-banner">{error}</div>}
      <div className="event-list">
        {events.map(event => (
          <article key={event.id} className="event-card">
            <div className="event-time">
              <strong>{new Date(event.start).toLocaleDateString()}</strong>
              <small>{new Date(event.start).toLocaleTimeString()} — {new Date(event.end).toLocaleTimeString()}</small>
            </div>
            <div className="event-details">
              <h3>{event.summary}</h3>
              <p>{event.description || 'No description'}</p>
              <small>{event.attendees.length} attendees · {event.location || 'No location'}</small>
            </div>
            <button
              className={event.imported ? 'secondary' : 'primary'}
              disabled={event.imported || importing === event.id}
              onClick={() => handleImport(event.id)}
            >
              {event.imported ? '✓ Imported' : importing === event.id ? 'Importing…' : 'Import →'}
            </button>
          </article>
        ))}
        {events.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No upcoming meetings</h3>
            <p>Your calendar is clear for the next 7 days.</p>
          </div>
        )}
      </div>
    </section>
  );
}
```

### 6.3 UploadFlow.tsx Changes

The upload flow tab bar already has `'◇ Import calendar'` as the third tab.
When this tab is selected, render the `CalendarEventPicker` component
instead of the upload form:

```typescript
// In UploadFlow.tsx, add a third tab handler:
const [activeTab, setActiveTab] = useState<'upload' | 'record' | 'calendar'>('upload');

// In the tab bar:
<button onClick={() => setActiveTab('calendar')}>◇ Import calendar</button>

// Conditional render:
{activeTab === 'calendar' && <CalendarEventPicker onComplete={onComplete} />}
```

### 6.4 Dashboard.tsx Changes

1. **Add calendar status widget** — Show a "Connected" badge or
   "Connect Calendar" CTA in the onboarding section.

2. **Enhance metric grid** — Add a "Calendar events" metric when connected:

```typescript
// In the metric grid, conditionally show:
{calendarStatus?.connected && (
  <article>
    <span className="metric-icon amber">◇</span>
    <div>
      <small>Calendar events</small>
      <strong>{calendarEventCount}</strong>
      <em>Next 7 days</em>
    </div>
  </article>
)}
```

3. **Update onboarding checklist** — The existing "Connect your calendar"
   step is already marked as done. When the user connects, update the
   workspace state to reflect this.

### 6.5 IntegrationsCenter.tsx Changes

Add Google Calendar as a first-class integration with connection status:

```typescript
// Replace the generic integration card with a rich one for Google Calendar:
{items['Google Calendar'] && (
  <article className="integration-card featured">
    <span className="integration-logo">G</span>
    <div>
      <h3>Google Calendar</h3>
      <p>{items['Google Calendar'].connected ? 'Connected · Syncing events' : 'Browse and import meetings'}</p>
    </div>
    <button
      className={items['Google Calendar'].connected ? 'secondary' : 'primary'}
      onClick={() => items['Google Calendar'].connected ? handleDisconnect() : handleConnect()}
    >
      {items['Google Calendar'].connected ? 'Disconnect' : 'Connect'}
    </button>
  </article>
)}
```

---

## 7. Implementation Roadmap

### Phase 1: Backend Foundation (estimated: 2-3 days)

| # | Task | Dependencies | Profile |
|---|------|-------------|---------|
| 1.1 | Add `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` to `pyproject.toml` | None | developer |
| 1.2 | Create `TokenEncryptor` in `services/token_encryption.py` | None | developer |
| 1.3 | Add `GoogleCalendarToken` and `OAuthState` models to `db/models.py` | None | developer |
| 1.4 | Create Alembic migration for new tables + Meeting columns | 1.3 | developer |
| 1.5 | Write unit tests for `TokenEncryptor` (encrypt/decrypt round-trip, invalid input) | 1.2 | developer |

### Phase 2: Service Layer (estimated: 2-3 days)

| # | Task | Dependencies | Profile |
|---|------|-------------|---------|
| 2.1 | Create `GoogleCalendarService` in `services/google_calendar.py` | 1.1, 1.2 | developer |
| 2.2 | Add Google OAuth env vars to `config.py` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`) | None | developer |
| 2.3 | Write unit tests for OAuth flow (mock google transport) | 2.1 | developer |
| 2.4 | Write unit tests for calendar event listing (mock API responses) | 2.1 | developer |

### Phase 3: API Routes (estimated: 2-3 days)

| # | Task | Dependencies | Profile |
|---|------|-------------|---------|
| 3.1 | Create `routes/google_calendar.py` with auth, callback, events, import endpoints | 2.1 | developer |
| 3.2 | Add SSRF validation on Google API URLs | 3.1 | developer |
| 3.3 | Register router in `main.py` | 3.1 | developer |
| 3.4 | Write integration tests for all 6 endpoints | 3.1, 3.3 | developer |
| 3.5 | Update workspace integration list to include Google Calendar | 3.1 | developer |

### Phase 4: Frontend (estimated: 2-3 days)

| # | Task | Dependencies | Profile |
|---|------|-------------|---------|
| 4.1 | Create `api/googleCalendar.ts` API client | 3.1 | developer |
| 4.2 | Create `CalendarEventPicker.tsx` component | 4.1 | developer |
| 4.3 | Update `MeetingSetup.tsx` to enable calendar import option | 4.2 | developer |
| 4.4 | Update `UploadFlow.tsx` with calendar tab | 4.2 | developer |
| 4.5 | Update `Dashboard.tsx` with calendar status widget | 4.1 | developer |
| 4.6 | Update `IntegrationsCenter.tsx` with Google Calendar card | 4.1 | developer |
| 4.7 | Add CSS styles for calendar components | 4.2-4.6 | developer |

### Phase 5: Polish & QA (estimated: 1-2 days)

| # | Task | Dependencies | Profile |
|---|------|-------------|---------|
| 5.1 | E2E test: OAuth flow (start → callback → events → import) | All | pre-tester |
| 5.2 | Security review: token encryption, CSRF, tenant isolation | All | pre-tester |
| 5.3 | Error handling audit: expired tokens, revoked access, network failures | All | pre-tester |
| 5.4 | Documentation: update README with Google Calendar setup instructions | All | developer |
| 5.5 | Lint pass and type checking (`mypy`, `ruff`) | All | pre-tester |

### Dependencies graph

```
1.1 → 2.1 → 3.1 → 3.3 → 4.1 → 4.2 → 4.3, 4.4
                              ↓
                            4.5, 4.6
1.2 → 1.5 (tests only)
1.3 → 1.4
2.2 (independent)
2.1 → 2.3, 2.4 (tests only)
3.1 → 3.2, 3.4, 3.5
```

### Environment variables to add

```bash
# Google Calendar OAuth2 (required for integration)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://your-domain.com/api/v1/integrations/google-calendar/callback
```

---

## Appendix: File Manifest

### New files to create

| Path | Purpose |
|------|---------|
| `src/meeting_notes_ai/services/token_encryption.py` | AES-256-GCM token encrypt/decrypt |
| `src/meeting_notes_ai/services/google_calendar.py` | OAuth2 + Calendar API service |
| `src/meeting_notes_ai/routes/google_calendar.py` | 6 API endpoints |
| `alembic/versions/0xx_add_google_calendar.py` | DB migration |
| `frontend/src/api/googleCalendar.ts` | Frontend API client |
| `frontend/src/workspace/CalendarEventPicker.tsx` | Event picker component |

### Files to modify

| Path | Change |
|------|--------|
| `pyproject.toml` | Add google-api-python-client deps |
| `src/meeting_notes_ai/config.py` | Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI |
| `src/meeting_notes_ai/db/models.py` | Add GoogleCalendarToken, OAuthState; extend Meeting |
| `src/meeting_notes_ai/main.py` | Register google_calendar router |
| `src/meeting_notes_ai/routes/workspace.py` | Add Google Calendar to integrations list |
| `frontend/src/workspace/MeetingSetup.tsx` | Enable calendar import capture option |
| `frontend/src/workspace/UploadFlow.tsx` | Add calendar tab |
| `frontend/src/workspace/Dashboard.tsx` | Add calendar status widget |
| `frontend/src/workspace/IntegrationsCenter.tsx` | Add Google Calendar card |
