"""Pre-development interface and behavioral tests for Google Calendar OAuth2 integration.

Tests the contract of the Calendar integration: service classes, router,
Pydantic schemas, API endpoints, tenant isolation, token refresh, and SSRF
protection. All tests are expected to FAIL until the feature is implemented
(RED phase).

Endpoints under test:
  POST   /api/v1/integrations/google-calendar/auth
  GET    /api/v1/integrations/google-calendar/callback
  GET    /api/v1/integrations/google-calendar/events
  POST   /api/v1/integrations/google-calendar/import/{event_id}
  GET    /api/v1/integrations/google-calendar/status
  DELETE /api/v1/integrations/google-calendar/disconnect
"""

from __future__ import annotations

from datetime import datetime, timezone
from inspect import signature
from typing import Any

import pytest

# Mark all tests in this module as integration (uses TestClient / AsyncClient)
pytestmark = pytest.mark.integration

from fastapi import FastAPI, Header
from pydantic import BaseModel

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.main import app

# ── Auth override fixture (required by all behavioral tests) ──────────────────

_DEFAULT_USER = {
    "user_id": "test-user-id",
    "email": "test@example.com",
    "display_name": "Test User",
}


@pytest.fixture(autouse=True)
def _mock_auth(_setup_test_db):
    """Override get_current_user so behavioral tests don't need real JWTs.

    Also ensures the in-memory test DB (session factory) is initialized for
    every test in this module, since the behavioral tests hit real routes
    that depend on get_db_session.

    Routes users by the Bearer token so per-user tests work:
    - "token-user-a" -> user_id "user-a"
    - "token-user-b" -> user_id "user-b"
    - anything else   -> _DEFAULT_USER
    """

    def _fake_get_current_user(
        authorization: str = Header(default="Bearer test-token"),
    ) -> dict[str, Any]:
        token = authorization.removeprefix("Bearer ").strip()
        if token == "token-user-a":
            return {"user_id": "user-a", "email": "usera@example.com", "display_name": "User A"}
        if token == "token-user-b":
            return {"user_id": "user-b", "email": "userb@example.com", "display_name": "User B"}
        return _DEFAULT_USER

    app.dependency_overrides[get_current_user] = _fake_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mock_token_encryptor(monkeypatch: pytest.MonkeyPatch):
    """Make TokenEncryptor.decrypt a passthrough for mock tokens."""
    from meeting_notes_ai.config import settings

    monkeypatch.setattr(settings, "storage_encryption_key", "test-key-for-calendar-integration")
    from meeting_notes_ai.services import token_encryption

    original_decrypt = token_encryption.TokenEncryptor.decrypt

    def _passthrough_encrypt(self, plaintext: str) -> str:
        return f"encrypted:{plaintext}"

    def _passthrough_decrypt(self, token_b64: str) -> str:
        if token_b64.startswith("encrypted:"):
            return token_b64[len("encrypted:") :]
        return original_decrypt(self, token_b64)

    monkeypatch.setattr(token_encryption.TokenEncryptor, "encrypt", _passthrough_encrypt)
    monkeypatch.setattr(token_encryption.TokenEncryptor, "decrypt", _passthrough_decrypt)
    yield


# ── Helpers ────────────────────────────────────────────────────────────────────


def _collect_routes(fastapi_app: FastAPI) -> list:
    """Collect all APIRoute objects, traversing _IncludedRouter wrappers."""
    collected = []
    for r in fastapi_app.routes:
        if type(r).__name__ == "_IncludedRouter":
            collected.extend(r.original_router.routes)
        elif hasattr(r, "path"):
            collected.append(r)
    return collected


def _find_route(fastapi_app: FastAPI, path_snippet: str):
    """Find an APIRoute by a substring of its path."""
    for r in _collect_routes(fastapi_app):
        if path_snippet in r.path:
            return r
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS once implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenEncryptionInterface:
    """Verify TokenEncryptor service class structure."""

    def test_token_encryptor_importable(self):
        """TokenEncryptor class exists in services module."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        assert TokenEncryptor is not None

    def test_token_encryptor_is_class(self):
        """TokenEncryptor is a regular class (not a function or alias)."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        assert isinstance(TokenEncryptor, type)

    def test_token_encryptor_init_signature(self):
        """TokenEncryptor.__init__ accepts an optional key parameter."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        sig = signature(TokenEncryptor.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        # Should accept a key parameter (optional)
        assert "key" in params

    def test_token_encryptor_has_encrypt_method(self):
        """TokenEncryptor has an encrypt() method."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        assert hasattr(TokenEncryptor, "encrypt")
        assert callable(TokenEncryptor.encrypt)

    def test_token_encryptor_has_decrypt_method(self):
        """TokenEncryptor has a decrypt() method."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        assert hasattr(TokenEncryptor, "decrypt")
        assert callable(TokenEncryptor.decrypt)

    def test_encrypt_returns_string(self):
        """encrypt() return type annotation is str."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        sig = signature(TokenEncryptor.encrypt)
        ret = sig.return_annotation
        # With from __future__ import annotations, ret might be a string
        assert ret is str or ret == "str"

    def test_decrypt_returns_string(self):
        """decrypt() return type annotation is str."""
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        sig = signature(TokenEncryptor.decrypt)
        ret = sig.return_annotation
        assert ret is str or ret == "str"


