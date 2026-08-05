"""Interface and behavioral tests for v0.2.0 authentication module.

Tests JWT auth signup/login endpoints, token handling, and authorization dependencies.
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as integration (uses TestClient/AsyncClient)
pytestmark = pytest.mark.integration


# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestAuthInterface:
    """Verify auth module exists with correct contracts."""

    def test_auth_module_importable(self):
        from meeting_notes_ai import auth

        assert auth is not None

    def test_auth_router_is_apirouter(self):
        from fastapi import APIRouter

        from meeting_notes_ai.auth import router

        assert isinstance(router, APIRouter)

    def test_auth_router_prefix(self):
        from meeting_notes_ai.auth import router

        assert router.prefix == "/api/v1/auth"

    def test_auth_router_has_tags(self):
        from meeting_notes_ai.auth import router

        assert router.tags is not None
        assert "auth" in router.tags

    # ── Request/Response Schemas ──────────────────────────────────────────────

    def test_signup_request_importable(self):
        from meeting_notes_ai.auth import SignupRequest

        assert SignupRequest is not None

    def test_signup_request_has_fields(self):
        from pydantic import EmailStr

        from meeting_notes_ai.auth import SignupRequest

        fields = SignupRequest.model_fields
        assert "email" in fields
        assert fields["email"].annotation is EmailStr
        assert "password" in fields
        assert "display_name" in fields

    def test_login_request_importable(self):
        from meeting_notes_ai.auth import LoginRequest

        assert LoginRequest is not None

    def test_login_request_has_fields(self):
        from pydantic import EmailStr

        from meeting_notes_ai.auth import LoginRequest

        fields = LoginRequest.model_fields
        assert "email" in fields
        assert fields["email"].annotation is EmailStr
        assert "password" in fields

    def test_token_response_importable(self):
        from meeting_notes_ai.auth import TokenResponse

        assert TokenResponse is not None

    def test_token_response_has_access_token(self):
        from meeting_notes_ai.auth import TokenResponse

        fields = TokenResponse.model_fields
        assert "access_token" in fields
        assert "token_type" in fields
        assert "expires_at" in fields

    def test_token_type_default_bearer(self):
        from meeting_notes_ai.auth import TokenResponse

        field = TokenResponse.model_fields["token_type"]
        assert field.default == "bearer"

    def test_user_response_importable(self):
        from meeting_notes_ai.auth import UserResponse

        assert UserResponse is not None

    def test_user_response_has_fields(self):
        from meeting_notes_ai.auth import UserResponse

        fields = UserResponse.model_fields
        assert "id" in fields
        assert "email" in fields
        assert "display_name" in fields

    # ── Service function signatures ──────────────────────────────────────────

    def test_hash_password_signature(self):
        from meeting_notes_ai.auth import hash_password

        assert callable(hash_password)
        assert hash_password.__name__ == "hash_password"
        sig = signature(hash_password)
        assert "password" in sig.parameters

    def test_hash_password_is_async(self):
        import inspect

        from meeting_notes_ai.auth import hash_password

        assert inspect.iscoroutinefunction(hash_password)

    def test_verify_password_signature(self):
        from meeting_notes_ai.auth import verify_password

        sig = signature(verify_password)
        assert "plain" in sig.parameters
        assert "hashed" in sig.parameters

    def test_verify_password_is_async(self):
        import inspect

        from meeting_notes_ai.auth import verify_password

        assert inspect.iscoroutinefunction(verify_password)

    def test_create_access_token_signature(self):
        from meeting_notes_ai.auth import create_access_token

        sig = signature(create_access_token)
        assert "user_id" in sig.parameters
        assert "expires_delta_hours" in sig.parameters

    def test_create_access_token_is_async(self):
        import inspect

        from meeting_notes_ai.auth import create_access_token

        assert inspect.iscoroutinefunction(create_access_token)

    def test_decode_access_token_signature(self):
        from meeting_notes_ai.auth import decode_access_token

        sig = signature(decode_access_token)
        assert "token" in sig.parameters

    def test_decode_access_token_is_async(self):
        import inspect

        from meeting_notes_ai.auth import decode_access_token

        assert inspect.iscoroutinefunction(decode_access_token)

    def test_require_team_role_signature(self):
        from meeting_notes_ai.auth import require_team_role

        sig = signature(require_team_role)
        assert "team_id" in sig.parameters
        assert "required_role" in sig.parameters

    def test_require_team_role_is_async(self):
        import inspect

        from meeting_notes_ai.auth import require_team_role

        assert inspect.iscoroutinefunction(require_team_role)

    # ── Route registration ────────────────────────────────────────────────────

    def test_signup_route_registered(self):
        from meeting_notes_ai.auth import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        signup_routes = [r for r in routes if "signup" in r.path]
        assert len(signup_routes) >= 1

    def test_login_route_registered(self):
        from meeting_notes_ai.auth import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        login_routes = [r for r in routes if "login" in r.path]
        assert len(login_routes) >= 1

    def test_me_route_registered(self):
        from meeting_notes_ai.auth import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        me_routes = [r for r in routes if r.path.endswith("/me")]
        assert len(me_routes) >= 1

    def test_signup_is_post(self):
        from meeting_notes_ai.auth import router

        for r in router.routes:
            if hasattr(r, "path") and "signup" in r.path:
                assert "POST" in r.methods
                return
        pytest.fail("Signup route not found")

    def test_login_is_post(self):
        from meeting_notes_ai.auth import router

        for r in router.routes:
            if hasattr(r, "path") and "login" in r.path:
                assert "POST" in r.methods
                return
        pytest.fail("Login route not found")

    def test_get_me_is_get(self):
        from meeting_notes_ai.auth import router

        for r in router.routes:
            if hasattr(r, "path") and r.path.endswith("/me"):
                assert "GET" in r.methods
                return
        pytest.fail("Get me route not found")


# ── Behavioral Tests (real JWT/password behavior) ────────────────────────────


@pytest.mark.asyncio
async def test_hash_password_returns_bcrypt_hash():
    """hash_password returns a bcrypt hash string."""
    from meeting_notes_ai.auth import hash_password

    hashed = await hash_password("secret123")
    assert isinstance(hashed, str)
    assert hashed.startswith("$2b$")


@pytest.mark.asyncio
async def test_verify_password_correct():
    """verify_password returns True for matching passwords."""
    from meeting_notes_ai.auth import hash_password, verify_password

    hashed = await hash_password("secret123")
    result = await verify_password("secret123", hashed)
    assert result is True


@pytest.mark.asyncio
async def test_verify_password_incorrect():
    """verify_password returns False for wrong password."""
    from meeting_notes_ai.auth import hash_password, verify_password

    hashed = await hash_password("secret123")
    result = await verify_password("wrongpass", hashed)
    assert result is False


@pytest.mark.asyncio
async def test_create_access_token_returns_jwt():
    """create_access_token returns a JWT token string."""
    from meeting_notes_ai.auth import create_access_token

    token = await create_access_token("user-123")
    assert isinstance(token, str)
    # JWT has three parts separated by dots
    assert len(token.split(".")) == 3


@pytest.mark.asyncio
async def test_decode_access_token_valid():
    """decode_access_token returns payload for a valid token."""
    from meeting_notes_ai.auth import create_access_token, decode_access_token

    token = await create_access_token("user-123")
    payload = await decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert "exp" in payload
    assert "iat" in payload


@pytest.mark.asyncio
async def test_decode_access_token_invalid():
    """decode_access_token raises HTTPException for invalid token."""

    from meeting_notes_ai.auth import decode_access_token

    with pytest.raises(Exception):  # HTTPException(401) or JWTError
        await decode_access_token("invalid-token-here")


@pytest.mark.asyncio
async def test_hash_and_verify_round_trip():
    """Hash then verify in sequence works correctly."""
    from meeting_notes_ai.auth import hash_password, verify_password

    passwords = ["short", "longer_password_123!", "with spaces and $ymbols"]
    for pw in passwords:
        hashed = await hash_password(pw)
        assert await verify_password(pw, hashed)
