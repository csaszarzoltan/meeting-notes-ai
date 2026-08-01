"""Interface + behavioral pre-tests for HIPAAConfig."""

import os
from dataclasses import is_dataclass

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


from meeting_notes_ai.hipaa.config import HIPAAConfig

# ── Interface tests (should pass immediately) ──────────────────────────────

class TestHIPAAConfigInterface:
    """Verify HIPAAConfig dataclass structure and defaults."""

    def test_is_dataclass(self):
        """HIPAAConfig should be a dataclass."""
        assert is_dataclass(HIPAAConfig)

    def test_default_phi_patterns_path(self):
        """Default phi_patterns_path should point to the patterns file."""
        cfg = HIPAAConfig()
        assert cfg.phi_patterns_path == "hipaa/phi_patterns.json"

    def test_default_audit_log_dir(self):
        """Default audit_log_dir should be data/audit_logs/."""
        cfg = HIPAAConfig()
        assert cfg.audit_log_dir == "data/audit_logs/"

    def test_default_audit_log_retention_days(self):
        """Default retention should be 6 years (2190 days)."""
        cfg = HIPAAConfig()
        assert cfg.audit_log_retention_days == 365 * 6

    def test_default_encryption_enabled(self):
        """Encryption should be enabled by default."""
        cfg = HIPAAConfig()
        assert cfg.encryption_enabled is True

    def test_default_master_key_env_var(self):
        """Default master key env var should be HIPAA_MASTER_KEY."""
        cfg = HIPAAConfig()
        assert cfg.master_key_env_var == "HIPAA_MASTER_KEY"

    def test_default_baa_effective_days(self):
        cfg = HIPAAConfig()
        assert cfg.default_baa_effective_days == 365

    def test_default_llm_validation_enabled(self):
        """LLM validation should be enabled by default."""
        cfg = HIPAAConfig()
        assert cfg.llm_validation_enabled is True

    def test_default_llm_validation_threshold(self):
        """Default LLM validation threshold should be 0.8."""
        cfg = HIPAAConfig()
        assert cfg.llm_validation_threshold == 0.8

    def test_phi_patterns_path_field_exists(self):
        assert "phi_patterns_path" in HIPAAConfig.__dataclass_fields__

    def test_audit_log_dir_field_exists(self):
        assert "audit_log_dir" in HIPAAConfig.__dataclass_fields__

    def test_audit_log_retention_days_field_exists(self):
        assert "audit_log_retention_days" in HIPAAConfig.__dataclass_fields__

    def test_encryption_enabled_field_exists(self):
        assert "encryption_enabled" in HIPAAConfig.__dataclass_fields__

    def test_master_key_env_var_field_exists(self):
        assert "master_key_env_var" in HIPAAConfig.__dataclass_fields__

    def test_llm_validation_enabled_field_exists(self):
        assert "llm_validation_enabled" in HIPAAConfig.__dataclass_fields__

    def test_llm_validation_threshold_field_exists(self):
        assert "llm_validation_threshold" in HIPAAConfig.__dataclass_fields__

    def test_encryption_key_length_field_exists(self):
        assert "encryption_key_length" in HIPAAConfig.__dataclass_fields__

    def test_audit_log_max_bytes_field_exists(self):
        assert "audit_log_max_bytes" in HIPAAConfig.__dataclass_fields__

    def test_audit_log_backup_count_field_exists(self):
        assert "audit_log_backup_count" in HIPAAConfig.__dataclass_fields__

    def test_scan_timeout_ms_field_exists(self):
        assert "scan_timeout_ms" in HIPAAConfig.__dataclass_fields__

    def test_encryption_nonce_length_field_exists(self):
        assert "encryption_nonce_length" in HIPAAConfig.__dataclass_fields__

    def test_default_encryption_key_length_is_32(self):
        """AES-256 requires 32-byte keys."""
        cfg = HIPAAConfig()
        assert cfg.encryption_key_length == 32

    def test_default_encryption_nonce_length_is_12(self):
        """GCM standard nonce length is 12 bytes."""
        cfg = HIPAAConfig()
        assert cfg.encryption_nonce_length == 12

    def test_scan_timeout_default_100ms(self):
        cfg = HIPAAConfig()
        assert cfg.scan_timeout_ms == 100

    def test_audit_log_max_bytes_default_100mb(self):
        cfg = HIPAAConfig()
        assert cfg.audit_log_max_bytes == 100 * 1024 * 1024

    def test_validates_threshold_range_too_low(self):
        """Threshold < 0 should raise ValueError."""
        with pytest.raises(ValueError):
            HIPAAConfig(llm_validation_threshold=-0.1)

    def test_validates_threshold_range_too_high(self):
        """Threshold > 1 should raise ValueError."""
        with pytest.raises(ValueError):
            HIPAAConfig(llm_validation_threshold=1.5)

    def test_validates_retention_days_too_low(self):
        """Retention days < 1 should raise ValueError."""
        with pytest.raises(ValueError):
            HIPAAConfig(audit_log_retention_days=0)

    def test_threshold_at_zero_is_valid(self):
        """Threshold = 0.0 should be valid (disables LLM validation)."""
        cfg = HIPAAConfig(llm_validation_threshold=0.0)
        assert cfg.llm_validation_threshold == 0.0

    def test_threshold_at_one_is_valid(self):
        """Threshold = 1.0 should be valid."""
        cfg = HIPAAConfig(llm_validation_threshold=1.0)
        assert cfg.llm_validation_threshold == 1.0

    def test_custom_values(self):
        """Custom values should override defaults."""
        cfg = HIPAAConfig(
            phi_patterns_path="/custom/patterns.json",
            audit_log_dir="/custom/logs/",
            encryption_enabled=False,
        )
        assert cfg.phi_patterns_path == "/custom/patterns.json"
        assert cfg.audit_log_dir == "/custom/logs/"
        assert cfg.encryption_enabled is False

    def test_can_create_with_all_override_fields(self):
        """Should be able to override every field."""
        cfg = HIPAAConfig(
            phi_patterns_path="/a",
            audit_log_dir="/b",
            audit_log_retention_days=30,
            encryption_enabled=False,
            master_key_env_var="MY_KEY",
            default_baa_effective_days=90,
            llm_validation_enabled=False,
            llm_validation_threshold=0.5,
        )
        assert cfg.audit_log_retention_days == 30
        assert cfg.default_baa_effective_days == 90


