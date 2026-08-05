"""Pre-development interface and behavioral tests for PHI Detection & Redaction.

Tests the PHIRedactor, PHIMatch, and PHIRedactionResult classes from the
hipaa module. Interface tests must pass immediately; behavioral tests will
fail (RED phase) until the implementation is completed.

Module under test:
  src/meeting_notes_ai/hipaa/phi_patterns.py  — PHIMatch, PHIRedactionResult, PHIRedactor
  src/meeting_notes_ai/hipaa/config.py        — HIPAAConfig
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHIPAAConfigInterface:
    """Verify HIPAAConfig dataclass contract."""

    def test_hipaa_config_importable(self):
        """HIPAAConfig exists and is importable."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert HIPAAConfig is not None

    def test_hipaa_config_is_dataclass(self):
        """HIPAAConfig is a dataclass."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert is_dataclass(HIPAAConfig)

    def test_hipaa_config_has_phi_patterns_path(self):
        """HIPAAConfig has phi_patterns_path field (str)."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "phi_patterns_path")

    def test_hipaa_config_has_audit_log_dir(self):
        """HIPAAConfig has audit_log_dir field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "audit_log_dir")

    def test_hipaa_config_has_audit_log_retention_days(self):
        """HIPAAConfig has audit_log_retention_days field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "audit_log_retention_days")

    def test_hipaa_config_has_encryption_enabled(self):
        """HIPAAConfig has encryption_enabled field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "encryption_enabled")

    def test_hipaa_config_has_master_key_env_var(self):
        """HIPAAConfig has master_key_env_var field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "master_key_env_var")

    def test_hipaa_config_has_default_baa_effective_days(self):
        """HIPAAConfig has default_baa_effective_days field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "default_baa_effective_days")

    def test_hipaa_config_has_llm_validation_enabled(self):
        """HIPAAConfig has llm_validation_enabled field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "llm_validation_enabled")

    def test_hipaa_config_has_llm_validation_threshold(self):
        """HIPAAConfig has llm_validation_threshold field."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        assert hasattr(HIPAAConfig, "llm_validation_threshold")

    def test_hipaa_config_defaults(self):
        """HIPAAConfig default values are correct."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        cfg = HIPAAConfig()
        assert cfg.phi_patterns_path == "hipaa/phi_patterns.json"
        assert cfg.audit_log_dir == "data/audit_logs/"
        assert cfg.audit_log_retention_days == 365 * 6
        assert cfg.encryption_enabled is True
        assert cfg.master_key_env_var == "HIPAA_MASTER_KEY"
        assert cfg.default_baa_effective_days == 365
        assert cfg.llm_validation_enabled is True
        assert cfg.llm_validation_threshold == 0.8

    def test_hipaa_config_can_be_instantiated_with_overrides(self):
        """HIPAAConfig can be instantiated with overridden values."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        cfg = HIPAAConfig(
            phi_patterns_path="/custom/patterns.json",
            encryption_enabled=False,
            llm_validation_threshold=0.9,
        )
        assert cfg.phi_patterns_path == "/custom/patterns.json"
        assert cfg.encryption_enabled is False
        assert cfg.llm_validation_threshold == 0.9


class TestPHIMatchInterface:
    """Verify PHIMatch dataclass contract."""

    def test_phi_match_importable(self):
        """PHIMatch exists and is importable."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert PHIMatch is not None

    def test_phi_match_is_dataclass(self):
        """PHIMatch is a dataclass."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert is_dataclass(PHIMatch)

    def test_phi_match_has_category_field(self):
        """PHIMatch has category field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "category")

    def test_phi_match_has_label_field(self):
        """PHIMatch has label field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "label")

    def test_phi_match_has_risk_level_field(self):
        """PHIMatch has risk_level field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "risk_level")

    def test_phi_match_has_start_end_fields(self):
        """PHIMatch has start and end fields."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "start")
        assert hasattr(PHIMatch, "end")

    def test_phi_match_has_matched_text_field(self):
        """PHIMatch has matched_text field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "matched_text")

    def test_phi_match_has_redaction_mode_field(self):
        """PHIMatch has redaction_mode field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        assert hasattr(PHIMatch, "redaction_mode")

    def test_phi_match_defaults(self):
        """PHIMatch has sensible default values."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        m = PHIMatch()
        assert m.category == ""
        assert m.label == ""
        assert m.risk_level == "low"
        assert m.start == 0
        assert m.end == 0
        assert m.matched_text == ""
        assert m.redaction_mode == "mask"

    def test_phi_match_instantiation(self):
        """PHIMatch can be instantiated with all fields."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

        m = PHIMatch(
            category="ssn",
            label="Social Security Number",
            risk_level="high",
            start=10,
            end=20,
            matched_text="123-45-6789",
            redaction_mode="mask",
        )
        assert m.category == "ssn"
        assert m.label == "Social Security Number"
        assert m.risk_level == "high"
        assert m.start == 10
        assert m.end == 20
        assert m.matched_text == "123-45-6789"


class TestPHIRedactionResultInterface:
    """Verify PHIRedactionResult dataclass contract."""

    def test_phi_redaction_result_importable(self):
        """PHIRedactionResult exists and is importable."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactionResult

        assert PHIRedactionResult is not None

    def test_phi_redaction_result_is_dataclass(self):
        """PHIRedactionResult is a dataclass."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactionResult

        assert is_dataclass(PHIRedactionResult)

    @property
    def _redaction_result_field_names(self):
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactionResult

        return {f.name for f in fields(PHIRedactionResult)}

    def test_phi_redaction_result_has_redacted_text(self):
        """PHIRedactionResult has redacted_text field."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactionResult

        assert hasattr(PHIRedactionResult, "redacted_text")

    def test_phi_redaction_result_has_matches(self):
        """PHIRedactionResult has matches list field."""
        assert "matches" in self._redaction_result_field_names

    def test_phi_redaction_result_has_count_by_category(self):
        """PHIRedactionResult has count_by_category dict field."""
        assert "count_by_category" in self._redaction_result_field_names

    def test_phi_redaction_result_defaults(self):
        """PHIRedactionResult defaults to empty state."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactionResult

        r = PHIRedactionResult()
        assert r.redacted_text == ""
        assert r.matches == []
        assert r.count_by_category == {}


class TestPHIRedactorInterface:
    """Verify PHIRedactor class contract."""

    def test_phi_redactor_importable(self):
        """PHIRedactor exists and is importable."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert PHIRedactor is not None

    def test_phi_redactor_init_signature(self):
        """PHIRedactor.__init__ accepts optional config."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        sig = signature(PHIRedactor.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_phi_redactor_scan_method_exists(self):
        """PHIRedactor has a scan method."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert hasattr(PHIRedactor, "scan")

    def test_phi_redactor_scan_signature(self):
        """scan(text: str) -> list[PHIMatch]."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        sig = signature(PHIRedactor.scan)
        assert "text" in sig.parameters

    def test_phi_redactor_redact_method_exists(self):
        """PHIRedactor has a redact method."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert hasattr(PHIRedactor, "redact")

    def test_phi_redactor_redact_signature(self):
        """redact(text: str, mode: str = 'mask') -> tuple[str, list[PHIMatch]]."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        sig = signature(PHIRedactor.redact)
        params = sig.parameters
        assert "text" in params
        assert "mode" in params
        # mode should default to "mask"
        assert params["mode"].default == "mask"

    def test_phi_redactor_add_custom_pattern_exists(self):
        """PHIRedactor has add_custom_pattern method."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert hasattr(PHIRedactor, "add_custom_pattern")

    def test_phi_redactor_get_stats_exists(self):
        """PHIRedactor has get_stats method."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert hasattr(PHIRedactor, "get_stats")

    def test_phi_redactor_reload_patterns_exists(self):
        """PHIRedactor has reload_patterns method."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        assert hasattr(PHIRedactor, "reload_patterns")

    def test_phi_redactor_can_be_instantiated(self):
        """PHIRedactor can be instantiated (with default config)."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        redactor = PHIRedactor()
        assert redactor is not None

    def test_phi_redactor_accepts_config(self):
        """PHIRedactor accepts a HIPAAConfig instance."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        cfg = HIPAAConfig(phi_patterns_path="/custom/patterns.json")
        redactor = PHIRedactor(config=cfg)
        assert redactor is not None
        assert redactor.config.phi_patterns_path == "/custom/patterns.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (will FAIL until implementation is done)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPHIRedactorBehavioral:
    """Behavioral tests for PHIRedactor."""

    @pytest.fixture
    def redactor(self):
        """Provide a default PHIRedactor instance."""
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        return PHIRedactor()

    def test_scan_returns_empty_list_for_empty_text(self, redactor):
        """scan() returns empty list for empty text."""
        assert redactor.scan("") == []

    def test_scan_detects_ssn(self, redactor):
        """scan() detects SSN pattern (XXX-XX-XXXX)."""
        matches = redactor.scan("Patient SSN is 123-45-6789.")
        assert len(matches) >= 1
        assert matches[0].category == "ssn"

    def test_scan_detects_dob(self, redactor):
        """scan() detects date of birth pattern."""
        matches = redactor.scan("Date of birth: 01/15/1980.")
        assert len(matches) >= 1
        assert matches[0].category == "dob"

    def test_scan_detects_phone(self, redactor):
        """scan() detects phone number pattern."""
        matches = redactor.scan("Call me at 555-123-4567.")
        assert len(matches) >= 1
        assert matches[0].category == "phone"

    def test_scan_detects_email(self, redactor):
        """scan() detects email address."""
        matches = redactor.scan("Email: jane.doe@example.com")
        assert len(matches) >= 1
        assert matches[0].category == "email"

    def test_scan_detects_name_pattern(self, redactor):
        """scan() detects first-last name patterns."""
        matches = redactor.scan("The patient John Smith was seen today.")
        assert len(matches) >= 1

    def test_redact_mask_replaces_with_placeholder(self, redactor):
        """redact(mode='mask') replaces PHI with [REDACTED]."""
        redacted, matches = redactor.redact("SSN: 123-45-6789", mode="mask")
        assert "[REDACTED]" in redacted
        assert "123-45-6789" not in redacted

    def test_redact_returns_matches(self, redactor):
        """redact() returns the list of PHIMatch objects."""
        redacted, matches = redactor.redact("Email: test@example.com")
        assert isinstance(matches, list)
        if matches:
            from meeting_notes_ai.hipaa.phi_patterns import PHIMatch

            assert isinstance(matches[0], PHIMatch)

    def test_add_custom_pattern_adds_pattern(self, redactor):
        """add_custom_pattern registers a new pattern at runtime."""
        redactor.add_custom_pattern("custom_id", r"\bCUST-\d{4}\b", "medium")
        matches = redactor.scan("Reference CUST-1234 found.")
        assert any(m.category == "custom_id" for m in matches)

    def test_get_stats_returns_dict(self, redactor):
        """get_stats() returns a dict with expected keys."""
        redactor.scan("Test text with SSN 123-45-6789 and email a@b.com")
        stats = redactor.get_stats()
        assert isinstance(stats, dict)

    def test_reload_patterns_returns_int(self, redactor):
        """reload_patterns() returns an integer (pattern count)."""
        count = redactor.reload_patterns()
        assert isinstance(count, int)
        assert count > 0

    def test_scan_handles_unicode(self, redactor):
        """scan() handles Unicode text without errors."""
        matches = redactor.scan("Patient name: José García — MRN: 1234567")
        # Should not raise and should find MRN at minimum
        assert isinstance(matches, list)

    def test_scan_text_with_multiple_phi_categories(self, redactor):
        """scan() detects multiple PHI categories in single text."""
        matches = redactor.scan(
            "John Smith (SSN: 123-45-6789, DOB: 01/15/1980, "
            "phone: 555-123-4567, email: john@example.com)"
        )
        categories = {m.category for m in matches}
        assert len(categories) >= 2  # At least name + one other


