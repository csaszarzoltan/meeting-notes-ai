"""Interface and behavioral tests for FastAPI app instantiation and health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from meeting_notes_ai.main import app
from meeting_notes_ai.routes.health import router as health_router
from meeting_notes_ai.routes.meetings import router as meetings_router

# ── Helper ────────────────────────────────────────────────────────────────────


def _collect_routes(fastapi_app: FastAPI) -> list:
    """Collect all APIRoute objects, traversing _IncludedRouter wrappers."""
    collected = []
    for r in fastapi_app.routes:
        if type(r).__name__ == "_IncludedRouter":
            collected.extend(r.original_router.routes)
        elif hasattr(r, "path"):
            collected.append(r)
    return collected


def _find_route(fastapi_app: FastAPI, path: str):
    """Find an APIRoute by path, traversing included routers."""
    for r in _collect_routes(fastapi_app):
        if r.path == path:
            return r
    return None


# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestAppInterface:
    """Verify the FastAPI app is correctly configured."""

    def test_app_is_fastapi_instance(self):
        """App should be a FastAPI instance with expected metadata."""
        assert isinstance(app, FastAPI)
        assert app.title == "MeetingNotesAI"
        assert app.version == "0.2.0"

    def test_health_router_included(self):
        """Health check router should be included in the app."""
        route = _find_route(app, "/healthz")
        assert route is not None, "/healthz route not found"

    def test_meetings_router_included(self):
        """Meetings router should be included in the app."""
        route = _find_route(app, "/api/v1/meetings")
        assert route is not None, "/api/v1/meetings route not found"

    def test_health_check_is_get(self):
        """Health check endpoint should be a GET route."""
        route = _find_route(app, "/healthz")
        assert route is not None, "/healthz route not found"
        assert "GET" in route.methods

    def test_meetings_route_is_post(self):
        """Meetings endpoint should be a POST route accepting UploadFile."""
        route = _find_route(app, "/api/v1/meetings")
        assert route is not None, "/api/v1/meetings route not found"
        assert "POST" in route.methods

    def test_health_router_has_tags(self):
        """Health router should have appropriate tags."""
        assert hasattr(health_router, "tags")

    def test_meetings_router_has_tags(self):
        """Meetings router should have appropriate tags."""
        assert hasattr(meetings_router, "tags")


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestAppBehavioral:
    """Verify app behavior with real implementation."""

    def test_health_check_returns_healthy_response(self):
        """Calling health_check should return a valid HealthResponse."""
        import asyncio

        from meeting_notes_ai.routes.health import health_check

        result = asyncio.run(health_check())
        assert result.status == "healthy"
        assert result.version == "0.1.0"
        assert "app" in result.services

    def test_client_get_healthz_returns_200(self):
        """TestClient GET /healthz should return 200 OK with health data."""
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
