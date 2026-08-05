"""Pre-development tests for the storage REST API (routes/storage.py).

Endpoints under test (brief Section 7):
  POST   /api/v1/meetings/{meeting_id}/audio     — upload (201), duplicate 409,
                                                   oversize 413, bad MIME 415
  GET    /api/v1/meetings/{meeting_id}/audio     — download (200, disposition)
  DELETE /api/v1/meetings/{meeting_id}/audio     — delete (204)
  GET    /api/v1/meetings/{meeting_id}/transcript — transcript txt download
  PUT/GET /api/v1/teams/{team_id}/retention     — retention policy
  POST   /api/v1/admin/retention/sweep          — admin sweep

All endpoints require get_current_user and meeting access via the
_verify_meeting_access pattern (routes/sharing.py). RED phase: the whole
module skips until routes/storage.py exists.

Test isolation: the session-scoped DB is shared, so upload tests target
freshly created meetings (owned by test-user-id) to avoid 409 collisions
with conftest-seeded rows.
"""

from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import pytest

pytestmark = pytest.mark.quick

storage_routes = pytest.importorskip(
    "meeting_notes_ai.routes.storage",
    reason="implementation pending: meeting_notes_ai/routes/storage.py",
)


def _token(user_id: str) -> str:
    """Create a valid JWT for a seeded user (mirrors test_sharing.py)."""
    from meeting_notes_ai.auth import create_access_token

    return asyncio.run(create_access_token(user_id))


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _meeting_audio_url(meeting_id: str) -> str:
    return f"/api/v1/meetings/{meeting_id}/audio"