# ═══════════════════════════════════════════════════════════════════════════════
# S4 regression tests — compile-once patterns, scan timeout, zero-width rejection
# ═══════════════════════════════════════════════════════════════════════════════


class TestPHICompileOnce:
    """S4: scan() must use a precompiled pattern set, never recompile per call."""

    def test_scan_does_not_recompile_patterns(self, monkeypatch):
        """scan() performs zero re.compile calls after construction."""
        import meeting_notes_ai.hipaa.phi_patterns as phi

        calls = {"n": 0}
        original_compile = phi.re.compile

        def counting_compile(pattern, *args, **kwargs):
            calls["n"] += 1
            return original_compile(pattern, *args, **kwargs)

        monkeypatch.setattr(phi.re, "compile", counting_compile)

        redactor = phi.PHIRedactor()
        compiles_at_init = calls["n"]
        # Default set = 6 named patterns + the generic name pattern.
        assert compiles_at_init >= 7

        redactor.scan("Patient John Smith, SSN 123-45-6789.")
        redactor.scan("Email jane.doe@example.com — MRN: 1234567")
        assert calls["n"] == compiles_at_init, "scan() recompiled patterns"


class TestPHIScanTimeout:
    """S4: scan() must respect scan_timeout_ms and fail fast, never hang."""

    def test_scan_raises_after_timeout(self, monkeypatch):
        """A scan past scan_timeout_ms raises PHIScanTimeoutError."""
        import meeting_notes_ai.hipaa.phi_patterns as phi
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        clock = {"t": 0.0}

        def fake_monotonic():
            clock["t"] += 0.05  # 50 ms per read — far past a 1 ms budget
            return clock["t"]

        monkeypatch.setattr(phi, "_monotonic", fake_monotonic)
        redactor = phi.PHIRedactor(config=HIPAAConfig(scan_timeout_ms=1))

        with pytest.raises(phi.PHIScanTimeoutError):
            redactor.scan("John Smith (SSN: 123-45-6789, DOB: 01/15/1980)")

    def test_scan_timeout_zero_disables_guard(self, monkeypatch):
        """scan_timeout_ms <= 0 disables the timeout guard entirely."""
        import meeting_notes_ai.hipaa.phi_patterns as phi
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        clock = {"t": 0.0}

        def fake_monotonic():
            clock["t"] += 0.05
            return clock["t"]

        monkeypatch.setattr(phi, "_monotonic", fake_monotonic)
        redactor = phi.PHIRedactor(config=HIPAAConfig(scan_timeout_ms=0))

        matches = redactor.scan("SSN 123-45-6789")
        assert any(m.category == "ssn" for m in matches)


