"""OAuth2 Authorization Code + PKCE core module for PM tool integrations.

Provides token exchange, PKCE challenge generation, state management,
and credential persistence for Jira, Linear, Asana, and Todoist.

All provider configs, PKCE crypto, and token lifecycle live here.
Routes in ``routes/oauth2.py`` call into this module.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import (
    OAuthState,
    PMIntegrationToken,
)
from meeting_notes_ai.services.integrations.base import AdapterAuth
from meeting_notes_ai.services.token_encryption import TokenEncryptor

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

_OAUTH_STATE_TTL_MINUTES = 10
_PKCE_VERIFIER_MIN_LEN = 43
_PKCE_VERIFIER_MAX_LEN = 128
_TOKEN_EXCHANGE_TIMEOUT = 15.0  # seconds


# ── Provider configuration ──────────────────────────────────────────────────


@dataclass(frozen=True)
class OAuth2ProviderConfig:
    """Static configuration for an OAuth2 provider."""

    authorize_url: str
    token_url: str
    scopes: list[str]
    supports_pkce: bool
    client_id_env: str  # env var name for client_id
    userinfo_url: str = ""  # optional: fetch account info after token exchange
    # Provider-specific token response field mappings
    access_token_key: str = "access_token"
    refresh_token_key: str = "refresh_token"
    expires_in_key: str = "expires_in"


OAUTH2_CONFIGS: dict[str, OAuth2ProviderConfig] = {
    "jira": OAuth2ProviderConfig(
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        scopes=["read:jira-work", "write:jira-work", "offline_access"],
        supports_pkce=True,
        client_id_env="JIRA_CLIENT_ID",
        userinfo_url="https://api.atlassian.com/oauth/userinfo",
    ),
    "linear": OAuth2ProviderConfig(
        authorize_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        scopes=["read", "write"],
        supports_pkce=True,
        client_id_env="LINEAR_CLIENT_ID",
    ),
    "asana": OAuth2ProviderConfig(
        authorize_url="https://app.asana.com/-/oauth_authorize",
        token_url="https://app.asana.com/-/oauth_token",
        scopes=["default", "projects:read", "tasks:read", "tasks:write"],
        supports_pkce=True,
        client_id_env="ASANA_CLIENT_ID",
    ),
    "todoist": OAuth2ProviderConfig(
        authorize_url="https://app.todoist.com/oauth/authorize",
        token_url="https://api.todoist.com/v1/oauth/token",
        scopes=["data:read", "data:read_write"],
        supports_pkce=True,
        client_id_env="TODOIST_CLIENT_ID",
    ),
}


# ── PKCE helpers ────────────────────────────────────────────────────────────


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 PKCE code_verifier and code_challenge.

    Returns:
        (code_verifier, code_challenge) where code_challenge is
        BASE64URL(SHA256(code_verifier)) as per S256 method.
    """
    code_verifier = secrets.token_urlsafe(64)[:_PKCE_VERIFIER_MAX_LEN]
    # Ensure minimum length
    while len(code_verifier) < _PKCE_VERIFIER_MIN_LEN:
        code_verifier = secrets.token_urlsafe(64)[:_PKCE_VERIFIER_MAX_LEN]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _generate_state_token() -> str:
    """Generate a cryptographically random CSRF state token."""
    return secrets.token_urlsafe(32)


# ── State storage ───────────────────────────────────────────────────────────


async def _store_oauth_state(
    state_token: str,
    user_id: str,
    provider: str,
    code_verifier: str,
    db: AsyncSession,
) -> None:
    """Store an OAuth state token with PKCE verifier and a 10-minute TTL."""
    record = OAuthState(
        state_token=state_token,
        user_id=user_id,
        provider=provider,
        code_verifier=code_verifier,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=_OAUTH_STATE_TTL_MINUTES),
    )
    db.add(record)
    await db.flush()