def _fresh_meeting() -> str:
    """Create a fresh meeting owned by test-user-id (no team) and return its id."""

    async def _create() -> str:
        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        meeting_id = f"storage-upload-{uuid4().hex[:12]}"
        async for session in get_db_session():
            session.add(
                Meeting(
                    id=meeting_id,
                    title="Storage Upload Test",
                    user_id="test-user-id",
                    filename="upload_test.wav",
                    mode="general",
                    transcript="",
                )
            )
            await session.commit()
        return meeting_id

    return asyncio.run(_create())


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorageRoutesInterface:
    """Router registration + handler signatures."""

    def test_router_exists(self):
        router = storage_routes.router
        assert router is not None

    def test_upload_audio_route_registered(self):
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and r.path.endswith("/audio") and "POST" in r.methods:
                return
        pytest.fail("POST .../meetings/{id}/audio route not found")

    def test_get_audio_route_registered(self):
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and r.path.endswith("/audio") and "GET" in r.methods:
                return
        pytest.fail("GET .../meetings/{id}/audio route not found")

    def test_delete_audio_route_registered(self):
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and r.path.endswith("/audio") and "DELETE" in r.methods:
                return
        pytest.fail("DELETE .../meetings/{id}/audio route not found")

    def test_transcript_route_registered(self):
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and r.path.endswith("/transcript") and "GET" in r.methods:
                return
        pytest.fail("GET .../meetings/{id}/transcript route not found")

    def test_team_retention_routes_registered(self):
        methods = set()
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and "/teams/" in r.path and "retention" in r.path:
                methods.update(r.methods)
        assert "PUT" in methods and "GET" in methods

    def test_admin_sweep_route_registered(self):
        for r in storage_routes.router.routes:
            if hasattr(r, "path") and "retention/sweep" in r.path and "POST" in r.methods:
                return
        pytest.fail("POST /api/v1/admin/retention/sweep route not found")

    def test_handlers_use_auth_pattern(self):
        # Endpoints must require a current user (get_current_user pattern).
        import inspect

        for r in storage_routes.router.routes:
            if not hasattr(r, "endpoint") or r.path.endswith("/sweep"):
                continue
            sig = inspect.signature(r.endpoint)
            params = sig.parameters
            assert "user" in params or "current_user" in params, (
                f"{r.path} handler missing user dependency"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (HTTP level)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorageApiBehavioral:
    """Upload/download/delete + RBAC via TestClient against the seeded DB."""

    @pytest.fixture
    def client(self, _setup_test_db, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.config import settings
        from meeting_notes_ai.main import app

        # Point the app's local backend at a temp dir so tests never write
        # into the repo's data/storage directory.
        monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
        return TestClient(app)

    # ── Upload ────────────────────────────────────────────────────────────────

    def test_upload_requires_auth(self, client):
        resp = client.post(_meeting_audio_url("test-meeting"))
        assert resp.status_code == 401

    def test_upload_audio_201_persists_metadata(self, client):
        meeting_id = _fresh_meeting()
        payload = b"RIFF test audio payload"
        resp = client.post(
            _meeting_audio_url(meeting_id),
            files={"file": ("test.wav", payload, "audio/wav")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["meeting_id"] == meeting_id
        assert data["size_bytes"] == len(payload)
        assert data["sha256"] == hashlib.sha256(payload).hexdigest()
        assert data["content_type"] == "audio/wav"
        assert data["kind"] == "audio"

    def test_upload_duplicate_returns_409(self, client):
        meeting_id = _fresh_meeting()
        files = {"file": ("dup.wav", b"duplicate audio", "audio/wav")}
        first = client.post(
            _meeting_audio_url(meeting_id),
            files=files,
            headers=_auth_headers("test-user-id"),
        )
        assert first.status_code == 201, first.text
        second = client.post(
            _meeting_audio_url(meeting_id),
            files=files,
            headers=_auth_headers("test-user-id"),
        )
        assert second.status_code == 409

    def test_upload_oversize_returns_413(self, client, monkeypatch):
        from meeting_notes_ai.config import settings

        monkeypatch.setattr(settings, "max_audio_size_mb", 1)
        meeting_id = _fresh_meeting()
        big = b"x" * (2 * 1024 * 1024)  # 2 MB > 1 MB cap
        resp = client.post(
            _meeting_audio_url(meeting_id),
            files={"file": ("big.wav", big, "audio/wav")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 413

    def test_upload_bad_mime_returns_415(self, client):
        meeting_id = _fresh_meeting()
        resp = client.post(
            _meeting_audio_url(meeting_id),
            files={"file": ("notes.txt", b"not audio", "text/plain")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 415

    # ── RBAC matrix ───────────────────────────────────────────────────────────

    def test_viewer_cannot_upload(self, client):
        resp = client.post(
            _meeting_audio_url("team-meeting"),
            files={"file": ("v.wav", b"viewer attempt", "audio/wav")},
            headers=_auth_headers("viewer-user-id"),
        )
        assert resp.status_code == 403

    def test_non_member_cannot_upload(self, client):
        resp = client.post(
            _meeting_audio_url("team-meeting"),
            files={"file": ("o.wav", b"outsider", "audio/wav")},
            headers=_auth_headers("other-user-id"),
        )
        assert resp.status_code in (403, 404)

    def test_unknown_meeting_upload_returns_404(self, client):
        resp = client.post(
            _meeting_audio_url("no-such-meeting"),
            files={"file": ("x.wav", b"x", "audio/wav")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 404

    def test_get_audio_requires_auth(self, client):
        resp = client.get(_meeting_audio_url("test-meeting"))
        assert resp.status_code == 401

    def test_owner_can_download_audio(self, client, stored_file):
        resp = client.get(
            _meeting_audio_url(stored_file.meeting_id),
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("audio/wav")
        assert "attachment" in resp.headers.get("content-disposition", "").lower()
        assert resp.content == stored_file.payload

    def test_viewer_can_download_team_audio(self, client, stored_team_file):
        # viewer-user-id is VIEWER on test-team; team-meeting belongs to it.
        resp = client.get(
            _meeting_audio_url("team-meeting"),
            headers=_auth_headers("viewer-user-id"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.content == stored_team_file.payload

    def test_non_member_cannot_download(self, client, stored_file):
        resp = client.get(
            _meeting_audio_url(stored_file.meeting_id),
            headers=_auth_headers("other-user-id"),
        )
        assert resp.status_code in (403, 404)

    def test_get_transcript_returns_txt(self, client):
        resp = client.get(
            "/api/v1/meetings/test-meeting/transcript",
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/plain")
        assert "attachment" in resp.headers.get("content-disposition", "").lower()
        assert "test meeting transcript" in resp.text.lower()

    def test_delete_audio_returns_204(self, client, stored_file):
        resp = client.delete(
            _meeting_audio_url(stored_file.meeting_id),
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 204

    def test_delete_audio_requires_auth(self, client):
        resp = client.delete(_meeting_audio_url("test-meeting"))
        assert resp.status_code == 401

    def test_delete_audio_non_member_forbidden(self, client, stored_file):
        resp = client.delete(
            _meeting_audio_url(stored_file.meeting_id),
            headers=_auth_headers("other-user-id"),
        )
        assert resp.status_code in (403, 404)
