"""HIPAA compliance configuration for MeetingNotesAI.

Provides shared configuration for BAA templates, encryption,
audit logging, and PHI redaction modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HIPAAConfig:
    """HIPAA compliance configuration.

    Settings are loaded from environment variables with sensible defaults
    for development and testing.
    """

    # BAA template path (relative to this module's templates dir)
    baa_template_path: str = field(
        default_factory=lambda: os.getenv(
            "HIPAA_BAA_TEMPLATE_PATH",
            str(Path(__file__).parent / "templates" / "baa_template.md.jinja"),
        )
    )

    # Encryption
    encryption_key_rotation_days: int = field(
        default_factory=lambda: int(os.getenv("HIPAA_KEY_ROTATION_DAYS", "90"))
    )

    # Audit log retention in days
    audit_retention_days: int = field(
        default_factory=lambda: int(os.getenv("HIPAA_AUDIT_RETENTION_DAYS", "1825"))
    )  # 5 years per HIPAA

    # Whether PHI redaction is enforced globally
    phi_redaction_enforced: bool = field(
        default_factory=lambda: os.getenv("HIPAA_PHI_REDACTION", "true").lower()
        == "true"
    )

    @classmethod
    def load(cls) -> HIPAAConfig:
        """Load HIPAA config from environment."""
        return cls()