class TestGoogleCalendarServiceInterface:
    """Verify GoogleCalendarService class structure."""

    def test_service_importable(self):
        """GoogleCalendarService exists in services module."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert GoogleCalendarService is not None

    def test_service_is_class(self):
        """GoogleCalendarService is a regular class."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert isinstance(GoogleCalendarService, type)

    def test_service_init_signature(self):
        """GoogleCalendarService.__init__ accepts client_id, client_secret,
        redirect_uri, encryptor."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        sig = signature(GoogleCalendarService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "client_id" in params
        assert "client_secret" in params
        assert "redirect_uri" in params
        assert "encryptor" in params

    def test_service_has_get_authorization_url(self):
        """Service has get_authorization_url() method."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert hasattr(GoogleCalendarService, "get_authorization_url")
        assert callable(GoogleCalendarService.get_authorization_url)

    def test_get_authorization_url_signature(self):
        """get_authorization_url(state: str) -> str."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        sig = signature(GoogleCalendarService.get_authorization_url)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "state" in params
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_service_has_exchange_code(self):
        """Service has exchange_code() async method."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert hasattr(GoogleCalendarService, "exchange_code")
        assert callable(GoogleCalendarService.exchange_code)

    def test_service_has_refresh_token(self):
        """Service has refresh_token() async method."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert hasattr(GoogleCalendarService, "refresh_token")
        assert callable(GoogleCalendarService.refresh_token)

    def test_service_has_list_events(self):
        """Service has list_events() async method."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert hasattr(GoogleCalendarService, "list_events")
        assert callable(GoogleCalendarService.list_events)

    def test_service_has_get_event(self):
        """Service has get_event() async method."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        assert hasattr(GoogleCalendarService, "get_event")
        assert callable(GoogleCalendarService.get_event)

    def test_list_events_signature(self):
        """list_events accepts access_token, refresh_token, calendar_id, days_ahead."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        sig = signature(GoogleCalendarService.list_events)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "access_token" in params
        assert "refresh_token" in params
        assert "calendar_id" in params
        assert "days_ahead" in params

    def test_get_event_signature(self):
        """get_event accepts access_token, refresh_token, calendar_id, event_id."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        sig = signature(GoogleCalendarService.get_event)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "access_token" in params
        assert "refresh_token" in params
        assert "calendar_id" in params
        assert "event_id" in params


class TestCalendarExceptionsInterface:
    """Verify exception hierarchy for Calendar operations."""

    def test_google_calendar_error_importable(self):
        """GoogleCalendarError exception exists."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarError

        assert issubclass(GoogleCalendarError, Exception)

    def test_token_expired_error_importable(self):
        """TokenExpiredError exception exists."""
        from meeting_notes_ai.services.google_calendar import TokenExpiredError

        assert issubclass(TokenExpiredError, Exception)

    def test_token_expired_inherits_calendar_error(self):
        """TokenExpiredError inherits from GoogleCalendarError."""
        from meeting_notes_ai.services.google_calendar import (
            GoogleCalendarError,
            TokenExpiredError,
        )

        assert issubclass(TokenExpiredError, GoogleCalendarError)


class TestGoogleCalendarRouterInterface:
    """Verify the Google Calendar router module structure."""

    def test_router_importable(self):
        """Routes module exists and exports a router."""
        from meeting_notes_ai.routes.google_calendar import router

        assert router is not None

    def test_router_prefix(self):
        """Router prefix includes google-calendar path."""
        from meeting_notes_ai.routes.google_calendar import router

        assert "google-calendar" in router.prefix

    def test_router_has_tags(self):
        """Router has appropriate tags."""
        from meeting_notes_ai.routes.google_calendar import router

        assert router.tags is not None
        assert len(router.tags) > 0

    def test_auth_endpoint_exists(self):
        """POST /auth endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/auth")
        assert route is not None, "/auth route not found"
        assert "POST" in route.methods

    def test_callback_endpoint_exists(self):
        """GET /callback endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/callback")
        assert route is not None, "/callback route not found"
        assert "GET" in route.methods

    def test_events_endpoint_exists(self):
        """GET /events endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/events")
        assert route is not None, "/events route not found"
        assert "GET" in route.methods

    def test_import_endpoint_exists(self):
        """POST /import/{event_id} endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/import")
        assert route is not None, "/import route not found"
        assert "POST" in route.methods

    def test_status_endpoint_exists(self):
        """GET /status endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/status")
        assert route is not None, "/status route not found"
        assert "GET" in route.methods

    def test_disconnect_endpoint_exists(self):
        """DELETE /disconnect endpoint is registered."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/integrations/google-calendar/disconnect")
        assert route is not None, "/disconnect route not found"
        assert "DELETE" in route.methods


