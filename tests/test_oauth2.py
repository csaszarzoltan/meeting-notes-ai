"""Tests for OAuth2 PKCE services and token refresh worker.

Exercises:
  - start_authorization (PKCE challenge generation, state storage)
  - handle_callback (code exchange, state verification)
  - refresh_token (token renewal, inactive marking)
  - PKCE helper functions (_generate_pkce_pair)

Uses respx for HTTP mocking and the shared in-memory test DB.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from meeting_notes_ai.db.models import OAuthState, PMIntegrationToken
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.oauth2 import (
    _generate_pkce_pair,
    handle_callback,
    refresh_token,
    start_authorization,
)

pytestmark = pytest.mark.quick

USER_ID = "test-user-001"
PROVIDER = "jira"
REDIRECT_URI = "https://app.example.com/callback"
_TEST_ENCRYPTION_KEY = "oauth2-test-encryption-key-32b!"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _oauth_env(monkeypatch: pytest.MonkeyPatch, _setup_test_db):
    """Set required env vars for OAuth2 provider configs.

    Also patch settings.storage_encryption_key so TokenEncryptor works.
    The settings singleton is created at module import time, so monkeypatch
    env vars are too late — we must patch the attribute directly.
    """
    monkeypatch.setenv("JIRA_CLIENT_ID", "test-client-id-123")
    monkeypatch.setenv("JIRA_CLIENT_ID_SECRET", "test-client-secret-456")
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)
    # Patch the settings singleton's attribute (created at import time)
    from meeting_notes_ai.config import settings

    monkeypatch.setattr(settings, "storage_encryption_key", _TEST_ENCRYPTION_KEY)


# ── T0-4.1: start_authorization URL contains PKCE challenge + state ───────────


async def test_start_authorization_generates_url_with_pkce_challenge():
    """Authorization URL must include code_challenge, code_challenge_method=S256, and state."""
    url, state_token = await start_authorization(
        provider=PROVIDER,
        redirect_uri=REDIRECT_URI,
        user_id=USER_ID,
        db=await _fresh_session(),
    )

    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert f"state={state_token}" in url
    assert "response_type=code" in url
    assert "client_id=test-client-id-123" in url
    assert url.startswith("https://auth.atlassian.com/authorize?")


# ── T0-4.2: start_authorization stores state in DB ────────────────────────────


async def test_start_authorization_stores_state_in_db():
    """OAuthState row must be created with correct user_id, provider, code_verifier."""
    db = await _fresh_session()

    url, state_token = await start_authorization(
        provider=PROVIDER,
        redirect_uri=REDIRECT_URI,
        user_id=USER_ID,
        db=db,
    )

    result = await db.execute(
        select(OAuthState).where(OAuthState.state_token == state_token)
    )
    record = result.scalar_one_or_none()

    assert record is not None
    assert record.user_id == USER_ID
    assert record.provider == PROVIDER
    assert record.code_verifier is not None
    assert len(record.code_verifier) >= 43
    assert record.used is False
    # SQLite returns naive UTC datetimes — strip tzinfo for comparison
    expires_at = record.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    assert expires_at > datetime.now(timezone.utc).replace(tzinfo=None)


# ── T0-4.3: handle_callback exchanges code for token ──────────────────────────


@respx.mock
async def test_handle_callback_exchanges_code_for_token():
    """Mock token endpoint; verify PMIntegrationToken upsert with encrypted credentials."""
    db = await _fresh_session()

    # First, create a valid state
    _, state_token = await start_authorization(
        provider=PROVIDER,
        redirect_uri=REDIRECT_URI,
        user_id=USER_ID,
        db=db,
    )
    await db.commit()

    # Mock the token endpoint (Atlassian)
    respx.post("https://auth.atlassian.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new-access-token-abc",
                "refresh_token": "new-refresh-token-xyz",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )

    auth = await handle_callback(
        provider=PROVIDER,
        code="auth-code-from-provider",
        state_token=state_token,
        user_id=USER_ID,
        db=db,
    )

    assert auth.token == "new-access-token-abc"
    assert auth.provider == PROVIDER

    # Verify PMIntegrationToken was upserted
    await db.commit()
    result = await db.execute(
        select(PMIntegrationToken).where(
            PMIntegrationToken.user_id == USER_ID,
            PMIntegrationToken.provider == PROVIDER,
        )
    )
    token_row = result.scalar_one_or_none()
    assert token_row is not None
    assert token_row.is_active is True
    assert token_row.token_expires_at is not None
    # SQLite returns naive UTC datetimes
    expires_at = token_row.token_expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    assert expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
    assert token_row.encrypted_credentials  # non-empty encrypted blob


# ── T0-4.4: handle_callback rejects invalid state ─────────────────────────────


async def test_handle_callback_rejects_invalid_state():
    """Missing/unknown state token must raise ValueError."""
    db = await _fresh_session()

    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        await handle_callback(
            provider=PROVIDER,
            code="some-code",
            state_token="nonexistent-state-token",
            user_id=USER_ID,
            db=db,
        )


# ── T0-4.5: handle_callback rejects expired state ────────────────────────────


async def test_handle_callback_rejects_expired_state():
    """State older than 10 minutes must be rejected."""
    db = await _fresh_session()

    # Insert an expired state directly — use naive UTC to match SQLite storage
    expired_state = OAuthState(
        state_token="expired-state-token-123",
        user_id=USER_ID,
        provider=PROVIDER,
        code_verifier="expired-verifier-that-is-long-enough-for-validation-43chars",
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=15)).replace(
            tzinfo=None
        ),
        used=False,
    )
    db.add(expired_state)
    await db.commit()

    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        await handle_callback(
            provider=PROVIDER,
            code="some-code",
            state_token="expired-state-token-123",
            user_id=USER_ID,
            db=db,
        )


# ── T0-4.6: refresh_token updates expires_at ──────────────────────────────────


@respx.mock
async def test_refresh_token_updates_expires_at():
    """Mock refresh endpoint returning new tokens; verify token_expires_at updated."""
    db = await _fresh_session()

    from meeting_notes_ai.services.token_encryption import TokenEncryptor

    encryptor = TokenEncryptor(key=_TEST_ENCRYPTION_KEY)
    creds = json.dumps({
        "token": "old-access-token",
        "refresh_token": "valid-refresh-token-abc",
        "email": "user@example.com",
    })
    encrypted = encryptor.encrypt(creds)

    token_row = PMIntegrationToken(
        user_id=USER_ID,
        provider=PROVIDER,
        encrypted_credentials=encrypted,
        account_email="user@example.com",
        account_url="https://acme.atlassian.net",
        token_expires_at=(datetime.now(timezone.utc) + timedelta(minutes=2)).replace(
            tzinfo=None
        ),
        is_active=True,
    )
    db.add(token_row)
    await db.commit()

    # Mock refresh endpoint
    respx.post("https://auth.atlassian.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "refreshed-access-token",
                "refresh_token": "refreshed-refresh-token",
                "expires_in": 7200,
                "token_type": "Bearer",
            },
        )
    )

    result = await refresh_token(
        provider=PROVIDER,
        user_id=USER_ID,
        db=db,
    )

    assert result is True

    # Verify the token row was updated
    await db.commit()
    refreshed_row = (
        await db.execute(
            select(PMIntegrationToken).where(
                PMIntegrationToken.user_id == USER_ID,
                PMIntegrationToken.provider == PROVIDER,
            )
        )
    ).scalar_one()

    assert refreshed_row.is_active is True
    assert refreshed_row.disconnected_at is None
    assert refreshed_row.token_expires_at is not None
    # Should be updated to ~2h from now
    expires_at = refreshed_row.token_expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    assert expires_at > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        hours=1
    )

    # Verify credentials were updated
    decrypted = json.loads(encryptor.decrypt(refreshed_row.encrypted_credentials))
    assert decrypted["token"] == "refreshed-access-token"
    assert decrypted["refresh_token"] == "refreshed-refresh-token"


# ── T0-4.7: refresh_token returns False on invalid grant ──────────────────────


@respx.mock
async def test_refresh_token_returns_false_on_invalid_grant():
    """Mock 401 from token endpoint; verify token marked inactive."""
    db = await _fresh_session()

    from meeting_notes_ai.services.token_encryption import TokenEncryptor

    encryptor = TokenEncryptor(key=_TEST_ENCRYPTION_KEY)
    creds = json.dumps({
        "token": "old-access-token",
        "refresh_token": "bad-refresh-token",
        "email": "user@example.com",
    })
    encrypted = encryptor.encrypt(creds)

    token_row = PMIntegrationToken(
        user_id=USER_ID,
        provider=PROVIDER,
        encrypted_credentials=encrypted,
        account_email="user@example.com",
        account_url="",
        token_expires_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).replace(
            tzinfo=None
        ),
        is_active=True,
    )
    db.add(token_row)
    await db.commit()

    # Mock refresh endpoint returning 401
    respx.post("https://auth.atlassian.com/oauth/token").mock(
        return_value=httpx.Response(
            401,
            json={"error": "invalid_grant", "error_description": "Token expired or revoked"},
        )
    )

    result = await refresh_token(
        provider=PROVIDER,
        user_id=USER_ID,
        db=db,
    )

    assert result is False

    # Verify token marked inactive
    await db.commit()
    row = (
        await db.execute(
            select(PMIntegrationToken).where(
                PMIntegrationToken.user_id == USER_ID,
                PMIntegrationToken.provider == PROVIDER,
            )
        )
    ).scalar_one()

    assert row.is_active is False
    assert row.disconnected_at is not None


# ── T0-4.8: PKCE code_verifier is valid ───────────────────────────────────────


def test_pkce_code_verifier_is_valid():
    """code_verifier must be 43-128 chars, base64url-safe."""
    for _ in range(50):
        verifier, _ = _generate_pkce_pair()
        assert 43 <= len(verifier) <= 128, f"verifier length {len(verifier)} out of range"
        # Must be base64url-safe (no +, /, or = characters)
        assert re.match(r"^[A-Za-z0-9_-]+$", verifier), (
            f"verifier contains non-base64url chars: {verifier!r}"
        )


# ── T0-4.9: PKCE code_challenge matches verifier ─────────────────────────────


def test_pkce_code_challenge_matches_verifier():
    """code_challenge must equal BASE64URL(SHA256(code_verifier))."""
    for _ in range(50):
        verifier, challenge = _generate_pkce_pair()
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge, (
            f"challenge mismatch: got {challenge!r}, expected {expected_challenge!r}"
        )
        # Challenge must also be base64url-safe
        assert re.match(r"^[A-Za-z0-9_-]+$", challenge)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _fresh_session():
    """Get a raw AsyncSession from the global factory."""
    factory = get_db_session.__globals__["_session_factory"]
    return factory()
