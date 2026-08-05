"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o"))
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "whisper-1"))
    max_audio_size_mb: int = field(
        default_factory=lambda: int(os.getenv("MAX_AUDIO_SIZE_MB", "25"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./meeting_notes.db")
    )
    database_echo: bool = field(
        default_factory=lambda: os.getenv("DATABASE_ECHO", "false").lower() in {"1", "true", "yes"}
    )
    jwt_secret: str = field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET", "meeting-notes-ai-secret-key-change-in-production"
        )
    )
    admin_api_enabled: bool = field(
        default_factory=lambda: (
            os.getenv("ADMIN_API_ENABLED", "false").lower() in {"1", "true", "yes"}
        )
    )
    admin_api_token: str = field(default_factory=lambda: os.getenv("ADMIN_API_TOKEN", ""))
    RATE_LIMIT_FREE_DAILY: int = field(
        default_factory=lambda: int(os.getenv("MEETING_RATE_LIMIT_FREE_DAILY", "100"))
    )
    RATE_LIMIT_PRO_DAILY: int = field(
        default_factory=lambda: int(os.getenv("MEETING_RATE_LIMIT_PRO_DAILY", "10000"))
    )
    RATE_LIMIT_ENTERPRISE_UNLIMITED: bool = field(
        default_factory=lambda: (
            os.getenv("MEETING_RATE_LIMIT_ENTERPRISE_UNLIMITED", "true").lower()
            in {"1", "true", "yes"}
        )
    )
    RATE_LIMIT_BURST_FACTOR: float = field(
        default_factory=lambda: float(os.getenv("MEETING_RATE_LIMIT_BURST_FACTOR", "1.0"))
    )

    # ── Secure file storage (v0.7.0) ─────────────────────────────────────────
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    storage_local_dir: str = field(
        default_factory=lambda: os.getenv("STORAGE_LOCAL_DIR", "data/storage")
    )
    s3_endpoint_url: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL", ""))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", "meeting-notes-ai"))
    s3_region: str = field(default_factory=lambda: os.getenv("S3_REGION", "us-east-1"))
    s3_access_key_id: str = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY_ID", ""))
    s3_secret_access_key: str = field(default_factory=lambda: os.getenv("S3_SECRET_ACCESS_KEY", ""))
    s3_force_path_style: bool = field(
        default_factory=lambda: (
            os.getenv("S3_FORCE_PATH_STYLE", "true").lower() in {"1", "true", "yes"}
        )
    )
    storage_encryption: str = field(default_factory=lambda: os.getenv("STORAGE_ENCRYPTION", "none"))
    storage_encryption_key: str = field(
        default_factory=lambda: os.getenv("STORAGE_ENCRYPTION_KEY", "")
    )
    default_retention_days: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_RETENTION_DAYS", "2190"))
    )
    retention_sweep_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("RETENTION_SWEEP_INTERVAL_SECONDS", "86400"))
    )

    # Shared patterns reference
    RAILWAY_HEALTHCHECK_PATH: str = "/healthz"

    @property
    def SUPPORTED_AUDIO_FORMATS(self) -> set[str]:
        """Supported audio MIME types."""
        return {"audio/wav", "audio/mpeg", "audio/mp4", "audio/webm"}

    @classmethod
    def load(cls) -> Settings:
        """Load settings from environment."""
        return cls()


settings = Settings()
