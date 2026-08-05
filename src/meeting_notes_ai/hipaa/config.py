"""HIPAA compliance configuration for MeetingNotesAI.

Provides shared configuration for PHI redaction, audit logging, encryption,
BAA templates, and LLM validation modules. All defaults per HIPAA §164.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HIPAAConfig:
    """HIPAA compliance configuration dataclass.

    All fields have sensible defaults for development and testing.
    Validation ensures thresholds and retention values are in range.
    """

    # ── PHI Redaction ──────────────────────────────────────────────────────────
    phi_patterns_path: str = "hipaa/phi_patterns.json"
    """Path to the PHI patterns JSON file (relative to app root)."""

    scan_timeout_ms: int = 100
    """Max time in milliseconds for a single scan() call."""

    # ── Audit Logging ──────────────────────────────────────────────────────────
    audit_log_dir: str = "data/audit_logs/"
    """Directory for append-only JSONL audit log files."""

    audit_log_retention_days: int = 365 * 6  # 6 years per HIPAA
    """Number of days to retain audit log entries (HIPAA min 6 years)."""

    audit_log_max_bytes: int = 100 * 1024 * 1024  # 100 MB
    """Max size of a single audit log file before rotation."""

    audit_log_backup_count: int = 0
    """Number of backup log files to keep (0 = unlimited)."""

    # ── Encryption ─────────────────────────────────────────────────────────────
    encryption_enabled: bool = True
    """Whether encryption at rest is enabled globally."""

    master_key_env_var: str = "HIPAA_MASTER_KEY"
    """Environment variable name holding the master key encryption key (KEK)."""

    encryption_key_length: int = 32
    """AES-256 key length in bytes (32 = 256 bits)."""

    encryption_nonce_length: int = 12
    """GCM standard nonce length in bytes (12 = 96 bits)."""

    # ── BAA Template ───────────────────────────────────────────────────────────
    baa_template_path: str = "hipaa/templates/baa_template.md.jinja"
    """Path to the BAA Jinja2 template file."""

    default_baa_effective_days: int = 365
    """Default number of days a BAA agreement is effective."""

    # ── LLM Validation ─────────────────────────────────────────────────────────
    llm_validation_enabled: bool = True
    """Whether LLM-based PHI validation pass is enabled."""

    llm_validation_threshold: float = 0.8
    """Confidence threshold (0.0-1.0) for LLM validation results."""

    def __post_init__(self) -> None:
        """Validate field values after initialisation."""
        if self.llm_validation_threshold < 0.0 or self.llm_validation_threshold > 1.0:
            raise ValueError(
                f"llm_validation_threshold must be between 0.0 and 1.0, "
                f"got {self.llm_validation_threshold}"
            )
        if self.audit_log_retention_days < 1:
            raise ValueError(
                f"audit_log_retention_days must be >= 1, got {self.audit_log_retention_days}"
            )

    @classmethod
    def load(cls) -> HIPAAConfig:
        """Load HIPAA config from defaults (env var overrides TBD)."""
        return cls()