class TestCalendarPydanticSchemasInterface:
    """Verify Pydantic response/request models exist with correct fields."""

    def test_calendar_auth_response_importable(self):
        """CalendarAuthResponse schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarAuthResponse

        assert issubclass(CalendarAuthResponse, BaseModel)

    def test_calendar_auth_response_fields(self):
        """CalendarAuthResponse has authorization_url and state fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarAuthResponse

        fields = CalendarAuthResponse.model_fields
        assert "authorization_url" in fields
        assert "state" in fields

    def test_calendar_callback_response_importable(self):
        """CalendarCallbackResponse schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarCallbackResponse

        assert issubclass(CalendarCallbackResponse, BaseModel)

    def test_calendar_callback_response_fields(self):
        """CalendarCallbackResponse has connected, calendar_id, expires_at fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarCallbackResponse

        fields = CalendarCallbackResponse.model_fields
        assert "connected" in fields
        assert "calendar_id" in fields
        assert "expires_at" in fields

    def test_calendar_event_importable(self):
        """CalendarEvent schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarEvent

        assert issubclass(CalendarEvent, BaseModel)

    def test_calendar_event_fields(self):
        """CalendarEvent has all required event fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarEvent

        fields = CalendarEvent.model_fields
        assert "id" in fields
        assert "summary" in fields
        assert "description" in fields
        assert "start" in fields
        assert "end" in fields
        assert "attendees" in fields
        assert "location" in fields
        assert "meet_link" in fields
        assert "organizer" in fields
        assert "calendar_id" in fields
        assert "imported" in fields

    def test_calendar_events_response_importable(self):
        """CalendarEventsResponse schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarEventsResponse

        assert issubclass(CalendarEventsResponse, BaseModel)

    def test_calendar_events_response_fields(self):
        """CalendarEventsResponse has events, calendar_id, days fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarEventsResponse

        fields = CalendarEventsResponse.model_fields
        assert "events" in fields
        assert "calendar_id" in fields
        assert "days" in fields

    def test_calendar_import_response_importable(self):
        """CalendarImportResponse schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarImportResponse

        assert issubclass(CalendarImportResponse, BaseModel)

    def test_calendar_import_response_fields(self):
        """CalendarImportResponse has meeting field."""
        from meeting_notes_ai.routes.google_calendar import CalendarImportResponse

        fields = CalendarImportResponse.model_fields
        assert "meeting" in fields

    def test_calendar_status_response_importable(self):
        """CalendarStatusResponse schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarStatusResponse

        assert issubclass(CalendarStatusResponse, BaseModel)

    def test_calendar_status_response_fields(self):
        """CalendarStatusResponse has connected, calendar_id, connected_at,
        token_expires_at, needs_reauth fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarStatusResponse

        fields = CalendarStatusResponse.model_fields
        assert "connected" in fields
        assert "calendar_id" in fields
        assert "connected_at" in fields
        assert "token_expires_at" in fields
        assert "needs_reauth" in fields

    def test_calendar_attendee_importable(self):
        """CalendarAttendee schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarAttendee

        assert issubclass(CalendarAttendee, BaseModel)

    def test_calendar_attendee_fields(self):
        """CalendarAttendee has email, display_name, response_status fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarAttendee

        fields = CalendarAttendee.model_fields
        assert "email" in fields
        assert "display_name" in fields
        assert "response_status" in fields

    def test_calendar_organizer_importable(self):
        """CalendarOrganizer schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarOrganizer

        assert issubclass(CalendarOrganizer, BaseModel)

    def test_calendar_organizer_fields(self):
        """CalendarOrganizer has email, display_name fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarOrganizer

        fields = CalendarOrganizer.model_fields
        assert "email" in fields
        assert "display_name" in fields

    def test_calendar_context_importable(self):
        """CalendarContext schema exists."""
        from meeting_notes_ai.routes.google_calendar import CalendarContext

        assert issubclass(CalendarContext, BaseModel)

    def test_calendar_context_fields(self):
        """CalendarContext has attendees, location, meet_link, description fields."""
        from meeting_notes_ai.routes.google_calendar import CalendarContext

        fields = CalendarContext.model_fields
        assert "attendees" in fields
        assert "location" in fields
        assert "meet_link" in fields
        assert "description" in fields


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (must FAIL with NotImplementedError until implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOAuth2AuthorizationURLBehavioral:
    """Test OAuth2 authorization URL generation endpoint."""

    @pytest.fixture
    def auth_headers(self):
        """Provide auth headers for authenticated requests."""
        return {"Authorization": "Bearer test-token"}

    @pytest.mark.asyncio
    async def test_auth_endpoint_returns_authorization_url(self, auth_headers):
        """POST /auth returns a valid Google OAuth URL with correct scopes."""
        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/integrations/google-calendar/auth",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "authorization_url" in data
            assert "state" in data
            # Verify the URL points to Google's OAuth endpoint
            assert "accounts.google.com/o/oauth2/auth" in data["authorization_url"]
            # Verify required OAuth parameters are present
            url = data["authorization_url"]
            assert "client_id=" in url
            assert "redirect_uri=" in url
            assert "scope=" in url
            assert "state=" in url
            assert "calendar.readonly" in url

    @pytest.mark.asyncio
    async def test_auth_endpoint_returns_unique_state_tokens(self, auth_headers):
        """Each /auth call generates a unique state token for CSRF protection."""
        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp1 = await client.post(
                "/api/v1/integrations/google-calendar/auth",
                headers=auth_headers,
            )
            resp2 = await client.post(
                "/api/v1/integrations/google-calendar/auth",
                headers=auth_headers,
            )
            assert resp1.json()["state"] != resp2.json()["state"]

    @pytest.mark.asyncio
    async def test_auth_endpoint_requires_authentication(self):
        """POST /auth without auth headers returns 401."""
        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        # Temporarily clear auth override to test real auth behavior
        app.dependency_overrides.clear()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/auth",
                )
                assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides[get_current_user] = lambda: _DEFAULT_USER


class TestOAuth2CallbackBehavioral:
    """Test OAuth2 callback handler stores encrypted tokens per-tenant."""

    @pytest.mark.asyncio
    async def test_callback_exchanges_code_and_stores_tokens(self):
        """GET /callback with valid code and state stores encrypted tokens."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_tokens = {
            "access_token": "mock-access-token-123",
            "refresh_token": "mock-refresh-token-456",
            "expires_at": "2026-08-06T15:30:00+00:00",
            "token_type": "Bearer",
            "scope": ["https://www.googleapis.com/auth/calendar.readonly"],
        }

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._verify_oauth_state",
                new_callable=AsyncMock,
                return_value="test-user-id",
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.exchange_code = AsyncMock(return_value=mock_tokens)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/callback",
                    params={"code": "test-auth-code", "state": "test-state-token"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["connected"] is True
                assert data["calendar_id"] == "primary"
                assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_callback_rejects_invalid_state(self):
        """GET /callback with invalid state returns 400."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._verify_oauth_state",
            new_callable=AsyncMock,
            return_value=None,  # Invalid state
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/callback",
                    params={"code": "test-code", "state": "invalid-state"},
                )
                assert resp.status_code == 400
                assert "state" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_callback_tokens_are_encrypted_before_storage(self):
        """Callback stores tokens encrypted, not in plaintext."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_tokens = {
            "access_token": "sensitive-access-token",
            "refresh_token": "sensitive-refresh-token",
            "expires_at": "2026-08-06T15:30:00+00:00",
            "token_type": "Bearer",
            "scope": ["https://www.googleapis.com/auth/calendar.readonly"],
        }

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._verify_oauth_state",
                new_callable=AsyncMock,
                return_value="test-user-id",
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.exchange_code = AsyncMock(return_value=mock_tokens)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/callback",
                    params={"code": "test-code", "state": "valid-state"},
                )
                assert resp.status_code == 200
                # The response should NOT contain plaintext tokens
                body = resp.text
                assert "sensitive-access-token" not in body
                assert "sensitive-refresh-token" not in body