class TestPHIRecompileRejectsZeroWidth:
    """S4: _recompile must reject empty/zero-width patterns from JSON."""

    def test_zero_width_patterns_are_skipped(self, tmp_path):
        """Empty and zero-width patterns never enter the compiled set."""
        import json

        import meeting_notes_ai.hipaa.phi_patterns as phi
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(
            json.dumps(
                {
                    "ssn": {
                        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                        "label": "SSN",
                        "risk_level": "high",
                    },
                    "empty": {
                        "pattern": "",
                        "label": "Empty",
                        "risk_level": "low",
                    },
                    "star": {
                        "pattern": r"a*",
                        "label": "Star",
                        "risk_level": "low",
                    },
                    "group": {
                        "pattern": r"(?:)",
                        "label": "Empty group",
                        "risk_level": "low",
                    },
                    "lookahead": {
                        "pattern": r"(?=foo)",
                        "label": "Lookahead",
                        "risk_level": "low",
                    },
                }
            )
        )

        redactor = phi.PHIRedactor(config=HIPAAConfig(phi_patterns_path=str(patterns_file)))

        # Empty/zero-width patterns never enter the compiled set.
        assert "ssn" in redactor._compiled
        assert "empty" not in redactor._compiled
        assert "star" not in redactor._compiled
        assert "group" not in redactor._compiled
        # A pure lookahead is compiled (it cannot match empty input) but
        # its zero-width matches are skipped at runtime.
        assert "lookahead" in redactor._compiled

        matches = redactor.scan("Call 123-45-6789 about foo, aaa")
        categories = {m.category for m in matches}
        assert "ssn" in categories
        assert "empty" not in categories
        assert "star" not in categories
        assert "group" not in categories
        assert "lookahead" not in categories
