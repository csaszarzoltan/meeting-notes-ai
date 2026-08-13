"""Pre-development interface and behavioral tests for API Key Management.

Tests the ApiKey ORM model and API Key CRUD routes. All tests are expected
to FAIL until the feature is implemented (RED phase).

Modules under test:
  src/meeting_notes_ai/db/models.py        — ApiKey model
  src/meeting_notes_ai/routes/api_keys.py  — API Key CRUD routes
"""

from __future__ import annotations

import asyncio
from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick

from fastapi import FastAPI

# ── Helpers (mirror test_app.py) ─────────────────────────────────────────────


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
# ApiKey Model Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyModel:
    """Verify the ApiKey ORM model definition."""

    def test_api_key_model_importable(self):
        """ApiKey model exists in db.models."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey is not None
        assert hasattr(ApiKey, "__tablename__")

    def test_api_key_tablename(self):
        """ApiKey maps to 'api_keys' table."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey.__tablename__ == "api_keys"

    def test_api_key_has_expected_columns(self):
        """ApiKey has all required columns."""
        from meeting_notes_ai.db.models import ApiKey

        cols = {c.name: c for c in ApiKey.__table__.columns}
        assert "id" in cols
        assert "user_id" in cols
        assert "key_prefix" in cols
        assert "hashed_key" in cols
        assert "tier" in cols
        assert "is_active" in cols
        assert "name" in cols
        assert "last_used_at" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_api_key_id_is_primary_key(self):
        """ApiKey.id is the primary key."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey.__table__.columns["id"].primary_key is True

    def test_api_key_id_is_uuid_string(self):
        """ApiKey.id is a String (UUID)."""
        from meeting_notes_ai.db.models import ApiKey

        col = ApiKey.__table__.columns["id"]
        assert hasattr(col.type, "length")
        assert col.type.length >= 36

    def test_api_key_user_id_is_foreign_key(self):
        """ApiKey.user_id is a FK to users.id."""
        from meeting_notes_ai.db.models import ApiKey

        fks = list(ApiKey.user_id.foreign_keys)
        assert len(fks) >= 1
        assert any("users.id" in str(fk.target_fullname) for fk in fks)

    def test_api_key_key_prefix_length(self):
        """ApiKey.key_prefix stores the first 8 characters."""
        from meeting_notes_ai.db.models import ApiKey

        col = ApiKey.__table__.columns["key_prefix"]
        assert hasattr(col.type, "length")
        assert col.type.length >= 8

    def test_api_key_hashed_key_not_nullable(self):
        """ApiKey.hashed_key is not nullable (always hashed)."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey.__table__.columns["hashed_key"].nullable is False

    def test_api_key_tier_defaults_free(self):
        """ApiKey.tier defaults to 'free'."""
        from meeting_notes_ai.db.models import ApiKey

        col = ApiKey.__table__.columns["tier"]
        default = col.default
        # Either via Python default or server_default
        assert default is not None or not col.nullable
        # The column should have 'free' as its default
        if hasattr(default, "arg"):
            assert default.arg == "free"
        elif hasattr(default, "args"):
            assert "free" in default.args
        elif hasattr(col, "default_factory"):
            pass  # handled at Python level

    def test_api_key_is_active_default_true(self):
        """ApiKey.is_active defaults to True."""
        from meeting_notes_ai.db.models import ApiKey

        col = ApiKey.__table__.columns["is_active"]
        assert col.default is True or (hasattr(col.default, "arg") and col.default.arg is True)

    def test_api_key_name_is_nullable(self):
        """ApiKey.name is nullable (user-friendly label, optional)."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey.__table__.columns["name"].nullable is True

    def test_api_key_last_used_at_is_nullable(self):
        """ApiKey.last_used_at is nullable (never used yet)."""
        from meeting_notes_ai.db.models import ApiKey

        assert ApiKey.__table__.columns["last_used_at"].nullable is True

    def test_api_key_timestamp_mixin_inherited(self):
        """ApiKey inherits TimestampMixin (created_at, updated_at)."""
        from meeting_notes_ai.db.models import ApiKey

        cols = {c.name: c for c in ApiKey.__table__.columns}
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_api_key_user_relationship(self):
        """ApiKey has a relationship to User."""
        from meeting_notes_ai.db.models import ApiKey

        assert hasattr(ApiKey, "user") or hasattr(ApiKey, "owner")

    def test_user_has_api_keys_backref(self):
        """User has a back-reference to api_keys."""
        from meeting_notes_ai.db.models import User

        assert hasattr(User, "api_keys")


# ═══════════════════════════════════════════════════════════════════════════════
# API Key Router Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyRouterInterface:
    """Verify API Key route module with correct contracts."""

    # ── Module existence ──────────────────────────────────────────────────

    def test_api_keys_module_importable(self):
        """Routes module exists and exports a router."""
        from meeting_notes_ai.routes.api_keys import router

        assert router is not None

    def test_api_keys_router_prefix(self):
        """Router prefix is /api/v1/api-keys."""
        from meeting_notes_ai.routes.api_keys import router

        assert router.prefix == "/api/v1/api-keys"

    def test_api_keys_router_has_tags(self):
        """Router has an 'api-keys' tag."""
        from meeting_notes_ai.routes.api_keys import router

        assert router.tags is not None
        assert "api-keys" in router.tags or "api_keys" in router.tags

    # ── Route registration ────────────────────────────────────────────────

    def test_create_api_key_route_registered(self):
        """POST /api-keys is registered on the router."""
        from meeting_notes_ai.routes.api_keys import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                path = r.path.rstrip("/")
                if path in ("", "/") and "POST" in r.methods:
                    return
                if path.endswith("/") and "POST" in r.methods:
                    return
        # Fallback: check the last path segment
        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                if "POST" in r.methods:
                    return
        pytest.fail("POST route not found on api-keys router")

    def test_list_api_keys_route_registered(self):
        """GET /api-keys is registered on the router."""
        from meeting_notes_ai.routes.api_keys import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                if "GET" in r.methods:
                    return
        pytest.fail("GET route not found on api-keys router")

    def test_delete_api_key_route_registered(self):
        """DELETE /api-keys/{key_id} is registered on the router."""
        from meeting_notes_ai.routes.api_keys import router

        for r in router.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                path = r.path.rstrip("/")
                if "{key_id}" in path and "DELETE" in r.methods:
                    return
        pytest.fail("DELETE .../{key_id} route not found on api-keys router")

    # ── Handler signatures ────────────────────────────────────────────────

    def test_create_api_key_handler_is_async(self):
        """create_api_key is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.api_keys import create_api_key

        assert inspect.iscoroutinefunction(create_api_key)

    def test_create_api_key_handler_signature(self):
        """create_api_key handler has user dependency."""
        from meeting_notes_ai.routes.api_keys import create_api_key

        sig = signature(create_api_key)
        assert "user" in sig.parameters or "current_user" in sig.parameters

    def test_list_api_keys_handler_is_async(self):
        """list_api_keys is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.api_keys import list_api_keys

        assert inspect.iscoroutinefunction(list_api_keys)

    def test_list_api_keys_handler_signature(self):
        """list_api_keys handler has user and db parameters."""
        from meeting_notes_ai.routes.api_keys import list_api_keys

        sig = signature(list_api_keys)
        assert "user" in sig.parameters or "current_user" in sig.parameters

    def test_delete_api_key_handler_is_async(self):
        """delete_api_key is a coroutine function."""
        import inspect

        from meeting_notes_ai.routes.api_keys import delete_api_key

        assert inspect.iscoroutinefunction(delete_api_key)

    def test_delete_api_key_handler_signature(self):
        """delete_api_key handler has key_id, user, db parameters."""
        from meeting_notes_ai.routes.api_keys import delete_api_key

        sig = signature(delete_api_key)
        assert "key_id" in sig.parameters
        assert "user" in sig.parameters or "current_user" in sig.parameters

    # ── Response schemas ──────────────────────────────────────────────────

    def test_create_api_key_response_importable(self):
        """CreateApiKeyResponse schema exists."""
        from meeting_notes_ai.routes.api_keys import CreateApiKeyResponse

        assert CreateApiKeyResponse is not None

    def test_create_api_key_response_has_full_key(self):
        """CreateApiKeyResponse has 'key' field (full API key, shown once)."""
        from meeting_notes_ai.routes.api_keys import CreateApiKeyResponse

        fields = CreateApiKeyResponse.model_fields
        assert "key" in fields

    def test_create_api_key_response_has_key_prefix(self):
        """CreateApiKeyResponse has 'key_prefix' field."""
        from meeting_notes_ai.routes.api_keys import CreateApiKeyResponse

        fields = CreateApiKeyResponse.model_fields
        assert "key_prefix" in fields

    def test_api_key_list_response_importable(self):
        """ApiKeyListResponse schema exists."""
        from meeting_notes_ai.routes.api_keys import ApiKeyListResponse

        assert ApiKeyListResponse is not None

    def test_api_key_list_response_has_api_keys(self):
        """ApiKeyListResponse has 'api_keys' list field."""
        from meeting_notes_ai.routes.api_keys import ApiKeyListResponse

        fields = ApiKeyListResponse.model_fields
        assert "api_keys" in fields

    def test_api_key_item_response_has_prefix_only(self):
        """ApiKeyItemResponse has key_prefix, name, created_at — NOT full key."""
        from meeting_notes_ai.routes.api_keys import ApiKeyItemResponse

        fields = ApiKeyItemResponse.model_fields
        assert "key_prefix" in fields
        assert "name" in fields
        assert "created_at" in fields
        # The full key should NOT be in the list response
        assert "key" not in fields

    # ── App wiring ────────────────────────────────────────────────────────

    def test_api_keys_router_included_in_app(self):
        """API keys router is wired into the FastAPI app."""
        from meeting_notes_ai.main import app

        route = _find_route(app, "/api/v1/api-keys")
        assert route is not None, "api-keys prefix not found in app"

    def test_existing_routes_still_present(self):
        """Pre-existing routes survive after adding api-keys."""
        from meeting_notes_ai.main import app

        assert _find_route(app, "/healthz") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (HTTP-level — will FAIL until routes are implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyBehavioral:
    """Behavioral tests for API Key CRUD endpoints via TestClient.

    These tests verify auth enforcement, correct response shapes, and access
    control. They all require full route implementation and will fail cleanly
    (RED phase) until that is done.
    """

    @pytest.fixture
    def client(self):
        """Provide a FastAPI TestClient."""
        from fastapi.testclient import TestClient

        from meeting_notes_ai.main import app

        return TestClient(app)

    @pytest.fixture
    def valid_token(self) -> str:
        """Return a valid JWT token for testing."""
        from meeting_notes_ai.auth import create_access_token

        return asyncio.run(create_access_token("test-user-id"))

    # ── POST /api/v1/api-keys ─────────────────────────────────────────────

    def test_create_api_key_requires_auth(self, client):
        """POST /api-keys returns 401 without auth token."""
        response = client.post("/api/v1/api-keys", json={"name": "My Key"})
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_create_api_key_success(self, client, valid_token):
        """POST /api-keys returns 201 with full key in response."""
        response = client.post(
            "/api/v1/api-keys",
            json={"name": "My Key"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "key" in data, "Response missing 'key' (full API key)"
        assert "key_prefix" in data, "Response missing 'key_prefix'"
        # Full key should be a string of reasonable length (43 chars for token_urlsafe(32))
        assert isinstance(data["key"], str) and len(data["key"]) >= 20
        # key_prefix should match the first 8 chars of the full key
        assert data["key"][:8] == data["key_prefix"]

    def test_create_api_key_returns_full_key_once(self, client, valid_token):
        """The full key is returned in the response (shown only at creation)."""
        response = client.post(
            "/api/v1/api-keys",
            json={"name": "Once Only Key"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        # The key should look like a URL-safe base64 token
        assert data["key"].replace("-", "").replace("_", "").isalnum()

    def test_create_api_key_without_name(self, client, valid_token):
        """POST /api-keys without name still works (name is optional)."""
        response = client.post(
            "/api/v1/api-keys",
            json={},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "key" in data

    # ── GET /api/v1/api-keys ──────────────────────────────────────────────

    def test_list_api_keys_requires_auth(self, client):
        """GET /api-keys returns 401 without auth token."""
        response = client.get("/api/v1/api-keys")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_list_api_keys_success(self, client, valid_token):
        """GET /api-keys returns list of keys with prefix only."""
        response = client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        # Response should contain api_keys list
        if isinstance(data, list):
            keys = data
        elif isinstance(data, dict) and "api_keys" in data:
            keys = data["api_keys"]
        else:
            pytest.fail(f"Unexpected response shape: {data}")
        assert isinstance(keys, list)

    def test_list_api_keys_shows_prefix_not_full_key(self, client, valid_token):
        """List response shows key_prefix, NOT the full key."""
        # First create a key
        create_resp = client.post(
            "/api/v1/api-keys",
            json={"name": "Hidden Key"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert create_resp.status_code == 201
        _ = create_resp.json()["key"]  # ensure create worked

        # Then list keys
        list_resp = client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        keys = data if isinstance(data, list) else data.get("api_keys", [])
        for item in keys:
            # The full key should never appear in list responses
            assert "key" not in item or item["key"] is None, (
                "Full key should not be exposed in list response"
            )
            # But key_prefix should be visible
            assert "key_prefix" in item

    def test_list_api_keys_empty(self, client, valid_token):
        """GET /api-keys for user with no keys returns empty list."""
        response = client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        keys = data if isinstance(data, list) else data.get("api_keys", [])
        assert len(keys) == 0

    # ── DELETE /api/v1/api-keys/{key_id} ──────────────────────────────────

    def test_delete_api_key_requires_auth(self, client):
        """DELETE /api-keys/{id} returns 401 without auth token."""
        response = client.delete("/api/v1/api-keys/test-key-id")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}: {response.text}"
        )

    def test_delete_api_key_sets_inactive(self, client, valid_token):
        """DELETE /api-keys/{id} soft-deletes (sets is_active=False)."""
        # Create a key first
        create_resp = client.post(
            "/api/v1/api-keys",
            json={"name": "To Delete"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert create_resp.status_code == 201
        key_data = create_resp.json()

        # Delete it
        delete_resp = client.delete(
            f"/api/v1/api-keys/{key_data['id']}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert delete_resp.status_code in (200, 204), (
            f"Expected 200/204 for delete, got {delete_resp.status_code}: {delete_resp.text}"
        )

        # List should no longer show the key (or show it as inactive)
        list_resp = client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        keys = data if isinstance(data, list) else data.get("api_keys", [])
        # The deleted key should either be absent or have is_active=False
        for k in keys:
            if k.get("id") == key_data["id"]:
                assert k.get("is_active") is False, "Deleted key should have is_active=False"

    def test_delete_api_key_not_found(self, client, valid_token):
        """DELETE /api-keys/{id} for unknown key returns 404."""
        response = client.delete(
            "/api/v1/api-keys/non-existent-key-id",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_delete_api_key_forbidden_not_owner(self, client):
        """DELETE /api-keys/{id} by another user returns 403."""
        from meeting_notes_ai.auth import create_access_token

        other_token = asyncio.run(create_access_token("other-user-id"))
        response = client.delete(
            "/api/v1/api-keys/other-users-key",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        # 403: only the key owner can delete their own key
        assert response.status_code in (403, 404), (
            f"Expected 403/404 for non-owner, got {response.status_code}"
        )