# ── Behavioral pre-tests (will fail with NotImplementedError until dev) ────

class TestHIPAAConfigBehavioral:
    """Expected behaviors once HIPAAConfig is wired into services."""

    def test_config_passed_to_redactor(self, hipaa_config):
        """HIPAAConfig should be accepted by PHIRedactor."""
        from meeting_notes_ai.hipaa.redactor import PHIRedactor

        try:
            PHIRedactor(hipaa_config)
        except NotImplementedError:
            pytest.skip("RED phase — PHIRedactor not implemented")

    def test_config_passed_to_audit_logger(self, hipaa_config):
        """HIPAAConfig should be accepted by AuditLogger."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        try:
            AuditLogger(hipaa_config)
        except NotImplementedError:
            pytest.skip("RED phase — AuditLogger not implemented")

    def test_config_passed_to_encryption_service(self, hipaa_config):
        """HIPAAConfig should be accepted by EncryptionService."""
        from meeting_notes_ai.hipaa.encryption import EncryptionService

        old = os.environ.get("HIPAA_MASTER_KEY")
        os.environ["HIPAA_MASTER_KEY"] = "ab" * 32
        try:
            EncryptionService(hipaa_config, lambda: None)
        except NotImplementedError:
            pytest.skip("RED phase — EncryptionService not implemented")
        finally:
            if old is None:
                del os.environ["HIPAA_MASTER_KEY"]
            else:
                os.environ["HIPAA_MASTER_KEY"] = old

    def test_config_passed_to_llm_validator(self, hipaa_config):
        """HIPAAConfig should be accepted by LLMValidator."""
        try:
            from meeting_notes_ai.hipaa.llm_validator import LLMValidator
            LLMValidator(None, hipaa_config)
        except NotImplementedError:
            pytest.skip("RED phase — LLMValidator not implemented")