class TestOAuthStatePurgeBehavioral:
    """F5: expired/used OAuthState rows are purged on read (verify)."""

    @pytest.mark.asyncio
    async def test_verify_oauth_state_purges_expired_and_used_rows(self):
        """Verifying a state consumes it and purges expired/used rows on read."""
        from datetime import timedelta

        from sqlalchemy import select

        from meeting_notes_ai.db.models import OAuthState
        from meeting_notes_ai.db.session import _session_factory
        from meeting_notes_ai.routes.google_calendar import _verify_oauth_state

        now = datetime.now(timezone.utc)

        async with _session_factory() as session:
            session.add_all(
                [
                    OAuthState(
                        state_token="used-state-f5",
                        user_id="test-user-id",
                        expires_at=now + timedelta(minutes=5),
                        used=True,
                    ),
                    OAuthState(
                        state_token="expired-state-f5",
                        user_id="test-user-id",
                        expires_at=now - timedelta(minutes=5),
                        used=False,
                    ),
                    OAuthState(
                        state_token="fresh-unused-f5",
                        user_id="test-user-id",
                        expires_at=now + timedelta(minutes=5),
                        used=False,
                    ),
                    OAuthState(
                        state_token="valid-state-f5",
                        user_id="test-user-id",
                        expires_at=now + timedelta(minutes=5),
                        used=False,
                    ),
                ]
            )
            await session.commit()

            # Verifying a valid state consumes it and purges used/expired rows
            user_id = await _verify_oauth_state("valid-state-f5", session)
            assert user_id == "test-user-id"
            await session.commit()

            remaining = (await session.execute(select(OAuthState.state_token))).scalars().all()
            assert "used-state-f5" not in remaining
            assert "expired-state-f5" not in remaining
            assert "valid-state-f5" not in remaining  # consumed on read
            assert "fresh-unused-f5" in remaining  # untouched states survive


