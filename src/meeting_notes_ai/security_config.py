"""Fail-fast validation for production security configuration."""

from __future__ import annotations

import logging

from meeting_notes_ai.config import Settings

logger = logging.getLogger(__name__)

_DEVELOPMENT_JWT_SECRET = "meeting-notes-ai-secret-key-change-in-production"


def validate_production_settings(settings: Settings) -> None:
    """Reject insecure settings before the application accepts traffic."""
    if settings.environment.lower() != "production":
        return
    errors: list[str] = []
    if (
        not settings.jwt_secret
        or settings.jwt_secret == _DEVELOPMENT_JWT_SECRET
        or len(settings.jwt_secret) < 32
    ):
        errors.append("JWT_SECRET must be a unique secret of at least 32 characters")
    if settings.admin_api_enabled and len(settings.admin_api_token) < 32:
        errors.append(
            "ADMIN_API_TOKEN must contain at least 32 characters when the admin API is enabled"
        )
    if errors:
        raise RuntimeError("; ".join(errors))


def validate_storage_settings(settings: Settings) -> None:
    """Fail fast when the storage encryption mode cannot be honoured.

    ``STORAGE_ENCRYPTION=aes256gcm`` without a key source
    (``STORAGE_ENCRYPTION_KEY`` or ``HIPAA_MASTER_KEY``) would silently
    disable at-rest encryption — refuse to boot instead (brief §8). In
    production with healthcare mode, warn when encryption is not enabled.
    """
    if settings.storage_encryption == "aes256gcm":
        seed = (
            settings.storage_encryption_key
            or _env("STORAGE_ENCRYPTION_KEY")
            or _env("HIPAA_MASTER_KEY")
        )
        if not seed:
            raise RuntimeError(
                "STORAGE_ENCRYPTION=aes256gcm requires STORAGE_ENCRYPTION_KEY "
                "(or HIPAA_MASTER_KEY) — refusing to store files in plaintext"
            )
    if settings.environment.lower() == "production" and (
        settings.storage_encryption or "none"
    ) != "aes256gcm":
        logger.warning(
            "HIPAA deployments must set STORAGE_ENCRYPTION=aes256gcm — "
            "stored audio/transcripts are NOT encrypted at rest"
        )

def _env(name: str) -> str:
    import os

    return os.getenv(name, "")
