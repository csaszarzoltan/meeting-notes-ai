"""Tests for the live-transcription UI integration.

Covers the small backend glue the live view depends on:

- ``POST /api/v1/meetings/live/start`` — JWT-authenticated draft-meeting
  creation (the WS endpoint requires the meeting row to already exist, so
  the UI needs a way to create one before connecting).
- ``GET /app/live`` — serves the component-based React SPA shell with a
  CSP that permits the WebSocket + microphone, and a Permissions-Policy
  that keeps the mic blocked everywhere except the live page itself.
- The security middleware must not clobber a route-provided
  ``Permissions-Policy`` header (the live page overrides the global
  camera/mic/geolocation lockdown).
"""

from __future__ import annotations

import pytest

from meeting_notes_ai.live_session import LiveStartResponse

pytestmark = pytest.mark.quick


class TestLiveStartEndpointInterface:
    """Interface tests for the draft-meeting endpoint."""

    def test_live_start_response_model_exists(self):
        """LiveStartResponse should be importable and constructible."""
        resp = LiveStartResponse(meeting_id="abc-123")
        assert resp.meeting_id == "abc-123"
        assert resp.status == "live_ready"

    def test_live_start_response_default_status(self):
        """LiveStartResponse.status should default to live_ready."""
        assert LiveStartResponse(meeting_id="x").status == "live_ready"

    def test_start_route_registered(self):
        """POST /api/v1/meetings/live/start should exist on the live router."""
        from meeting_notes_ai.routes.live_transcription import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/start") and "POST" in methods:
                return
        pytest.fail("POST /api/v1/meetings/live/start route not found")

    def test_start_handler_has_user_dependency(self):
        """The start handler should depend on the current user."""
        import inspect

        from meeting_notes_ai.routes.live_transcription import start_live_session

        params = inspect.signature(start_live_session).parameters
        assert "user" in params or "current_user" in params


class TestLiveStartEndpointBehavioral:
    """Behavioral tests for POST /api/v1/meetings/live/start."""

    @pytest.fixture
    def client(self, _setup_test_db, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.config import settings
        from meeting_notes_ai.main import app

        monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
        return TestClient(app)

    def _auth_headers(self, user_id: str = "test-user-id") -> dict:
        import asyncio

        from meeting_notes_ai.auth import create_access_token

        token = asyncio.run(create_access_token(user_id))
        return {"Authorization": f"Bearer {token}"}

    def test_start_requires_auth(self, client):
        resp = client.post("/api/v1/meetings/live/start")
        assert resp.status_code == 401

    def test_start_creates_draft_meeting(self, client):
        """Authenticated start creates a meeting row and returns its id."""
        resp = client.post("/api/v1/meetings/live/start", headers=self._auth_headers())
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["meeting_id"]
        assert data["status"] == "live_ready"

        # The meeting must exist in the DB (WS requires it before connect).
        import asyncio

        from sqlalchemy import select

        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        async def _fetch():
            async for session in get_db_session():
                result = await session.execute(
                    select(Meeting).where(Meeting.id == data["meeting_id"])
                )
                return result.scalar_one_or_none()
            return None

        row = asyncio.run(_fetch())
        assert row is not None, "start must persist a draft meeting row"
        assert row.user_id == "test-user-id"
        assert row.transcript in (None, "")

    def test_start_then_ws_connect_works(self, client):
        """The draft meeting can immediately be used by the WS endpoint."""
        import asyncio
        import json

        from meeting_notes_ai.auth import create_access_token
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        token = asyncio.run(create_access_token("test-user-id"))

        # Override the AI seam so the WS flow runs without external keys.
        from meeting_notes_ai.main import app
        from meeting_notes_ai.models import (
            ActionItem,
            ExtractionResult,
            MeetingMode,
            TranscriptionResult,
            TranscriptSegment,
        )
        from meeting_notes_ai.routes.live_transcription import get_live_service

        class _FakeTranscription:
            async def transcribe(self, audio_bytes, filename, language=None):
                return TranscriptionResult(
                    text="hello from the live ui",
                    language=language or "en",
                    duration_seconds=1.0,
                    segments=[
                        TranscriptSegment(start=0.0, end=1.0, text="hello from the live ui")
                    ],
                )

        class _FakeExtraction:
            async def extract(self, transcript, mode=MeetingMode.GENERAL):
                return ExtractionResult(
                    summary="UI test summary",
                    action_items=[ActionItem(assignee="QA", description="Verify live UI")],
                    decisions=[],
                    key_points=[],
                )

        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
        )
        app.dependency_overrides[get_live_service] = lambda: service
        try:
            start = client.post("/api/v1/meetings/live/start", headers=self._auth_headers())
            assert start.status_code == 201
            meeting_id = start.json()["meeting_id"]

            url = f"/api/v1/meetings/live?token={token}&meeting_id={meeting_id}"
            with client.websocket_connect(url) as ws:
                ws.send_bytes(b"\x00" * 3200)
                ws.send_text(json.dumps({"type": "finalize"}))
                finalized = None
                for _ in range(10):
                    msg = ws.receive_json()
                    if msg.get("type") == "finalized":
                        finalized = msg
                        break
            assert finalized is not None
            assert finalized["meeting_id"] == meeting_id
            assert finalized["transcript"] == "hello from the live ui"
            assert finalized["action_items"][0]["description"] == "Verify live UI"
        finally:
            app.dependency_overrides.pop(get_live_service, None)


class TestLiveAppRoute:
    """GET /app/live serves the component-based live transcription UI."""

    @pytest.fixture
    def client(self, _setup_test_db):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.main import app

        return TestClient(app)

    def test_live_app_route_returns_200(self, client):
        resp = client.get("/app/live")
        assert resp.status_code == 200

    def test_live_app_route_has_react_root(self, client):
        """The served page must mount a component root (React SPA shell)."""
        resp = client.get("/app/live")
        assert 'id="root"' in resp.text

    def test_live_app_csp_allows_websocket_and_self_scripts(self, client):
        """CSP must permit the WS connection and the built bundle."""
        resp = client.get("/app/live")
        csp = resp.headers["Content-Security-Policy"]
        assert "connect-src" in csp and "ws:" in csp
        assert "script-src 'self'" in csp

    def test_live_app_permissions_policy_allows_microphone(self, client):
        """The live page must be allowed to open the microphone."""
        resp = client.get("/app/live")
        policy = resp.headers["Permissions-Policy"]
        assert "microphone" in policy
        assert "camera=()" in policy  # camera stays blocked


class TestMiddlewarePermissionsPolicyOverride:
    """The security middleware must respect a route-set Permissions-Policy."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from meeting_notes_ai.middleware import SecurityHeadersMiddleware

        app = FastAPI()

        @app.get("/custom-policy")
        async def custom_policy():
            from fastapi.responses import HTMLResponse

            return HTMLResponse(
                "<html><body>ok</body></html>",
                headers={"Permissions-Policy": "microphone=(self), camera=()"},
            )

        @app.get("/default-policy")
        async def default_policy():
            from fastapi.responses import HTMLResponse

            return HTMLResponse("<html><body>default</body></html>")

        app.add_middleware(SecurityHeadersMiddleware)
        return TestClient(app)

    def test_route_policy_is_preserved(self, client):
        resp = client.get("/custom-policy")
        assert resp.headers["Permissions-Policy"] == "microphone=(self), camera=()"

    def test_default_policy_still_applied(self, client):
        resp = client.get("/default-policy")
        assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
