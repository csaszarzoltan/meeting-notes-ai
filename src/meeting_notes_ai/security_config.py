"""Fail-fast validation for production security configuration."""

from __future__ import annotations

from meeting_notes_ai.config import Settings

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
