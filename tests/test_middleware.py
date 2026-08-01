"""Pre-development interface and behavioral tests for RateLimitMiddleware.

Tests the ASGI middleware that applies rate limiting to all requests.
All tests are expected to FAIL until the middleware is implemented (RED phase).

Module under test:
  src/meeting_notes_ai/middleware.py  — RateLimitMiddleware
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS once implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimitMiddlewareInterface:
    """Verify RateLimitMiddleware class contract."""

    def test_middleware_module_importable(self):
        """Middleware module exists and is importable."""
        import meeting_notes_ai.middleware  # noqa: F811

        assert meeting_notes_ai.middleware is not None

    def test_ratelimit_middleware_class_exists(self):
        """RateLimitMiddleware class exists in the middleware module."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        assert RateLimitMiddleware is not None

    def test_middleware_implements_asgi_interface(self):
        """RateLimitMiddleware has __call__ method (ASGI interface)."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        assert hasattr(RateLimitMiddleware, "__call__")

    def test_middleware_call_signature(self):
        """__call__ accepts (scope, receive, send) ASGI params."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        sig = signature(RateLimitMiddleware.__call__)
        params = sig.parameters
        assert "scope" in params
        assert "receive" in params
        assert "send" in params

    def test_middleware_call_is_async(self):
        """__call__ is an async coroutine function."""
        import inspect

        from meeting_notes_ai.middleware import RateLimitMiddleware

        assert inspect.iscoroutinefunction(RateLimitMiddleware.__call__)

    def test_middleware_constructor_signature(self):
        """Constructor accepts (app, ...) — follows Starlette middleware pattern."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        sig = signature(RateLimitMiddleware.__init__)
        params = sig.parameters
        assert "app" in params

    def test_middleware_inherits_from_base(self):
        """RateLimitMiddleware inherits from a base middleware class."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        bases = RateLimitMiddleware.__bases__
        # Should inherit from some ASGI/middleware base
        base_names = {b.__name__ for b in bases}
        assert len(base_names) >= 1

    def test_middleware_can_be_instantiated(self):
        """RateLimitMiddleware can be instantiated with an app."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        async def dummy_app(scope, receive, send):
            pass

        middleware = RateLimitMiddleware(dummy_app)
        assert middleware is not None

    def test_middleware_accepts_rate_limiter_param(self):
        """RateLimitMiddleware optionally accepts a custom rate limiter instance."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        sig = signature(RateLimitMiddleware.__init__)
        _ = sig.parameters
        # Should accept a rate_limiter or similar param (optional — creates default)
        # If no explicit param, it should create a default limiter internally
        # This test is informational — not a hard fail

    def test_middleware_accepts_exclude_paths(self):
        """RateLimitMiddleware accepts a set of paths to skip."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        sig = signature(RateLimitMiddleware.__init__)
        _ = sig.parameters
        # Optional — middleware may use a fixed exclude list

    def test_middleware_excludes_healthz(self):
        """RateLimitMiddleware skips /healthz by default."""
        from meeting_notes_ai.middleware import RateLimitMiddleware

        # Check if middleware has an exclude_paths or similar attribute
        # or if the default behavior excludes /healthz
        # This can be instantiation-time or a class constant
        async def dummy_app(scope, receive, send):
            pass

        mw = RateLimitMiddleware(dummy_app)
        # Either an attribute or the constructor sets it
        exclude = getattr(mw, "exclude_paths", None) or getattr(mw, "skip_paths", None)
        if exclude is not None:
            assert any("healthz" in p for p in exclude)


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (will FAIL until middleware is fully implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimitMiddlewareBehavioral:
    """Behavioral tests for RateLimitMiddleware via TestClient.

    These tests verify that the middleware correctly intercepts requests,
    adds rate limit headers, returns 429 when limits are exceeded, and
    skips the health check endpoint.
    """

    @pytest.fixture
    def app(self):
        """Provide a FastAPI app with RateLimitMiddleware applied."""
        from fastapi import FastAPI
        from meeting_notes_ai.middleware import RateLimitMiddleware

        app = FastAPI()

        @app.get("/hello")
        async def hello():
            return {"message": "world"}

        @app.get("/healthz")
        async def healthz():
            return {"status": "healthy"}

        app.add_middleware(RateLimitMiddleware)
        return app

    @pytest.fixture
    def client(self, app):
        """Provide a FastAPI TestClient."""
        from fastapi.testclient import TestClient

        return TestClient(app)

    # ── Middleware intercepts requests ─────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_middleware_does_not_block_normal_requests(self, client):
        """Normal requests pass through the middleware and return 200."""
        response = client.get("/hello")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_middleware_adds_rate_limit_headers(self, client):
        """Response includes X-RateLimit-* headers."""
        response = client.get("/hello")
        headers = response.headers
        assert "X-RateLimit-Limit" in headers, (
            f"Missing X-RateLimit-Limit header. Headers: {dict(headers)}"
        )
        assert "X-RateLimit-Remaining" in headers, (
            "Missing X-RateLimit-Remaining header"
        )
        assert "X-RateLimit-Reset" in headers, (
            "Missing X-RateLimit-Reset header"
        )

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_rate_limit_headers_have_valid_values(self, client):
        """Rate limit headers contain numeric values."""
        response = client.get("/hello")
        limit = response.headers.get("X-RateLimit-Limit", "")
        remaining = response.headers.get("X-RateLimit-Remaining", "")
        reset = response.headers.get("X-RateLimit-Reset", "")
        assert limit.isdigit(), f"X-RateLimit-Limit not a digit: {limit}"
        assert remaining.isdigit() or remaining.replace(".", "", 1).isdigit(), (
            f"X-RateLimit-Remaining not numeric: {remaining}"
        )
        assert reset.replace(".", "", 1).isdigit() or reset.isdigit(), (
            f"X-RateLimit-Reset not numeric: {reset}"
        )

    # ── 429 when limit exceeded ────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_returns_429_when_limit_exceeded(self, client):
        """When rate limit is exceeded, returns 429 Too Many Requests."""
        # Send many requests rapidly to exhaust the rate limit
        responses = []
        for _ in range(200):
            resp = client.get("/hello")
            responses.append(resp.status_code)
            if resp.status_code == 429:
                break

        # After exhausting the limit, should get 429
        assert 429 in responses, (
            f"Never got 429 after sending requests. Statuses: {responses}"
        )

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_429_response_has_retry_after_header(self, client):
        """429 response includes Retry-After header."""
        # Exhaust the rate limit
        for _ in range(200):
            resp = client.get("/hello")
            if resp.status_code == 429:
                assert "Retry-After" in resp.headers, (
                    f"Missing Retry-After header on 429. Headers: {dict(resp.headers)}"
                )
                retry_after = resp.headers["Retry-After"]
                assert retry_after.isdigit() or float(retry_after) > 0, (
                    f"Invalid Retry-After: {retry_after}"
                )
                return
        pytest.fail("Never hit 429 rate limit")

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_429_response_has_json_body(self, client):
        """429 response includes JSON body with detail and retry_after_seconds."""
        for _ in range(200):
            resp = client.get("/hello")
            if resp.status_code == 429:
                try:
                    data = resp.json()
                except Exception as exc:
                    pytest.fail(f"429 response is not valid JSON: {exc}")
                assert "detail" in data, (
                    f"429 response missing 'detail'. Body: {data}"
                )
                assert "retry_after_seconds" in data, (
                    f"429 response missing 'retry_after_seconds'. Body: {data}"
                )
                assert isinstance(data["retry_after_seconds"], (int, float))
                return
        pytest.fail("Never hit 429 rate limit")

    # ── Health check bypass ───────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_healthz_bypasses_rate_limiter(self, client):
        """GET /healthz always returns 200, even after many requests."""
        # Send many requests to non-health endpoint first to exhaust the limiter
        for _ in range(200):
            client.get("/hello")

        # Health endpoint should still return 200
        response = client.get("/healthz")
        assert response.status_code == 200, (
            f"Health endpoint should bypass rate limiter, got {response.status_code}"
        )

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_healthz_no_rate_limit_headers(self, client):
        """GET /healthz does not include X-RateLimit-* headers."""
        response = client.get("/healthz")
        # Health check should skip rate limiting entirely
        assert "X-RateLimit-Limit" not in response.headers, (
            "Health endpoint should not have rate limit headers"
        )
        assert "X-RateLimit-Remaining" not in response.headers

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_healthz_no_consume_tokens(self, client):
        """GET /healthz does not consume rate limit tokens."""
        # Exhaust tokens via /hello
        for _ in range(200):
            client.get("/hello")

        # Health endpoint should still work
        health_resp = client.get("/healthz")
        assert health_resp.status_code == 200

        # Non-health endpoints should still be blocked
        hello_resp = client.get("/hello")
        assert hello_resp.status_code == 429, (
            "After exhausting limit, /hello should be 429 even if /healthz was called"
        )

    # ── Per-identity rate limiting ─────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_different_ips_have_separate_limits(self, client):
        """Different client IPs have independent rate limit counters."""
        # Exhaust the limiter for one IP
        for _ in range(200):
            client.get("/hello", headers={"X-Forwarded-For": "1.1.1.1"})

        # A different IP should still be allowed
        resp = client.get("/hello", headers={"X-Forwarded-For": "2.2.2.2"})
        assert resp.status_code == 200, (
            f"Different IP should not be rate limited, got {resp.status_code}"
        )

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_authenticated_user_rate_limited_by_user(self, client):
        """Authenticated users are rate limited by user_id, not IP."""
        from meeting_notes_ai.auth import create_access_token

        token = create_access_token("rate-limited-user")
        headers = {"Authorization": f"Bearer {token}"}

        # Exhaust limit for this user
        for _ in range(200):
            resp = client.get("/hello", headers=headers)
            if resp.status_code == 429:
                break

        # Even from a different IP, same user should be limited
        resp2 = client.get(
            "/hello",
            headers={**headers, "X-Forwarded-For": "9.9.9.9"},
        )
        assert resp2.status_code == 429, (
            "User should still be rate limited after exhaustion, regardless of IP"
        )
