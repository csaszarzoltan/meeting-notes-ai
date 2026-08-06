"""Google Calendar OAuth2 integration service.

Handles the full lifecycle: authorization URL generation, token exchange,
token refresh, event listing, and meeting import. All methods are async
and tenant-scoped via the user_id parameter.

Dependencies:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
            access_type="offline",  # request refresh_token
            prompt="consent",  # force consent to get refresh_token
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
