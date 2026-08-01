"""Interface and behavioral tests for FastAPI app instantiation and health endpoint."""

from __future__ import annotations

import pytest

# Mark as integration (uses TestClient/AsyncClient)
pytestmark = pytest.mark.integration

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
        assert app.version == "0.6.2"

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
        assert result.version == "0.6.2"
        assert "app" in result.services

    def test_client_get_healthz_returns_200(self):
        """TestClient GET /healthz should return 200 OK with health data."""
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.6.2"


# ── Rate Limit Response Headers (P1) ──────────────────────────────────────────
# These tests fail RED until Task 1.1 (RateLimitMiddleware + headers) is
# implemented.  The middleware doesn't exist in v0.3.0, so no X-RateLimit-*
# headers appear on any response and no 429 is ever returned.


class TestRateLimitHeaders:
    """Verify rate limit response headers (Task 1.1 — RED until P1)."""

    # ── Interface tests ────────────────────────────────────────────────────

    def test_200_response_includes_x_ratelimit_limit(self):
        """Every response includes X-RateLimit-Limit header."""
        client = TestClient(app)
        response = client.get("/healthz")
        assert "X-RateLimit-Limit" in response.headers

    def test_200_response_includes_x_ratelimit_remaining(self):
        """Every response includes X-RateLimit-Remaining header."""
        client = TestClient(app)
        response = client.get("/healthz")
        assert "X-RateLimit-Remaining" in response.headers

    def test_200_response_includes_x_ratelimit_reset(self):
        """Every response includes X-RateLimit-Reset header."""
        client = TestClient(app)
        response = client.get("/healthz")
        assert "X-RateLimit-Reset" in response.headers

    def test_x_ratelimit_limit_is_int(self):
        """X-RateLimit-Limit value is an integer."""
        client = TestClient(app)
        response = client.get("/healthz")
        value = response.headers.get("X-RateLimit-Limit")
        assert value is not None, "X-RateLimit-Limit header missing"
        assert value.isdigit(), f"Expected integer, got {value!r}"

    def test_x_ratelimit_remaining_is_int(self):
        """X-RateLimit-Remaining value is an integer."""
        client = TestClient(app)
        response = client.get("/healthz")
        value = response.headers.get("X-RateLimit-Remaining")
        assert value is not None, "X-RateLimit-Remaining header missing"
        assert value.isdigit(), f"Expected integer, got {value!r}"

    def test_x_ratelimit_reset_is_int(self):
        """X-RateLimit-Reset value is an integer (seconds)."""
        client = TestClient(app)
        response = client.get("/healthz")
        value = response.headers.get("X-RateLimit-Reset")
        assert value is not None, "X-RateLimit-Reset header missing"
        assert value.isdigit(), f"Expected integer, got {value!r}"

    def test_429_response_includes_retry_after(self):
        """429 response includes Retry-After header."""
        # Without rate limiting there is no 429 — this fails RED
        client = TestClient(app)
        # Force 429 by hitting a non-existent endpoint with many requests
        for _ in range(200):
            client.get("/healthz")
        response = client.get("/healthz")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"].isdigit()

    def test_429_response_body_shape(self):
        """429 body has detail and retry_after_seconds keys."""
        client = TestClient(app)
        for _ in range(200):
            client.get("/healthz")
        response = client.get("/healthz")
        assert response.status_code == 429
        data = response.json()
        assert "detail" in data
        assert "retry_after_seconds" in data
        assert isinstance(data["retry_after_seconds"], int | float)

    # ── Behavioral tests (xfail until P1) ──────────────────────────────────

    def test_x_ratelimit_remaining_decrements(self):
        """X-RateLimit-Remaining decrements with each request."""
        client = TestClient(app)
        headers = {"X-Forwarded-For": "198.51.100.77"}
        resp1 = client.get("/healthz", headers=headers)
        remaining1 = int(resp1.headers["X-RateLimit-Remaining"])
        resp2 = client.get("/healthz", headers=headers)
        remaining2 = int(resp2.headers["X-RateLimit-Remaining"])
        assert remaining2 < remaining1, f"Remaining did not decrement: {remaining1} → {remaining2}"

    def test_x_ratelimit_reset_is_positive(self):
        """X-RateLimit-Reset value is a positive integer."""
        client = TestClient(app)
        response = client.get("/healthz")
        value = int(response.headers["X-RateLimit-Reset"])
        assert value > 0, f"Expected positive reset seconds, got {value}"

    def test_429_retry_after_is_seconds_to_next_token(self):
        """429 Retry-After is seconds until bucket has at least 1 token."""
        client = TestClient(app)
        for _ in range(200):
            client.get("/healthz")
        response = client.get("/healthz")
        assert response.status_code == 429
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0, f"Expected positive Retry-After, got {retry_after}"
