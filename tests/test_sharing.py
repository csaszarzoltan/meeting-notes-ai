"""Pre-development interface and behavioral tests for v0.3.0 Meeting Sharing.

Tests public link generation, listing, revocation, and anonymous access
for meeting summaries. All tests are expected to FAIL until the feature
is implemented (RED phase).

Endpoints under test:
  POST   /api/v1/meetings/{meeting_id}/share          — Generate share link
  GET    /api/v1/meetings/{meeting_id}/shares          — List active shares
  DELETE /api/v1/meetings/{meeting_id}/shares/{share_id} — Revoke share
  GET    /public/shares/{token}                        — Public meeting summary
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import signature
from uuid import uuid4

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick

from fastapi import FastAPI
from pydantic import BaseModel

# ── Helpers (mirror test_app_v2.py) ─────────────────────────────────────────────


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


class TestSharingInterface:
    """Verify sharing route module with correct contracts."""

    # ── Module existence ──────────────────────────────────────────────────────

    def test_sharing_module_importable(self):
        """Routes module exists and exports a router."""
        from meeting_notes_ai.routes.sharing import router

        assert router is not None

    def test_sharing_router_prefix(self):
        """Router prefix is /api/v1/meetings (shares under meeting scope)."""
        from meeting_notes_ai.routes.sharing import router

        assert router.prefix == "/api/v1/meetings"

    def test_sharing_router_has_tags(self):
        """Router has a 'sharing' tag."""
        from meeting_notes_ai.routes.sharing import router

        assert router.tags is not None
        assert "sharing" in router.tags

    def test_public_module_importable(self):
        """Public routes module exists and exports a router."""
        from meeting_notes_ai.routes.public import router

        assert router is not None

    def test_public_router_prefix(self):
        """Public router prefix is /public."""
        from meeting_notes_ai.routes.public import router

        assert router.prefix == "/public"

    def test_public_router_has_tags(self):
        """Public router has a 'public' tag."""
        from meeting_notes_ai.routes.public import router

        assert router.tags is not None
        assert "public" in router.tags

    # ── Request schemas ───────────────────────────────────────────────────────

    def test_share_request_importable(self):
        """ShareRequest schema exists."""
        from meeting_notes_ai.routes.sharing import ShareRequest

        assert ShareRequest is not None
        assert issubclass(ShareRequest, BaseModel)

    def test_share_request_fields(self):
        """ShareRequest has optional expires_in field."""
        from meeting_notes_ai.routes.sharing import ShareRequest

        fields = ShareRequest.model_fields
        assert "expires_in" in fields
        # expires_in is optional
        assert fields["expires_in"].default is None or "default" in repr(fields["expires_in"])

    def test_share_request_expires_in_validator(self):
        """ShareRequest validates expires_in against allowed values."""
        from meeting_notes_ai.routes.sharing import ShareRequest

        # These should all be valid
        for val in ["1h", "24h", "7d", "never", None]:
            req = ShareRequest(expires_in=val)
            assert req.expires_in == val

    # ── Response schemas ──────────────────────────────────────────────────────

    def test_share_response_importable(self):
        """ShareResponse schema exists."""
        from meeting_notes_ai.routes.sharing import ShareResponse

        assert ShareResponse is not None
        assert issubclass(ShareResponse, BaseModel)

    def test_share_response_fields(self):
        """ShareResponse has all required fields."""
        from meeting_notes_ai.routes.sharing import ShareResponse

        fields = ShareResponse.model_fields
        assert "token" in fields
        assert "url" in fields
        assert "expires_at" in fields
        assert "is_active" in fields

    def test_share_response_is_active_defaults_true(self):
        """ShareResponse.is_active defaults to True."""
        from meeting_notes_ai.routes.sharing import ShareResponse

        field = ShareResponse.model_fields["is_active"]
        # is_active should default to True
        default = field.default
        assert default is True

    def test_share_list_response_importable(self):
        """ShareListResponse schema exists."""
        from meeting_notes_ai.routes.sharing import ShareListResponse

        assert ShareListResponse is not None
        assert issubclass(ShareListResponse, BaseModel)

    def test_share_list_response_has_shares(self):
        """ShareListResponse has a 'shares' list field."""
        from meeting_notes_ai.routes.sharing import ShareListResponse

        fields = ShareListResponse.model_fields
        assert "shares" in fields

    def test_share_list_response_shares_is_list_of_share_response(self):
        """ShareListResponse.shares is a list of ShareResponse."""
        from typing import get_origin, get_args

        from meeting_notes_ai.routes.sharing import ShareListResponse, ShareResponse

        fields = ShareListResponse.model_fields
        annotation = fields["shares"].annotation
        # The type should be list[ShareResponse]
        origin = get_origin(annotation)
        assert origin is list, f"Expected list, got {origin}"
        args = get_args(annotation)
        assert ShareResponse in args or any(
            issubclass(a, ShareResponse) for a in args if hasattr(a, "__mro__")
        )

    def test_public_share_response_importable(self):
        """PublicShareResponse schema exists."""
        from meeting_notes_ai.routes.public import PublicShareResponse

        assert PublicShareResponse is not None
        assert issubclass(PublicShareResponse, BaseModel)

    def test_public_share_response_fields(self):
        """PublicShareResponse has all expected meeting summary fields."""
        from meeting_notes_ai.routes.public import PublicShareResponse

        fields = PublicShareResponse.model_fields
        assert "title" in fields
        assert "transcript" in fields
        assert "action_items" in fields
        assert "decisions" in fields
        assert "key_points" in fields
        assert "mode" in fields
        assert "metadata" in fields

    # ── Route registration (sharing router) ───────────────────────────────────

    def test_create_share_route_registered(self):
        """POST /{meeting_id}/share is registered on the sharing router."""
        from meeting_notes_ai.routes.sharing import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                path = r.path.rstrip("/")
                if path.endswith("/share") and "POST" in r.methods:
                    return
        pytest.fail("POST .../{meeting_id}/share route not found on sharing router")

    def test_list_shares_route_registered(self):
        """GET /{meeting_id}/shares is registered on the sharing router."""
        from meeting_notes_ai.routes.sharing import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                path = r.path.rstrip("/")
                if path.endswith("/shares") and "GET" in r.methods:
                    return
        pytest.fail("GET .../{meeting_id}/shares route not found on sharing router")

    def test_revoke_share_route_registered(self):
        """DELETE /{meeting_id}/shares/{share_id} is registered."""
        from meeting_notes_ai.routes.sharing import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                if "shares/" in r.path and "{share_id}" in r.path and "DELETE" in r.methods:
                    return
        pytest.fail(
            "DELETE .../{meeting_id}/shares/{share_id} route not found on sharing router"
        )

    # ── Route registration (public router) ────────────────────────────────────

    def test_public_share_by_token_route_registered(self):
        """GET /public/shares/{token} is registered on the public router."""
        from meeting_notes_ai.routes.public import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                if "shares/" in r.path and "{token}" in r.path and "GET" in r.methods:
                    return
        pytest.fail("GET /public/shares/{token} route not found on public router")

    # ── Handler signatures ────────────────────────────────────────────────────

    def test_create_share_handler_signature(self):
        """create_share_link handler has meeting_id, request, user parameters."""
        from meeting_notes_ai.routes.sharing import create_share_link

        sig = signature(create_share_link)
        params = sig.parameters
        assert "meeting_id" in params
        # Should have request body and user dependency
        body_params = [p for p in params if p in ("request", "body", "share_request")]
        assert len(body_params) >= 1, "Expected a request body parameter"
        assert "user" in params or "current_user" in params

    def test_create_share_handler_is_async(self):
        """create_share_link is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.sharing import create_share_link

        assert inspect.iscoroutinefunction(create_share_link)

    def test_list_shares_handler_signature(self):
        """list_shares handler has meeting_id and user parameters."""
        from meeting_notes_ai.routes.sharing import list_shares

        sig = signature(list_shares)
        assert "meeting_id" in sig.parameters
        assert "user" in sig.parameters
        assert "db" in sig.parameters

    def test_list_shares_handler_is_async(self):
        """list_shares is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.sharing import list_shares

        assert inspect.iscoroutinefunction(list_shares)

    def test_revoke_share_handler_signature(self):
        """revoke_share_link handler has meeting_id, share_id, user parameters."""
        from meeting_notes_ai.routes.sharing import revoke_share_link

        sig = signature(revoke_share_link)
        assert "meeting_id" in sig.parameters
        assert "share_id" in sig.parameters
        assert "user" in sig.parameters

    def test_revoke_share_handler_is_async(self):
        """revoke_share_link is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.sharing import revoke_share_link

        assert inspect.iscoroutinefunction(revoke_share_link)

    def test_get_public_share_handler_signature(self):
        """get_share_by_token handler has token parameter, no auth."""
        from meeting_notes_ai.routes.public import get_share_by_token

        sig = signature(get_share_by_token)
        assert "token" in sig.parameters
        # Public endpoint should NOT require user auth
        assert "user" not in sig.parameters

    def test_get_public_share_handler_is_async(self):
        """get_share_by_token is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.public import get_share_by_token

        assert inspect.iscoroutinefunction(get_share_by_token)

    # ── App wiring ────────────────────────────────────────────────────────────

    def test_sharing_router_included_in_app(self):
        """Sharing router is wired into the FastAPI app."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/api/v1/meetings")
        assert route is not None, "Meetings prefix not found in app"
        # Check that at least one share endpoint is wired under meetings
        share_routes = [r for r in _collect_routes(app) if "share" in r.path.lower()]
        assert len(share_routes) >= 1, "No share-related routes found in app"

    def test_public_router_included_in_app(self):
        """Public router is wired into the FastAPI app."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/public")
        assert route is not None, "/public routes not found in app"

    def test_existing_routes_still_present(self):
        """Pre-existing routes survive after adding sharing."""
        from meeting_notes_ai.main import app

        assert _find_route(app, "/healthz") is not None
        assert _find_route(app, "/api/v1/auth") is not None
        assert _find_route(app, "/api/v1/teams") is not None
        assert _find_route(app, "/api/v1/meetings") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SharedLink Model Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSharedLinkModel:
    """Verify the SharedLink ORM model definition."""

    def test_shared_link_model_importable(self):
        """SharedLink model exists in db.models."""
        from meeting_notes_ai.db.models import SharedLink

        assert SharedLink is not None
        assert hasattr(SharedLink, "__tablename__")

    def test_shared_link_tablename(self):
        """SharedLink maps to 'shared_links' table."""
        from meeting_notes_ai.db.models import SharedLink

        assert SharedLink.__tablename__ == "shared_links"

    def test_shared_link_has_expected_columns(self):
        """SharedLink has all required columns."""
        from meeting_notes_ai.db.models import SharedLink

        cols = {c.name: c for c in SharedLink.__table__.columns}
        assert "id" in cols
        assert "meeting_id" in cols
        assert "team_id" in cols
        assert "created_by" in cols
        assert "token" in cols
        assert "expires_at" in cols
        assert "is_active" in cols

    def test_shared_link_id_is_primary_key(self):
        """SharedLink.id is the primary key."""
        from meeting_notes_ai.db.models import SharedLink

        assert SharedLink.__table__.columns["id"].primary_key is True

    def test_shared_link_id_is_uuid_string(self):
        """SharedLink.id is a String(36) (UUID)."""
        from meeting_notes_ai.db.models import SharedLink

        col = SharedLink.__table__.columns["id"]
        assert hasattr(col.type, "length")
        assert col.type.length == 36

    def test_shared_link_token_is_unique_and_indexed(self):
        """SharedLink.token is unique and indexed."""
        from meeting_notes_ai.db.models import SharedLink

        col = SharedLink.__table__.columns["token"]
        assert col.unique is True
        assert col.index is True

    def test_shared_link_meeting_id_is_foreign_key(self):
        """SharedLink.meeting_id is a FK to meetings.id."""
        from meeting_notes_ai.db.models import SharedLink

        fks = list(SharedLink.meeting_id.foreign_keys)
        assert len(fks) >= 1
        assert any("meetings.id" in str(fk.target_fullname) for fk in fks)

    def test_shared_link_created_by_is_foreign_key(self):
        """SharedLink.created_by is a FK to users.id."""
        from meeting_notes_ai.db.models import SharedLink

        fks = list(SharedLink.created_by.foreign_keys)
        assert len(fks) >= 1
        assert any("users.id" in str(fk.target_fullname) for fk in fks)

    def test_shared_link_team_id_is_nullable(self):
        """SharedLink.team_id is nullable."""
        from meeting_notes_ai.db.models import SharedLink

        assert SharedLink.__table__.columns["team_id"].nullable is True

    def test_shared_link_expires_at_is_nullable(self):
        """SharedLink.expires_at is nullable (permanent links)."""
        from meeting_notes_ai.db.models import SharedLink

        assert SharedLink.__table__.columns["expires_at"].nullable is True

    def test_shared_link_is_active_default_true(self):
        """SharedLink.is_active defaults to True."""
        from meeting_notes_ai.db.models import SharedLink

        col = SharedLink.__table__.columns["is_active"]
        # SQLAlchemy wraps scalar defaults in ScalarElementColumnDefault
        assert col.default is not None
        # Check the underlying Python default value
        assert col.default.arg is True

    def test_shared_link_timestamp_mixin_inherited(self):
        """SharedLink inherits TimestampMixin (created_at, updated_at)."""
        from meeting_notes_ai.db.models import SharedLink

        cols = {c.name: c for c in SharedLink.__table__.columns}
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_shared_link_meeting_relationship(self):
        """SharedLink has a relationship to Meeting."""
        from meeting_notes_ai.db.models import SharedLink

        assert hasattr(SharedLink, "meeting")

    def test_shared_link_creator_relationship(self):
        """SharedLink has a relationship to User (creator)."""
        from meeting_notes_ai.db.models import SharedLink

        assert hasattr(SharedLink, "creator") or hasattr(SharedLink, "created_by_user")

    def test_meeting_has_shared_links_backref(self):
        """Meeting has a back-reference to shared links."""
        from meeting_notes_ai.db.models import Meeting

        assert hasattr(Meeting, "shared_links") or hasattr(Meeting, "shares")


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (HTTP-level — will FAIL until routes are implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSharingBehavioral:
    """Behavioral tests for the sharing endpoints via TestClient.

    These tests verify auth enforcement, correct response shapes, expiration,
    revocation, and access control. They all require full route implementation
    and will fail cleanly (RED phase) until that is done.
    """

    @pytest.fixture
    def client(self, _setup_test_db):
        """Provide a FastAPI TestClient."""
        from fastapi.testclient import TestClient

        from meeting_notes_ai.main import app

        return TestClient(app)

    @pytest.fixture
    def valid_token(self) -> str:
        """Return a valid JWT token for testing."""
        import asyncio

        from meeting_notes_ai.auth import create_access_token

        return asyncio.run(create_access_token("test-user-id"))

    # ── POST /api/v1/meetings/{meeting_id}/share ──────────────────────────────

    def test_create_share_link_requires_auth(self, client):
        """POST /share returns 401 without auth token."""
        response = client.post(
            "/api/v1/meetings/test-meeting/share",
            json={"expires_in": "24h"},
        )
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_create_share_link_success(self, client, valid_token):
        """POST /share returns 201/200 with share link details."""
        from meeting_notes_ai.routes.sharing import ShareResponse

        response = client.post(
            "/api/v1/meetings/test-meeting/share",
            json={"expires_in": "24h"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code in (200, 201), (
            f"Expected 200/201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        # Validate shape matches ShareResponse contract
        assert "token" in data, "Response missing 'token'"
        assert "url" in data, "Response missing 'url'"
        assert "expires_at" in data, "Response missing 'expires_at'"
        assert "is_active" in data, "Response missing 'is_active'"
        assert data["is_active"] is True
        assert isinstance(data["token"], str) and len(data["token"]) > 0
        assert "public/shares/" in data["url"]
        # expires_at should be in the future
        from datetime import datetime

        expires = datetime.fromisoformat(data["expires_at"])
        assert expires > datetime.now(expires.tzinfo)

    def test_create_share_link_without_expiry(self, client, valid_token):
        """POST /share without expires_in still works (defaults to never)."""
        response = client.post(
            "/api/v1/meetings/test-meeting/share",
            json={},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code in (200, 201), (
            f"Expected 200/201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "token" in data
        # expires_at may be None for permanent links
        if data.get("expires_at") is not None:
            from datetime import datetime

            expires = datetime.fromisoformat(data["expires_at"])
            assert expires > datetime.now(expires.tzinfo)

    def test_create_share_link_invalid_expiry(self, client, valid_token):
        """POST /share with invalid expires_in returns 422."""
        response = client.post(
            "/api/v1/meetings/test-meeting/share",
            json={"expires_in": "invalid"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 422, (
            f"Expected 422 for invalid expiry, got {response.status_code}"
        )

    def test_create_share_link_meeting_not_found(self, client, valid_token):
        """POST /share for non-existent meeting returns 404."""
        # Pre-verify route exists (will fail with ModuleNotFoundError until implemented)
        from meeting_notes_ai.routes.sharing import create_share_link

        _ = create_share_link  # ensure route handler is imported
        response = client.post(
            "/api/v1/meetings/non-existent-id/share",
            json={"expires_in": "24h"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 404, (
            f"Expected 404 for unknown meeting, got {response.status_code}"
        )

    def test_create_share_link_non_member_forbidden(self, client, valid_token):
        """POST /share by non-member is forbidden (403)."""
        # Pre-verify route exists
        from meeting_notes_ai.routes.sharing import create_share_link

        _ = create_share_link
        response = client.post(
            "/api/v1/meetings/other-teams-meeting/share",
            json={"expires_in": "24h"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        # Should be 403 (not member) or 404 (not found - don't leak info)
        assert response.status_code in (403, 404), (
            f"Expected 403/404 for non-member, got {response.status_code}"
        )

    def test_create_share_link_team_member_can_share(self, client, valid_token):
        """Meeting with team — team member (admin/member) can share (200)."""
        from meeting_notes_ai.routes.sharing import ShareResponse

        response = client.post(
            "/api/v1/meetings/team-meeting/share",
            json={"expires_in": "7d"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code in (200, 201), (
            f"Expected 200/201 for team member, got {response.status_code}"
        )

    def test_create_share_link_viewer_cannot_share(self, client):
        """Viewer role cannot create share links."""
        # Use a viewer token against a meeting they can see but not share
        import asyncio

        from meeting_notes_ai.auth import create_access_token

        viewer_token = asyncio.run(create_access_token("viewer-user-id"))
        response = client.post(
            "/api/v1/meetings/team-meeting/share",
            json={"expires_in": "24h"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403, (
            f"Expected 403 for viewer, got {response.status_code}"
        )

    # ── GET /api/v1/meetings/{meeting_id}/shares ──────────────────────────────

    def test_list_shares_requires_auth(self, client):
        """GET /shares returns 401 without auth token."""
        response = client.get("/api/v1/meetings/test-meeting/shares")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_list_shares_success(self, client, valid_token):
        """GET /shares returns list of share objects."""
        response = client.get(
            "/api/v1/meetings/test-meeting/shares",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        # Should at minimum be a list (possibly empty)
        if isinstance(data, list):
            shares = data
        elif isinstance(data, dict) and "shares" in data:
            shares = data["shares"]
        else:
            pytest.fail(f"Unexpected response shape: {data}")
        assert isinstance(shares, list)

    def test_list_shares_empty(self, client, valid_token):
        """GET /shares for meeting with no shares returns empty list."""
        response = client.get(
            "/api/v1/meetings/empty-meeting/shares",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        if isinstance(data, list):
            assert len(data) == 0
        elif isinstance(data, dict) and "shares" in data:
            assert len(data["shares"]) == 0

    def test_list_shares_forbidden_no_access(self, client, valid_token):
        """GET /shares for inaccessible meeting returns 403/404."""
        from meeting_notes_ai.routes.sharing import list_shares

        _ = list_shares
        response = client.get(
            "/api/v1/meetings/restricted-meeting/shares",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code in (403, 404)

    # ── DELETE /api/v1/meetings/{meeting_id}/shares/{share_id} ────────────────

    def test_revoke_share_requires_auth(self, client):
        """DELETE /shares/{id} returns 401 without auth token."""
        response = client.delete(
            "/api/v1/meetings/test-meeting/shares/test-share-id",
        )
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_revoke_share_success(self, client, valid_token):
        """DELETE /shares/{id} succeeds and marks link inactive."""
        response = client.delete(
            "/api/v1/meetings/test-meeting/shares/test-share-id",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        # Should return 200 or 204
        assert response.status_code in (200, 204), (
            f"Expected 200/204 for revoke, got {response.status_code}: {response.text}"
        )

    def test_revoke_share_not_found(self, client, valid_token):
        """DELETE /shares/{id} for unknown share returns 404."""
        from meeting_notes_ai.routes.sharing import revoke_share_link

        _ = revoke_share_link
        response = client.delete(
            "/api/v1/meetings/test-meeting/shares/non-existent-share",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 404, (
            f"Expected 404, got {response.status_code}"
        )

    def test_revoke_share_forbidden_not_creator(self, client):
        """DELETE /shares/{id} by non-creator returns 403."""
        import asyncio

        from meeting_notes_ai.auth import create_access_token

        other_user_token = asyncio.run(create_access_token("other-user-id"))
        response = client.delete(
            "/api/v1/meetings/test-meeting/shares/creator-owned-share",
            headers={"Authorization": f"Bearer {other_user_token}"},
        )
        # 403: only creator or admin can revoke
        assert response.status_code == 403, (
            f"Expected 403 for non-creator, got {response.status_code}"
        )

    def test_revoke_share_team_admin_can_revoke(self, client):
        """Team admin can revoke any share in their team's meeting."""
        import asyncio

        from meeting_notes_ai.auth import create_access_token

        admin_token = asyncio.run(create_access_token("admin-user-id"))
        response = client.delete(
            "/api/v1/meetings/team-meeting/shares/other-creator-share",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Admin should have permission even if not the creator
        assert response.status_code in (200, 204), (
            f"Expected 200/204 for admin revoke, got {response.status_code}"
        )

    # ── GET /public/shares/{token} ────────────────────────────────────────────

    def test_public_share_success(self, client):
        """GET /public/shares/{token} returns meeting summary (no auth)."""
        response = client.get("/public/shares/valid-test-token")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        # Must contain meeting summary fields
        assert "title" in data
        assert "transcript" in data
        assert "action_items" in data
        assert "decisions" in data
        assert "key_points" in data
        assert "mode" in data
        assert "metadata" in data

    def test_public_share_invalid_token_returns_404(self, client):
        """GET /public/shares/{token} with invalid token returns 404."""
        from meeting_notes_ai.routes.public import get_share_by_token

        _ = get_share_by_token
        response = client.get("/public/shares/invalid-token")
        assert response.status_code == 404, (
            f"Expected 404 for invalid token, got {response.status_code}"
        )

    def test_public_share_expired_token_returns_404(self, client):
        """GET /public/shares/{token} with expired token returns 404."""
        from meeting_notes_ai.routes.public import get_share_by_token

        _ = get_share_by_token
        response = client.get("/public/shares/expired-test-token")
        assert response.status_code == 404, (
            f"Expected 404 for expired token, got {response.status_code}"
        )

    def test_public_share_revoked_token_returns_404(self, client):
        """GET /public/shares/{token} with revoked token returns 404."""
        from meeting_notes_ai.routes.public import get_share_by_token

        _ = get_share_by_token
        response = client.get("/public/shares/revoked-test-token")
        assert response.status_code == 404, (
            f"Expected 404 for revoked token, got {response.status_code}"
        )

    def test_public_share_no_auth_header_needed(self, client):
        """GET /public/shares/{token} works without any Authorization header."""
        response = client.get(
            "/public/shares/valid-test-token",
            headers={},  # No auth
        )
        assert response.status_code == 200, (
            f"Public endpoint should not require auth, got {response.status_code}"
        )

    def test_public_share_teams_meeting_not_leaked(self, client):
        """Public endpoint does not leak internal fields (team_id, user_id)."""
        response = client.get("/public/shares/valid-test-token")
        assert response.status_code == 200
        data = response.json()
        # Sensitive fields should NOT appear in public response
        sensitive = ["user_id", "team_id", "created_by", "is_active", "token"]
        for field in sensitive:
            assert field not in data, f"Public response leaked '{field}'"