async def _verify_oauth_state(
    state_token: str,
    db: AsyncSession,
) -> tuple[str, str, str] | None:
    """Verify and consume an OAuth state token.

    Returns:
        (user_id, provider, code_verifier) if valid, None otherwise.

    Expired and already-used state rows are purged on read.
    """
    result = await db.execute(
        select(OAuthState).where(
            OAuthState.state_token == state_token,
            OAuthState.used.is_(False),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        await _purge_oauth_states(db)
        await db.flush()
        return None

    # SQLite round-trips DateTime(timezone=True) as naive UTC
    expires_at = record.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        await _purge_oauth_states(db)
        await db.flush()
        return None

    record.used = True
    user_id = record.user_id
    provider = record.provider or ""
    code_verifier = record.code_verifier or ""

    await _purge_oauth_states(db)
    await db.flush()
    return user_id, provider, code_verifier


async def _purge_oauth_states(db: AsyncSession) -> None:
    """Delete expired and already-consumed OAuth state rows."""
    from sqlalchemy import delete, or_

    await db.execute(
        delete(OAuthState).where(
            or_(
                OAuthState.used.is_(True),
                OAuthState.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    )


# ── Public API ──────────────────────────────────────────────────────────────


async def start_authorization(
    provider: str,
    redirect_uri: str,
    user_id: str,
    db: AsyncSession,
) -> tuple[str, str]:
    """Begin an OAuth2 authorization flow with PKCE.

    Args:
        provider: One of "jira", "linear", "asana", "todoist".
        redirect_uri: The OAuth2 callback URL registered with the provider.
        user_id: The authenticated user's ID (stored with the state).
        db: Async database session.

    Returns:
        (authorization_url, state_token) — redirect the user to authorization_url.

    Raises:
        ValueError: Unknown provider or missing client_id env var.
    """
    config = OAUTH2_CONFIGS.get(provider)
    if config is None:
        raise ValueError(f"Unknown OAuth2 provider: {provider}")

    client_id = os.getenv(config.client_id_env, "")
    if not client_id:
        raise ValueError(f"Missing environment variable: {config.client_id_env}")

    # Generate PKCE pair
    code_verifier, code_challenge = _generate_pkce_pair()

    # Generate CSRF state
    state_token = _generate_state_token()

    # Persist state + code_verifier in DB
    await _store_oauth_state(state_token, user_id, provider, code_verifier, db)

    # Build authorization URL
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state_token,
    }
    if config.supports_pkce:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    authorization_url = f"{config.authorize_url}?{query}"

    logger.info("OAuth2 start: provider=%s user=%s", provider, user_id[:8])
    return authorization_url, state_token


async def handle_callback(
    provider: str,
    code: str,
    state_token: str,
    user_id: str,
    db: AsyncSession,
) -> AdapterAuth:
    """Handle an OAuth2 callback: verify state, exchange code for tokens.

    Encrypts the tokens with TokenEncryptor and upserts PMIntegrationToken.

    Args:
        provider: One of "jira", "linear", "asana", "todoist".
        code: The authorization code from the callback query.
        state_token: The CSRF state token from the callback query.
        user_id: The authenticated user's ID.
        db: Async database session.

    Returns:
        AdapterAuth with decrypted credentials for the adapter.

    Raises:
        ValueError: Invalid state, unknown provider, or token exchange failure.
    """
    # Verify state and retrieve PKCE verifier
    verified = await _verify_oauth_state(state_token, db)
    if verified is None:
        raise ValueError("Invalid or expired OAuth state — please try again")

    state_user_id, state_provider, code_verifier = verified

    # Security: state must belong to this user and match the provider
    if state_user_id != user_id:
        raise ValueError("OAuth state does not belong to this user")
    if state_provider != provider:
        raise ValueError(
            f"OAuth state provider mismatch: expected {state_provider}, got {provider}"
        )

    config = OAUTH2_CONFIGS.get(provider)
    if config is None:
        raise ValueError(f"Unknown OAuth2 provider: {provider}")

    client_id = os.getenv(config.client_id_env, "")
    if not client_id:
        raise ValueError(f"Missing environment variable: {config.client_id_env}")

    client_secret = os.getenv(f"{config.client_id_env}_SECRET", "")

    # Exchange authorization code for tokens
    token_data = await _exchange_code(
        config=config,
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        code_verifier=code_verifier,
    )

    access_token = token_data.get(config.access_token_key, "")
    refresh_token = token_data.get(config.refresh_token_key, "")
    expires_in = token_data.get(config.expires_in_key, 0)

    if not access_token:
        raise ValueError(f"No access_token in {provider} token response")

    # Compute token expiry
    token_expires_at = None
    if expires_in:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Fetch user info if available
    email = ""
    account_url = ""
    if config.userinfo_url and access_token:
        email, account_url = await _fetch_userinfo(
            config.userinfo_url, access_token
        )

    # Build credentials blob
    credentials = {
        "token": access_token,
        "refresh_token": refresh_token,
        "email": email,
    }

    # Encrypt and upsert PMIntegrationToken
    encryptor = TokenEncryptor()
    encrypted = encryptor.encrypt(json.dumps(credentials))

    await _upsert_pm_token(
        db=db,
        user_id=user_id,
        provider=provider,
        encrypted_credentials=encrypted,
        account_email=email,
        account_url=account_url,
        token_expires_at=token_expires_at,
    )

    logger.info("OAuth2 callback: provider=%s user=%s email=%s", provider, user_id[:8], email)

    return AdapterAuth(
        provider=provider,
        token=access_token,
        email=email,
        account_url=account_url,
    )


async def refresh_token(
    provider: str,
    user_id: str,
    db: AsyncSession,
) -> bool:
    """Attempt to refresh an expired OAuth2 token.

    Args:
        provider: One of "jira", "linear", "asana", "todoist".
        user_id: The authenticated user's ID.
        db: Async database session.

    Returns:
        True if refresh succeeded (token row updated), False if re-auth needed.
    """
    config = OAUTH2_CONFIGS.get(provider)
    if config is None:
        return False

    # Load existing token
    result = await db.execute(
        select(PMIntegrationToken).where(
            PMIntegrationToken.user_id == user_id,
            PMIntegrationToken.provider == provider,
            PMIntegrationToken.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False

    # Decrypt to get refresh_token
    encryptor = TokenEncryptor()
    try:
        creds = json.loads(encryptor.decrypt(row.encrypted_credentials))
    except (ValueError, json.JSONDecodeError):
        logger.warning("OAuth2 refresh: failed to decrypt token for %s/%s", provider, user_id[:8])
        return False

    refresh_tok = creds.get("refresh_token", "")
    if not refresh_tok:
        # No refresh token available — need re-auth
        row.is_active = False
        row.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
        return False

    client_id = os.getenv(config.client_id_env, "")
    if not client_id:
        return False
    client_secret = os.getenv(f"{config.client_id_env}_SECRET", "")

    # Call provider's token endpoint with refresh_token grant
    try:
        token_data = await _refresh_token_request(
            config=config,
            refresh_token=refresh_tok,
            client_id=client_id,
            client_secret=client_secret,
        )
    except Exception:
        logger.exception("OAuth2 refresh: token request failed for %s/%s", provider, user_id[:8])
        row.is_active = False
        row.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
        return False

    new_access = token_data.get(config.access_token_key, "")
    if not new_access:
        row.is_active = False
        row.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
        return False

    # Update stored credentials
    new_refresh = token_data.get(config.refresh_token_key, refresh_tok)
    expires_in = token_data.get(config.expires_in_key, 0)
    token_expires_at = None
    if expires_in:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    updated_creds = {
        "token": new_access,
        "refresh_token": new_refresh,
        "email": creds.get("email", ""),
    }
    row.encrypted_credentials = encryptor.encrypt(json.dumps(updated_creds))
    if token_expires_at:
        row.token_expires_at = token_expires_at
    row.is_active = True
    row.disconnected_at = None
    await db.flush()

    logger.info("OAuth2 refresh: provider=%s user=%s succeeded", provider, user_id[:8])
    return True


# ── Internal helpers ────────────────────────────────────────────────────────


async def _exchange_code(
    config: OAuth2ProviderConfig,
    code: str,
    client_id: str,
    client_secret: str,
    code_verifier: str,
) -> dict:
    """Exchange an authorization code for tokens via the provider's token endpoint."""
    payload: dict[str, str | None] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT) as client:
        resp = await client.post(config.token_url, data=payload)
        resp.raise_for_status()
        return resp.json()


async def _refresh_token_request(
    config: OAuth2ProviderConfig,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Refresh an access token via the provider's token endpoint."""
    payload: dict[str, str | None] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT) as client:
        resp = await client.post(config.token_url, data=payload)
        resp.raise_for_status()
        return resp.json()


async def _fetch_userinfo(userinfo_url: str, access_token: str) -> tuple[str, str]:
    """Fetch account email and URL from the provider's userinfo endpoint.

    Returns:
        (email, account_url) — empty strings on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            resp.raise_for_status()
            data = resp.json()
            email = data.get("email", "")
            account_url = data.get("account_url", "")
            return email, account_url
    except Exception:
        logger.debug("OAuth2 userinfo fetch failed for %s", userinfo_url, exc_info=True)
        return "", ""


async def _upsert_pm_token(
    db: AsyncSession,
    user_id: str,
    provider: str,
    encrypted_credentials: str,
    account_email: str,
    account_url: str,
    token_expires_at: datetime | None,
) -> None:
    """Upsert a PMIntegrationToken row for (user, provider)."""
    result = await db.execute(
        select(PMIntegrationToken).where(
            PMIntegrationToken.user_id == user_id,
            PMIntegrationToken.provider == provider,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.encrypted_credentials = encrypted_credentials
        row.account_email = account_email
        row.account_url = account_url
        row.token_expires_at = token_expires_at
        row.is_active = True
        row.disconnected_at = None
    else:
        row = PMIntegrationToken(
            user_id=user_id,
            provider=provider,
            encrypted_credentials=encrypted_credentials,
            account_email=account_email,
            account_url=account_url,
            token_expires_at=token_expires_at,
        )
        db.add(row)
    await db.flush()
