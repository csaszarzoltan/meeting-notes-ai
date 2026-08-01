"""Acceptance tests for production startup and credential handling."""

import pytest

from meeting_notes_ai.config import Settings
from meeting_notes_ai.security_config import validate_production_settings


def test_development_settings_keep_local_database_default():
    settings = Settings()
    assert settings.database_url.startswith("sqlite+aiosqlite:///")


def test_production_rejects_default_jwt_secret():
    settings = Settings(
        environment="production", jwt_secret="meeting-notes-ai-secret-key-change-in-production"
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_settings(settings)


def test_production_requires_admin_token_when_admin_api_enabled():
    settings = Settings(
        environment="production",
        jwt_secret="x" * 48,
        admin_api_enabled=True,
        admin_api_token="",
    )
    with pytest.raises(RuntimeError, match="ADMIN_API_TOKEN"):
        validate_production_settings(settings)


def test_production_accepts_strong_required_secrets():
    settings = Settings(
        environment="production",
        jwt_secret="j" * 48,
        admin_api_enabled=True,
        admin_api_token="a" * 48,
    )
    validate_production_settings(settings)
