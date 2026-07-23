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
