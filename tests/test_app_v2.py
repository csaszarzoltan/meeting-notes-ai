"""Interface tests for v0.2.0 app routing — verify all new routers are included.

These tests check that the FastAPI application wires up the auth, batch,
team, and webhook routers correctly.
"""

from __future__ import annotations

import pytest

# Mark as integration (uses TestClient/AsyncClient)
pytestmark = pytest.mark.integration

from fastapi import FastAPI

from meeting_notes_ai.main import app


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


# ── Interface Tests (must PASS once wiring is done) ───────────────────────────


class TestAppV2Interface:
    """Verify v0.2.0 routers are registered."""

    # Note: These tests will FAIL until main.py is updated by the developer
    # to include the new routers. This is by design — they document the
    # expected app wiring.

    def test_app_is_fastapi_instance(self):
        """App should be a FastAPI instance."""
        assert isinstance(app, FastAPI)

    def test_auth_router_included(self):
        """Auth router should be included in the app."""
        route = _find_route(app, "/api/v1/auth")
        assert route is not None, "/api/v1/auth routes not found"

    def test_auth_signup_routes_available(self):
        """POST /api/v1/auth/signup should be registered."""
        for r in _collect_routes(app):
            if "signup" in r.path and "POST" in (getattr(r, "methods", set())):
                return
        pytest.fail("POST /api/v1/auth/signup not found")

    def test_auth_login_routes_available(self):
        """POST /api/v1/auth/login should be registered."""
        for r in _collect_routes(app):
            if "login" in r.path and "POST" in (getattr(r, "methods", set())):
                return
        pytest.fail("POST /api/v1/auth/login not found")

    def test_batch_router_included(self):
        """Batch router should be included in the app."""
        route = _find_route(app, "/api/v1/batches")
        assert route is not None, "/api/v1/batches routes not found"

    def test_batch_create_route_available(self):
        """POST /api/v1/batches should be registered."""
        for r in _collect_routes(app):
            if r.path.rstrip("/") == "/api/v1/batches" and "POST" in (getattr(r, "methods", set())):
                return
        pytest.fail("POST /api/v1/batches not found")

    def test_batch_status_route_available(self):
        """GET /api/v1/batches/{batch_id} should be registered."""
        for r in _collect_routes(app):
            if "batches/" in r.path and "GET" in (getattr(r, "methods", set())):
                return
        pytest.fail("GET /api/v1/batches/{batch_id} not found")

    def test_team_router_included(self):
        """Team router should be included in the app."""
        route = _find_route(app, "/api/v1/teams")
        assert route is not None, "/api/v1/teams routes not found"

    def test_team_create_route_available(self):
        """POST /api/v1/teams should be registered."""
        for r in _collect_routes(app):
            if r.path.rstrip("/") == "/api/v1/teams" and "POST" in (getattr(r, "methods", set())):
                return
        pytest.fail("POST /api/v1/teams not found")

    def test_webhook_router_included(self):
        """Webhook router should be included in the app."""
        route = _find_route(app, "/api/v1/webhooks")
        assert route is not None, "/api/v1/webhooks routes not found"

    def test_webhook_create_route_available(self):
        """POST /api/v1/webhooks should be registered."""
        for r in _collect_routes(app):
            if r.path.rstrip("/") == "/api/v1/webhooks" and "POST" in (getattr(r, "methods", set())):
                return
        pytest.fail("POST /api/v1/webhooks not found")

    def test_existing_routes_still_work(self):
        """v0.1.0 routes should still be registered."""
        route = _find_route(app, "/healthz")
        assert route is not None, "/healthz not found"
        route = _find_route(app, "/api/v1/meetings")
        assert route is not None, "/api/v1/meetings not found"