class TestEventListingBehavioral:
    """Test event listing returns upcoming 7-day events."""

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-token"}

    @pytest.mark.asyncio
    async def test_events_endpoint_returns_list(self, auth_headers):
        """GET /events returns a list of calendar events with correct structure."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_events = [
            {
                "id": "event-1",
                "summary": "Q3 Planning",
                "description": "Review quarterly goals",
                "start": "2026-08-07T10:00:00+02:00",
                "end": "2026-08-07T11:00:00+02:00",
                "attendees": [
                    {
                        "email": "alice@example.com",
                        "displayName": "Alice",
                        "responseStatus": "accepted",
                    }
                ],
                "location": "Conference Room A",
                "meet_link": "https://meet.google.com/abc-defg-hij",
                "organizer": {"email": "bob@example.com", "displayName": "Bob"},
                "calendar_id": "primary",
                "html_link": "https://calendar.google.com/calendar/event?eid=...",
                "imported": False,
            }
        ]

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted:at"
            mock_token_record.encrypted_refresh_token = "encrypted:rt"
            mock_token_record.token_expires_at = None
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(return_value=mock_events)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "events" in data
                assert isinstance(data["events"], list)
                assert len(data["events"]) >= 1
                # Verify event structure
                event = data["events"][0]
                assert event["id"] == "event-1"
                assert event["summary"] == "Q3 Planning"
                assert "start" in event
                assert "end" in event
                assert "attendees" in event
                assert "meet_link" in event

    @pytest.mark.asyncio
    async def test_events_endpoint_default_7_days(self, auth_headers):
        """GET /events defaults to 7 days ahead."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted:at"
            mock_token_record.encrypted_refresh_token = "encrypted:rt"
            mock_token_record.token_expires_at = None
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(return_value=[])  # empty for import tests

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["days"] == 7
                assert data["calendar_id"] == "primary"
                # Verify list_events was called with days_ahead=7
                mock_service.list_events.assert_called_once()
                call_kwargs = mock_service.list_events.call_args
                assert call_kwargs.kwargs.get("days_ahead") == 7

    @pytest.mark.asyncio
    async def test_events_mark_already_imported(self, auth_headers):
        """Events that have been imported are marked with imported=true."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_events = [
            {
                "id": "imported-event",
                "summary": "Already imported",
                "description": "",
                "start": "2026-08-07T10:00:00+02:00",
                "end": "2026-08-07T11:00:00+02:00",
                "attendees": [],
                "location": "",
                "meet_link": None,
                "organizer": {"email": "", "displayName": ""},
                "calendar_id": "primary",
                "html_link": "",
            }
        ]

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value={"imported-event"},
            ),
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted:at"
            mock_token_record.encrypted_refresh_token = "encrypted:rt"
            mock_token_record.token_expires_at = None
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(return_value=mock_events)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                events = resp.json()["events"]
                assert len(events) == 1
                assert events[0]["imported"] is True


class TestEventAttendeeFieldMappingBehavioral:
    """Regression: Google camelCase displayName/responseStatus map to snake_case API fields."""

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-token"}

    @pytest.mark.asyncio
    async def test_normalize_event_maps_attendee_fields_to_snake_case(self):
        """_normalize_event emits display_name/response_status, not camelCase keys."""
        from meeting_notes_ai.services.google_calendar import GoogleCalendarService

        svc = GoogleCalendarService(
            client_id="cid", client_secret="csecret", redirect_uri="http://test/cb", encryptor=None
        )
        raw = {
            "id": "evt-1",
            "summary": "Q3 Planning",
            "start": {"dateTime": "2026-08-07T10:00:00+02:00"},
            "end": {"dateTime": "2026-08-07T11:00:00+02:00"},
            "attendees": [
                {
                    "email": "alice@example.com",
                    "displayName": "Alice",
                    "responseStatus": "accepted",
                },
                {
                    "email": "bob@example.com",
                    "displayName": "Bob",
                    "responseStatus": "tentative",
                },
            ],
            "organizer": {"email": "carol@example.com", "displayName": "Carol"},
        }
        normalized = svc._normalize_event(raw)
        assert normalized["attendees"][0] == {
            "email": "alice@example.com",
            "display_name": "Alice",
            "response_status": "accepted",
        }
        assert normalized["attendees"][1]["display_name"] == "Bob"
        assert normalized["attendees"][1]["response_status"] == "tentative"
        assert normalized["organizer"] == {"email": "carol@example.com", "display_name": "Carol"}

    @pytest.mark.asyncio
    async def test_events_endpoint_returns_attendee_display_names(self, auth_headers):
        """GET /events surfaces attendee display_name/response_status to the client."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_events = [
            {
                "id": "event-1",
                "summary": "Q3 Planning",
                "description": "",
                "start": "2026-08-07T10:00:00+02:00",
                "end": "2026-08-07T11:00:00+02:00",
                "attendees": [
                    {
                        "email": "alice@example.com",
                        "display_name": "Alice",
                        "response_status": "accepted",
                    }
                ],
                "location": "",
                "meet_link": None,
                "organizer": {"email": "bob@example.com", "display_name": "Bob"},
                "calendar_id": "primary",
                "html_link": "",
            }
        ]

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted:at"
            mock_token_record.encrypted_refresh_token = "encrypted:rt"
            mock_token_record.token_expires_at = None
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(return_value=mock_events)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                attendee = resp.json()["events"][0]["attendees"][0]
                assert attendee["display_name"] == "Alice"
                assert attendee["response_status"] == "accepted"
                assert resp.json()["events"][0]["organizer"]["display_name"] == "Bob"


class TestEventsErrorHandlingBehavioral:
    """F2: external-call errors in the events endpoint map to clean HTTP codes."""

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-token"}

    def _mock_token_record(self):
        from unittest.mock import AsyncMock

        mock_token = AsyncMock()
        mock_token.encrypted_access_token = "encrypted:at"
        mock_token.encrypted_refresh_token = "encrypted:rt"
        mock_token.token_expires_at = None
        return mock_token

    @pytest.mark.asyncio
    async def test_events_endpoint_returns_401_on_token_expired(self, auth_headers):
        """GET /events maps TokenExpiredError from list_events to 401."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app
        from meeting_notes_ai.services.google_calendar import TokenExpiredError

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=self._mock_token_record(),
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(side_effect=TokenExpiredError("token revoked"))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 401
                assert "re-authorize" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_events_endpoint_returns_502_on_calendar_error(self, auth_headers):
        """GET /events maps GoogleCalendarError from list_events to 502 (not 500)."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app
        from meeting_notes_ai.services.google_calendar import GoogleCalendarError

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=self._mock_token_record(),
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.list_events = AsyncMock(side_effect=GoogleCalendarError("api down"))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=auth_headers,
                )
                assert resp.status_code == 502
                # No raw exception text leaks into the detail
                assert "api down" not in resp.text


