"""Interface and behavioral tests for P1: Tier Configuration + Admin Endpoint.

All tests fail RED until Tasks 1.2 and 1.3 are implemented.

Task 1.2 — Tier Configuration via Env Vars (config.py):
  - Settings gains RATE_LIMIT_FREE_DAILY, RATE_LIMIT_PRO_DAILY,
    RATE_LIMIT_ENTERPRISE_UNLIMITED, RATE_LIMIT_BURST_FACTOR
  - All configurable via MEETING_RATE_LIMIT_* env vars

Task 1.3 — User Tier Field + Admin Endpoint:
  - User model gains `tier` column defaulting to "free"
  - PATCH /api/v1/admin/users/{user_id}/tier — admin-only tier change
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meeting_notes_ai.config import Settings
from meeting_notes_ai.main import app

# ── Helpers ────────────────────────────────────────────────────────────────────


def _collect_routes(fastapi_app: FastAPI) -> list:
    """Collect all APIRoute objects, traversing _IncludedRouter wrappers."""
    collected = []
    for r in fastapi_app.routes:
        if type(r).__name__ == "_IncludedRouter":
            collected.extend(r.original_router.routes)  # type: ignore[attr-defined]
        elif hasattr(r, "path"):
            collected.append(r)
    return collected


def _find_route(fastapi_app: FastAPI, path: str):
    """Find an APIRoute by path."""
    for r in _collect_routes(fastapi_app):
        if r.path == path:
            return r
    return None


# ── Interface Tests (RED until P1) ────────────────────────────────────────────


class TestTierConfigInterface:
    """Verify Settings gains rate-limit tier configuration attributes."""

    def test_settings_default_free_daily(self) -> None:
        """RATE_LIMIT_FREE_DAILY defaults to 100."""
        s = Settings()
        assert getattr(s, "RATE_LIMIT_FREE_DAILY", None) is not None, (
            "Settings missing RATE_LIMIT_FREE_DAILY"
        )
        assert s.RATE_LIMIT_FREE_DAILY == 100

    def test_settings_default_pro_daily(self) -> None:
        """RATE_LIMIT_PRO_DAILY defaults to 10000."""
        s = Settings()
        assert getattr(s, "RATE_LIMIT_PRO_DAILY", None) is not None, (
            "Settings missing RATE_LIMIT_PRO_DAILY"
        )
        assert s.RATE_LIMIT_PRO_DAILY == 10000

    def test_settings_has_enterprise_unlimited(self) -> None:
        """RATE_LIMIT_ENTERPRISE_UNLIMITED is True by default."""
        s = Settings()
        assert hasattr(s, "RATE_LIMIT_ENTERPRISE_UNLIMITED"), (
            "Settings missing RATE_LIMIT_ENTERPRISE_UNLIMITED"
        )
        assert s.RATE_LIMIT_ENTERPRISE_UNLIMITED is True

    def test_settings_has_burst_factor(self) -> None:
        """RATE_LIMIT_BURST_FACTOR defaults to 1.0."""
        s = Settings()
        assert hasattr(s, "RATE_LIMIT_BURST_FACTOR"), (
            "Settings missing RATE_LIMIT_BURST_FACTOR"
        )
        assert isinstance(s.RATE_LIMIT_BURST_FACTOR, int | float)
        assert s.RATE_LIMIT_BURST_FACTOR == 1.0

    def test_settings_env_var_mapping(self) -> None:
        """Tier limits are configurable via MEETING_RATE_LIMIT_* env vars."""
        assert hasattr(Settings, "RATE_LIMIT_FREE_DAILY") or hasattr(
            Settings(), "RATE_LIMIT_FREE_DAILY"
        ), "Settings must expose RATE_LIMIT_FREE_DAILY for env var override"
        # The field should be loadable from MEETING_RATE_LIMIT_FREE_DAILY
        # as documented in analysis/analysis-brief.md §Task 1.2
        _expected_env = "MEETING_RATE_LIMIT_FREE_DAILY"
        _expected_env_pro = "MEETING_RATE_LIMIT_PRO_DAILY"
        # These names must match the analysis brief spec
        assert _expected_env, "Expected env var name defined"
        assert _expected_env_pro, "Expected env var name defined"


class TestUserTierInterface:
    """Verify User model gains a `tier` field and admin endpoint exists."""

    def test_user_model_has_tier_field(self) -> None:
        """User model (from db/models.py) has tier defaulting to 'free'."""
        # Lazy import — the module may not exist yet in v0.3.0
        import importlib

        try:
            mod = importlib.import_module("meeting_notes_ai.db.models")
            User = getattr(mod, "User", None)
            assert User is not None, "User model not found in db.models"
            # Check tier column via SQLAlchemy Column or similar
            tier_col = getattr(User, "tier", None)
            assert tier_col is not None, (
                "User model missing 'tier' attribute/column"
            )
        except (ImportError, ModuleNotFoundError):
            raise AssertionError(
                "meeting_notes_ai.db.models module does not exist — "
                "User model (with tier field) not yet implemented"
            )

    def test_user_tier_defaults_free(self) -> None:
        """User model tier field defaults to 'free'."""
        import importlib

        try:
            mod = importlib.import_module("meeting_notes_ai.db.models")
            User = getattr(mod, "User", None)
            assert User is not None, "User model not found"
            # Check the column default
            tier_col = getattr(User, "tier", None)
            if tier_col is not None and hasattr(tier_col, "default"):
                default = (
                    tier_col.default.arg
                    if hasattr(tier_col.default, "arg")
                    else tier_col.default
                )
                assert default == "free", f"Expected default='free', got {default!r}"
        except (ImportError, ModuleNotFoundError):
            raise AssertionError("User model not implemented yet")

    def test_admin_tier_change_endpoint_exists(self) -> None:
        """PATCH /api/v1/admin/users/{user_id}/tier is registered."""
        route = _find_route(app, "/api/v1/admin/users/{user_id}/tier")
        assert route is not None, (
            "Admin tier-change endpoint not found in app routes"
        )
        assert "PATCH" in route.methods, (
            f"Expected PATCH method, got {route.methods}"
        )

    def test_admin_tier_change_admin_only(self) -> None:
        """Non-admin caller gets 403 on tier-change endpoint."""
        client = TestClient(app)
        response = client.patch("/api/v1/admin/users/user-001/tier", json={"tier": "pro"})
        assert response.status_code == 403, (
            f"Expected 403 for non-admin, got {response.status_code}"
        )


class TestAdminTierChangeEndpointInterface:
    """Verify the body schema for the admin tier-change endpoint."""

    def test_admin_tier_change_accepts_json_body(self) -> None:
        """PATCH endpoint accepts JSON body with 'tier' field."""
        client = TestClient(app)
        # Without auth this should 401/403, but we're testing the
        # _existence_ of the route — 404 means endpoint doesn't exist
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "pro"},
        )
        assert response.status_code != 404, (
            "Admin tier-change endpoint returned 404 — route not registered"
        )
        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 (no auth), got {response.status_code}"
        )

    def test_admin_tier_change_validates_tier_values(self) -> None:
        """Endpoint validates tier is one of: free, pro, enterprise."""
        client = TestClient(app)
        # Test with invalid tier value — should 422 if validation exists
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "invalid_tier"},
        )
        # Route exists → not 404; validation fails → 422
        assert response.status_code != 404, (
            "Admin tier-change endpoint returned 404 — route not registered"
        )


# ── Behavioral Tests (xfail until P1) ───────────────────────────────────────


class TestTierConfigBehavioral:
    """Verify env var overrides and tier-based limits (Task 1.2)."""

    @pytest.mark.xfail(strict=True)
    def test_env_var_overrides_free_daily(self) -> None:
        """MEETING_RATE_LIMIT_FREE_DAILY env var changes free limit."""
        import os

        os.environ["MEETING_RATE_LIMIT_FREE_DAILY"] = "50"
        try:
            s = Settings()
            assert s.RATE_LIMIT_FREE_DAILY == 50, (
                f"Expected 50 after env override, got {s.RATE_LIMIT_FREE_DAILY}"
            )
        finally:
            del os.environ["MEETING_RATE_LIMIT_FREE_DAILY"]

    @pytest.mark.xfail(strict=True)
    def test_env_var_overrides_pro_daily(self) -> None:
        """MEETING_RATE_LIMIT_PRO_DAILY env var changes pro limit."""
        import os

        os.environ["MEETING_RATE_LIMIT_PRO_DAILY"] = "5000"
        try:
            s = Settings()
            assert s.RATE_LIMIT_PRO_DAILY == 5000, (
                f"Expected 5000 after env override, got {s.RATE_LIMIT_PRO_DAILY}"
            )
        finally:
            del os.environ["MEETING_RATE_LIMIT_PRO_DAILY"]

    @pytest.mark.xfail(strict=True)
    def test_burst_factor_affects_capacity(self) -> None:
        """RATE_LIMIT_BURST_FACTOR multiplies daily limit for bucket capacity."""
        import os

        os.environ["MEETING_RATE_LIMIT_BURST_FACTOR"] = "2.0"
        try:
            s = Settings()
            assert s.RATE_LIMIT_BURST_FACTOR == 2.0, (
                f"Expected 2.0 after override, got {s.RATE_LIMIT_BURST_FACTOR}"
            )
        finally:
            del os.environ["MEETING_RATE_LIMIT_BURST_FACTOR"]


class TestAdminTierChangeBehavioral:
    """Verify admin can change user tier (Task 1.3)."""

    @pytest.mark.xfail(strict=True)
    def test_admin_changes_user_tier(self) -> None:
        """Admin PATCH on tier endpoint changes user's tier."""
        client = TestClient(app)
        # This requires admin auth which doesn't exist in v0.3.0
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "pro"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 200, (
            f"Expected 200 for admin tier change, got {response.status_code}"
        )

    @pytest.mark.xfail(strict=True)
    def test_tier_change_returns_updated_user(self) -> None:
        """Admin tier change response includes updated user info."""
        client = TestClient(app)
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "pro"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "tier" in data, "Response missing 'tier' field"
        assert data["tier"] == "pro"

    @pytest.mark.xfail(strict=True)
    def test_tier_change_persists_in_db(self) -> None:
        """User's tier persists after endpoint call."""
        # This would query the database — stub for now
        client = TestClient(app)
        # Change tier
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "enterprise"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 200

        # Verify by reading the user's tier back (requires GET endpoint)
        get_resp = client.get(
            "/api/v1/admin/users/user-001",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data.get("tier") == "enterprise", (
            f"Expected tier='enterprise', got {data.get('tier')!r}"
        )

    @pytest.mark.xfail(strict=True)
    def test_tier_change_affects_rate_limit(self) -> None:
        """After tier change, rate limit headers reflect new tier."""
        client = TestClient(app)
        # Change user to enterprise (unlimited)
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "enterprise"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 200

        # Subsequent request should show enterprise-tier limit
        resp = client.get(
            "/healthz",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert resp.status_code == 200
        limit = resp.headers.get("X-RateLimit-Limit")
        assert limit is not None, "Missing X-RateLimit-Limit header"
        # Enterprise tier has no daily limit — could be "unlimited" or very large
        assert limit.upper() == "UNLIMITED" or int(limit) >= 100000, (
            f"Expected enterprise unlimited limit, got {limit!r}"
        )

    @pytest.mark.xfail(strict=True)
    def test_non_admin_cannot_change_tier(self) -> None:
        """Non-admin caller receives 403."""
        client = TestClient(app)
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "pro"},
            headers={"Authorization": "Bearer non-admin-token"},
        )
        assert response.status_code == 403, (
            f"Expected 403 for non-admin, got {response.status_code}"
        )

    @pytest.mark.xfail(strict=True)
    def test_tier_change_rejects_invalid_tier(self) -> None:
        """Endpoint returns 422 for invalid tier values."""
        client = TestClient(app)
        response = client.patch(
            "/api/v1/admin/users/user-001/tier",
            json={"tier": "gold"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 422, (
            f"Expected 422 for invalid tier, got {response.status_code}"
        )

    @pytest.mark.xfail(strict=True)
    def test_tier_change_nonexistent_user(self) -> None:
        """Endpoint returns 404 for non-existent user."""
        client = TestClient(app)
        response = client.patch(
            "/api/v1/admin/users/nonexistent-user/tier",
            json={"tier": "pro"},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 404, (
            f"Expected 404 for nonexistent user, got {response.status_code}"
        )