class TestCalendarImportBehavioral:
    """Test import endpoint creates a meeting record from a calendar event."""

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-token"}

    @pytest.mark.asyncio
    async def test_import_creates_meeting(self, auth_headers):
        """POST /import/{event_id} creates a meeting record from calendar event."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_event = {
            "id": "event-123",
            "summary": "Q3 Planning",
            "description": "Review quarterly goals",
            "start": "2026-08-07T10:00:00+02:00",
            "end": "2026-08-07T11:00:00+02:00",
            "attendees": [
                {"email": "alice@example.com", "displayName": "Alice"},
                {"email": "bob@example.com", "displayName": "Bob"},
            ],
            "location": "Conference Room A",
            "meet_link": "https://meet.google.com/abc-defg-hij",
            "organizer": {"email": "alice@example.com", "displayName": "Alice"},
            "calendar_id": "primary",
        }

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value=set(),
            ),
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted-at"
            mock_token_record.encrypted_refresh_token = "encrypted-rt"
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.get_event = AsyncMock(return_value=mock_event)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/event-123",
                    headers=auth_headers,
                )
                assert resp.status_code == 201
                data = resp.json()
                meeting = data["meeting"]
                assert meeting["title"] == "Q3 Planning"
                assert meeting["source"] == "calendar_import"
                assert meeting["google_calendar_event_id"] == "event-123"
                assert meeting["date"] == "2026-08-07T10:00:00+02:00"
                assert meeting["duration"] == "1h"
                assert meeting["participants"] == 2
                assert meeting["review_status"] == "needs_review"
                # Calendar context should include attendees, location, meet_link
                ctx = meeting["calendar_context"]
                assert "alice@example.com" in ctx["attendees"]
                assert "bob@example.com" in ctx["attendees"]
                assert ctx["location"] == "Conference Room A"
                assert ctx["meet_link"] == "https://meet.google.com/abc-defg-hij"

    @pytest.mark.asyncio
    async def test_import_rejects_duplicate_event(self, auth_headers):
        """POST /import/{event_id} returns 409 if event already imported."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value={"already-imported-event"},
            ),
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "encrypted:at"
            mock_token_record.encrypted_refresh_token = "encrypted:rt"
            mock_load.return_value = mock_token_record

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/already-imported-event",
                    headers=auth_headers,
                )
                assert resp.status_code == 409
                assert "already" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_returns_409_when_not_connected(self, auth_headers):
        """POST /import returns 409 if Google Calendar is not connected."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
            return_value=None,  # No token record = not connected
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/some-event",
                    headers=auth_headers,
                )
                assert resp.status_code == 409
                assert "connected" in resp.json()["detail"].lower()


class TestSharedCalendarImportBehavioral:
    """F1: event import uniqueness is per (user_id, event_id) — no raw 500.

    Regression: user A imports event X -> 201; user B importing the SAME
    event X from a shared calendar -> 409, not the unhandled IntegrityError 500.
    """

    @pytest.mark.asyncio
    async def test_shared_event_second_user_import_returns_409(self):
        """User A imports event X; user B importing the same event gets 409."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.auth import get_current_user
        from meeting_notes_ai.main import app

        mock_event = {
            "id": "shared-event-f1",
            "summary": "Shared Team Sync",
            "description": "",
            "start": "2026-08-07T10:00:00+02:00",
            "end": "2026-08-07T11:00:00+02:00",
            "attendees": [],
            "location": "",
            "meet_link": None,
            "organizer": {"email": "", "displayName": ""},
            "calendar_id": "primary",
            "html_link": "",
        }
        mock_token = AsyncMock()
        mock_token.encrypted_access_token = "encrypted:at"
        mock_token.encrypted_refresh_token = "encrypted:rt"
        mock_token.token_expires_at = None

        original_override = app.dependency_overrides.get(get_current_user)

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=mock_token,
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.get_event = AsyncMock(return_value=mock_event)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # User A (default override -> test-user-id) imports the event
                resp_a = await client.post(
                    "/api/v1/integrations/google-calendar/import/shared-event-f1",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp_a.status_code == 201

                # User B (other-user-id) tries to import the SAME event
                app.dependency_overrides[get_current_user] = lambda: {
                    "user_id": "other-user-id",
                    "email": "other@example.com",
                    "display_name": "Other User",
                }
                try:
                    resp_b = await client.post(
                        "/api/v1/integrations/google-calendar/import/shared-event-f1",
                        headers={"Authorization": "Bearer test-token"},
                    )
                finally:
                    if original_override is not None:
                        app.dependency_overrides[get_current_user] = original_override
                    else:
                        app.dependency_overrides.pop(get_current_user, None)

                # The shared-calendar duplicate must be a clean 409, never a 500
                assert resp_b.status_code == 409
                assert "already" in resp_b.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_duplicate_import_hits_db_constraint_returns_409(self):
        """A same-user import race reaching the DB constraint returns 409 (not 500)."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_event = {
            "id": "race-event-f1",
            "summary": "Race Event",
            "description": "",
            "start": "2026-08-07T10:00:00+02:00",
            "end": "2026-08-07T11:00:00+02:00",
            "attendees": [],
            "location": "",
            "meet_link": None,
            "organizer": {"email": "", "displayName": ""},
            "calendar_id": "primary",
            "html_link": "",
        }
        mock_token = AsyncMock()
        mock_token.encrypted_access_token = "encrypted:at"
        mock_token.encrypted_refresh_token = "encrypted:rt"
        mock_token.token_expires_at = None

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value=set(),
            ),
            patch(
                "meeting_notes_ai.routes.google_calendar._event_imported_by_any_user",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=mock_token,
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.get_event = AsyncMock(return_value=mock_event)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"Authorization": "Bearer test-token"}
                # First import inserts the meeting row (real DB)
                resp1 = await client.post(
                    "/api/v1/integrations/google-calendar/import/race-event-f1",
                    headers=headers,
                )
                assert resp1.status_code == 201
                # Second import: app-level checks are bypassed (simulated race)
                # so the composite unique constraint fires -> 409, never a 500
                resp2 = await client.post(
                    "/api/v1/integrations/google-calendar/import/race-event-f1",
                    headers=headers,
                )
                assert resp2.status_code == 409


class TestImportErrorHandlingBehavioral:
    """F4: import endpoint distinguishes token expiry (401) from API errors (404)."""

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-token"}

    def _mock_token_record(self):
        from unittest.mock import AsyncMock

        mock_token = AsyncMock()
        mock_token.encrypted_access_token = "encrypted:at"
        mock_token.encrypted_refresh_token = "encrypted:rt"
        return mock_token

    @pytest.mark.asyncio
    async def test_import_returns_401_on_token_expired(self, auth_headers):
        """POST /import maps TokenExpiredError from get_event to 401 (not 404)."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app
        from meeting_notes_ai.services.google_calendar import TokenExpiredError

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value=set(),
            ),
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=self._mock_token_record(),
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.get_event = AsyncMock(side_effect=TokenExpiredError("token revoked"))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/evt-token-expired",
                    headers=auth_headers,
                )
                assert resp.status_code == 401
                assert "re-authorize" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_returns_404_without_leaking_error(self, auth_headers):
        """POST /import maps GoogleCalendarError to 404 with a generic detail."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app
        from meeting_notes_ai.services.google_calendar import GoogleCalendarError

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._get_imported_event_ids",
                new_callable=AsyncMock,
                return_value=set(),
            ),
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
                return_value=self._mock_token_record(),
            ),
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_service = mock_svc_cls.return_value
            mock_service.get_event = AsyncMock(side_effect=GoogleCalendarError("secret-detail-xyz"))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/evt-missing",
                    headers=auth_headers,
                )
                assert resp.status_code == 404
                detail = resp.json()["detail"]
                assert "secret-detail-xyz" not in resp.text  # no raw error echo
                assert "calendar event" in detail.lower()


class TestTenantIsolationBehavioral:
    """Test tenant isolation — user A cannot see user B's calendar events."""

    @pytest.mark.asyncio
    async def test_user_a_events_invisible_to_user_b(self):
        """Events belong to user_id scope; different tokens per user."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        user_a_headers = {"Authorization": "Bearer token-user-a"}
        user_b_headers = {"Authorization": "Bearer token-user-b"}

        user_a_events = [
            {
                "id": "a-event",
                "summary": "User A Meeting",
                "description": "",
                "start": "2026-08-07T10:00:00+02:00",
                "end": "2026-08-07T11:00:00+02:00",
                "attendees": [],
                "location": "",
                "meet_link": None,
                "organizer": {"email": "", "displayName": ""},
                "calendar_id": "primary",
                "html_link": "",
            }
        ]

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_a = AsyncMock()
            mock_token_a.encrypted_access_token = "encrypted:a-at"
            mock_token_a.encrypted_refresh_token = "encrypted:a-rt"
            mock_token_a.token_expires_at = None

            mock_token_b = AsyncMock()
            mock_token_b.encrypted_access_token = "encrypted:b-at"
            mock_token_b.encrypted_refresh_token = "encrypted:b-rt"
            mock_token_b.token_expires_at = None

            # Different tokens for different users
            mock_load.side_effect = lambda db, uid: (
                mock_token_a if uid == "user-a" else mock_token_b
            )

            mock_service = mock_svc_cls.return_value
            # Make the mock service's encryptor decrypt to real strings
            # so the events endpoint's token-decryption works correctly
            mock_service.encryptor.decrypt = lambda token: token.replace("encrypted:", "")
            # User A gets their events, User B gets empty
            mock_service.list_events = AsyncMock(
                side_effect=lambda **kwargs: (
                    user_a_events if kwargs.get("access_token") == "a-at" else []
                )
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp_a = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=user_a_headers,
                )
                resp_b = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers=user_b_headers,
                )

                # User A sees events, User B sees none
                assert len(resp_a.json()["events"]) == 1
                assert resp_a.json()["events"][0]["summary"] == "User A Meeting"
                assert len(resp_b.json()["events"]) == 0

    @pytest.mark.asyncio
    async def test_import_uses_user_scoped_token_lookup(self):
        """Import endpoint loads tokens for the authenticated user only."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
            return_value=None,  # No token for this user
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/integrations/google-calendar/import/event-1",
                    headers={"Authorization": "Bearer user-b-token"},
                )
                # Should fail because this user has no connected calendar
                assert resp.status_code == 409


class TestTokenRefreshBehavioral:
    """Test token refresh is triggered automatically when tokens are expired."""

    @pytest.mark.asyncio
    async def test_expired_token_triggers_refresh(self):
        """Events endpoint refreshes token when token_expires_at is in the past."""
        # Token expired 1 hour ago
        from datetime import timedelta
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "old-encrypted-at"
            mock_token_record.encrypted_refresh_token = "encrypted-rt"
            mock_token_record.token_expires_at = expired_time
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.refresh_token = AsyncMock(
                return_value={
                    "access_token": "new-access-token",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "token_type": "Bearer",
                }
            )
            mock_service.list_events = AsyncMock(return_value=[])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp.status_code == 200
                # Verify refresh_token was called
                mock_service.refresh_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_token_skips_refresh(self):
        """Events endpoint does NOT refresh token when token_expires_at is in the future."""
        from datetime import timedelta
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        with (
            patch(
                "meeting_notes_ai.routes.google_calendar._load_user_token",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("meeting_notes_ai.routes.google_calendar._get_calendar_service") as mock_svc_cls,
        ):
            mock_token_record = AsyncMock()
            mock_token_record.encrypted_access_token = "valid-encrypted-at"
            mock_token_record.encrypted_refresh_token = "encrypted-rt"
            mock_token_record.token_expires_at = future_time
            mock_load.return_value = mock_token_record

            mock_service = mock_svc_cls.return_value
            mock_service.refresh_token = AsyncMock()
            mock_service.list_events = AsyncMock(return_value=[])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/events",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp.status_code == 200
                # refresh_token should NOT be called
                mock_service.refresh_token.assert_not_called()


class TestSSRFProtectionBehavioral:
    """Test SSRF protection rejects non-HTTPS and non-Google URLs."""

    def test_ssrf_protector_blocks_http(self):
        """SSRFProtector rejects HTTP (non-HTTPS) URLs."""
        from meeting_notes_ai.security import SSRFProtector

        protector = SSRFProtector()
        assert protector.validate_url("http://evil.com/steal") is False

    def test_ssrf_protector_blocks_localhost(self):
        """SSRFProtector blocks localhost URLs."""
        from meeting_notes_ai.security import SSRFProtector

        protector = SSRFProtector()
        assert protector.validate_url("https://localhost/admin") is False

    def test_ssrf_protector_blocks_private_ranges(self):
        """SSRFProtector blocks private network ranges (10.x, 192.168.x, etc)."""
        from meeting_notes_ai.security import SSRFProtector

        protector = SSRFProtector()
        assert protector.validate_url("https://10.0.0.1/secret") is False
        assert protector.validate_url("https://192.168.1.1/admin") is False
        assert protector.validate_url("https://172.16.0.1/internal") is False

    def test_ssrf_protector_allows_google_apis(self):
        """SSRFProtector allows Google API endpoints."""
        from meeting_notes_ai.security import SSRFProtector

        protector = SSRFProtector()
        assert protector.validate_url("https://oauth2.googleapis.com/token") is True
        assert (
            protector.validate_url("https://www.googleapis.com/calendar/v3/users/me/calendarList")
            is True
        )
        assert protector.validate_url("https://accounts.google.com/o/oauth2/auth") is True

    def test_ssrf_protector_blocks_cloud_metadata(self):
        """SSRFProtector blocks cloud metadata endpoints."""
        from meeting_notes_ai.security import SSRFProtector

        protector = SSRFProtector()
        assert protector.validate_url("https://169.254.169.254/latest/meta-data/") is (False)


class TestCalendarStatusBehavioral:
    """Test calendar connection status endpoint."""

    @pytest.mark.asyncio
    async def test_status_when_connected(self):
        """GET /status returns connected=true when user has active tokens."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
        ) as mock_load:
            mock_token = AsyncMock()
            mock_token.calendar_id = "primary"
            mock_token.created_at = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
            mock_token.token_expires_at = datetime(2099, 8, 6, 13, 0, 0, tzinfo=timezone.utc)
            mock_load.return_value = mock_token

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/status",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["connected"] is True
                assert data["calendar_id"] == "primary"
                assert data["needs_reauth"] is False

    @pytest.mark.asyncio
    async def test_status_when_not_connected(self):
        """GET /status returns connected=false when no tokens exist."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/integrations/google-calendar/status",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["connected"] is False
                assert data["needs_reauth"] is False


class TestCalendarDisconnectBehavioral:
    """Test disconnect endpoint soft-deletes tokens."""

    @pytest.mark.asyncio
    async def test_disconnect_sets_inactive(self):
        """DELETE /disconnect marks the token record as inactive."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        mock_token = AsyncMock()
        mock_token.is_active = True
        mock_token.disconnected_at = None

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
            return_value=mock_token,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(
                    "/api/v1/integrations/google-calendar/disconnect",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert resp.status_code == 204
                # Verify the token was marked inactive
                assert mock_token.is_active is False
                assert mock_token.disconnected_at is not None

    @pytest.mark.asyncio
    async def test_disconnect_idempotent_when_not_connected(self):
        """DELETE /disconnect returns 204 even when not connected."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from meeting_notes_ai.main import app

        with patch(
            "meeting_notes_ai.routes.google_calendar._load_user_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(
                    "/api/v1/integrations/google-calendar/disconnect",
                    headers={"Authorization": "Bearer test-token"},
                )
                # Should succeed (204) even when nothing to disconnect
                assert resp.status_code == 204
