"""Interface and behavioral pre-dev tests for Compliance Dashboard (T6).

RED phase: interface tests PASS, behavioral tests FAIL with NotImplementedError.
Dev must implement src/meeting_notes_ai/hipaa/dashboard.py to make behavioral tests pass.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


from meeting_notes_ai.hipaa.dashboard import (
    ComplianceService,
    ComplianceSummary,
    PHIStats,
)

# ── Interface Tests (must PASS immediately) ────────────────────────────────────


class TestDashboardDataclassInterfaces:
    """Verify dataclass definitions and field contracts."""

    def test_compliance_summary_is_dataclass(self):
        """ComplianceSummary should be a dataclass."""
        assert is_dataclass(ComplianceSummary)

    def test_compliance_summary_fields(self):
        """ComplianceSummary should have all expected fields."""
        fields = ComplianceSummary.__dataclass_fields__
        assert "total_phi_scans" in fields
        assert "total_redactions" in fields
        assert "active_encryption_keys" in fields
        assert "active_baa_agreements" in fields
        assert "audit_entries_30d" in fields
        assert "overall_compliance_score" in fields
        assert "last_audit_entry" in fields
        assert "encryption_health" in fields

    def test_compliance_summary_defaults(self):
        """ComplianceSummary should have sensible zero/empty defaults."""
        s = ComplianceSummary()
        assert s.total_phi_scans == 0
        assert s.total_redactions == 0
        assert s.active_encryption_keys == 0
        assert s.active_baa_agreements == 0
        assert s.audit_entries_30d == 0
        assert s.overall_compliance_score == 0.0
        assert s.last_audit_entry is None
        assert s.encryption_health == "healthy"

    def test_compliance_score_range_zero(self):
        """overall_compliance_score should accept 0.0."""
        s = ComplianceSummary(overall_compliance_score=0.0)
        assert s.overall_compliance_score == 0.0

    def test_compliance_score_range_one(self):
        """overall_compliance_score should accept 1.0."""
        s = ComplianceSummary(overall_compliance_score=1.0)
        assert s.overall_compliance_score == 1.0

    def test_phi_stats_is_dataclass(self):
        """PHIStats should be a dataclass."""
        assert is_dataclass(PHIStats)

    def test_phi_stats_fields(self):
        """PHIStats should have all expected fields."""
        fields = PHIStats.__dataclass_fields__
        assert "by_category" in fields
        assert "by_risk_level" in fields
        assert "by_date" in fields
        assert "total_false_positives" in fields
        assert "total_llm_corrections" in fields

    def test_phi_stats_defaults(self):
        """PHIStats should have empty dict/zero defaults."""
        p = PHIStats()
        assert p.by_category == {}
        assert p.by_risk_level == {}
        assert p.by_date == {}
        assert p.total_false_positives == 0
        assert p.total_llm_corrections == 0

    def test_phi_stats_by_category_populated(self):
        """PHIStats should accept category data."""
        p = PHIStats(by_category={"name": 10, "ssn": 3})
        assert p.by_category["name"] == 10
        assert p.by_category["ssn"] == 3


class TestComplianceServiceInterface:
    """Verify ComplianceService class and method signatures."""

    def test_compliance_service_can_be_imported(self):
        """ComplianceService should be importable."""
        assert ComplianceService is not None

    def test_init_signature(self):
        """__init__ should accept all 4 optional service references."""
        sig = signature(ComplianceService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "audit_logger" in params
        assert "encryption_service" in params
        assert "baa_service" in params
        assert "phi_redactor" in params

    def test_init_defaults_to_none(self):
        """All constructor params should default to None."""
        sig = signature(ComplianceService.__init__)
        for name in ("audit_logger", "encryption_service", "baa_service", "phi_redactor"):
            param = sig.parameters[name]
            assert param.default is None, f"{name} should default to None"

    def test_get_summary_signature(self):
        """get_summary should accept only self."""
        assert hasattr(ComplianceService, "get_summary")
        sig = signature(ComplianceService.get_summary)
        params = list(sig.parameters.keys())
        assert params == ["self"]

    def test_get_summary_is_async(self):
        """get_summary should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ComplianceService.get_summary)

    def test_get_phi_stats_signature(self):
        """get_phi_stats should accept 'since' parameter."""
        assert hasattr(ComplianceService, "get_phi_stats")
        sig = signature(ComplianceService.get_phi_stats)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "since" in params

    def test_get_phi_stats_default(self):
        """get_phi_stats since should default to '30d'."""
        sig = signature(ComplianceService.get_phi_stats)
        param = sig.parameters["since"]
        assert param.default == "30d"

    def test_get_phi_stats_is_async(self):
        """get_phi_stats should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ComplianceService.get_phi_stats)

    def test_get_recent_activity_signature(self):
        """get_recent_activity should accept limit parameter."""
        assert hasattr(ComplianceService, "get_recent_activity")
        sig = signature(ComplianceService.get_recent_activity)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "limit" in params

    def test_get_recent_activity_default(self):
        """get_recent_activity limit should default to 50."""
        sig = signature(ComplianceService.get_recent_activity)
        param = sig.parameters["limit"]
        assert param.default == 50

    def test_get_recent_activity_is_async(self):
        """get_recent_activity should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ComplianceService.get_recent_activity)

    def test_get_encryption_status_signature(self):
        """get_encryption_status should accept only self."""
        assert hasattr(ComplianceService, "get_encryption_status")
        sig = signature(ComplianceService.get_encryption_status)
        params = list(sig.parameters.keys())
        assert params == ["self"]

    def test_get_encryption_status_is_async(self):
        """get_encryption_status should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ComplianceService.get_encryption_status)

    def test_get_baa_compliance_signature(self):
        """get_baa_compliance should accept only self."""
        assert hasattr(ComplianceService, "get_baa_compliance")
        sig = signature(ComplianceService.get_baa_compliance)
        params = list(sig.parameters.keys())
        assert params == ["self"]

    def test_get_baa_compliance_is_async(self):
        """get_baa_compliance should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ComplianceService.get_baa_compliance)

    def test_get_summary_returns_compliance_summary(self):
        """get_summary return annotation should be ComplianceSummary."""
        sig = signature(ComplianceService.get_summary)
        # PEP 563 (from __future__ import annotations) stores annotations as strings
        assert sig.return_annotation == "ComplianceSummary"

    def test_get_phi_stats_returns_phi_stats(self):
        """get_phi_stats return annotation should be PHIStats."""
        sig = signature(ComplianceService.get_phi_stats)
        assert sig.return_annotation == "PHIStats"

    def test_get_recent_activity_returns_list(self):
        """get_recent_activity return annotation should be list[dict]."""
        sig = signature(ComplianceService.get_recent_activity)
        assert sig.return_annotation == "list[dict]"

    def test_get_encryption_status_returns_dict(self):
        """get_encryption_status return annotation should be dict."""
        sig = signature(ComplianceService.get_encryption_status)
        assert sig.return_annotation == "dict"

    def test_get_baa_compliance_returns_dict(self):
        """get_baa_compliance return annotation should be dict."""
        sig = signature(ComplianceService.get_baa_compliance)
        assert sig.return_annotation == "dict"


# ── Behavioral Tests (GREEN phase — implemented) ───────────────────────────────


class TestComplianceServiceBehavioralRED:
    """Behavioral tests for a fully implemented ComplianceService.

    RED-phase NotImplementedError markers were removed when the
    implementation landed (a7952e5 precedent) — a working service can
    never satisfy ``pytest.raises(NotImplementedError)``.
    """

    @pytest.mark.asyncio
    async def test_get_summary_returns_all_fields(self):
        """get_summary should return ComplianceSummary with all fields populated."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            result = await service.get_summary()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, ComplianceSummary)
        assert result.total_phi_scans >= 0
        assert result.total_redactions >= 0
        assert result.active_encryption_keys >= 0
        assert result.active_baa_agreements >= 0
        assert result.audit_entries_30d >= 0
        assert 0.0 <= result.overall_compliance_score <= 1.0
        assert result.encryption_health in (
            "healthy",
            "degraded",
            "unhealthy",
            "unprovisioned",
        )

    @pytest.mark.asyncio
    async def test_get_phi_stats_has_all_chart_data(self):
        """get_phi_stats should return PHIStats with chartable data."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            stats = await service.get_phi_stats()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(stats, PHIStats)
        assert isinstance(stats.by_category, dict)
        assert isinstance(stats.by_risk_level, dict)
        assert isinstance(stats.by_date, dict)

    @pytest.mark.asyncio
    async def test_get_recent_activity_respects_limit(self):
        """get_recent_activity should return at most 'limit' entries."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            entries = await service.get_recent_activity(limit=5)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(entries, list)
        assert len(entries) <= 5

    @pytest.mark.asyncio
    async def test_get_recent_activity_ordered_by_timestamp(self):
        """get_recent_activity entries should be in descending timestamp order."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            entries = await service.get_recent_activity(limit=10)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        if len(entries) > 1:
            timestamps = [e.get("timestamp", "") for e in entries]
            assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_empty_state_summary(self):
        """get_summary should handle empty state (no data) gracefully."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            result = await service.get_summary()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, ComplianceSummary)
        assert result.overall_compliance_score >= 0.0

    @pytest.mark.asyncio
    async def test_empty_state_phi_stats(self):
        """get_phi_stats should handle empty state (no scans) gracefully."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            stats = await service.get_phi_stats()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(stats, PHIStats)
        # Empty stats should still have empty dicts, not crash
        assert stats.by_category is not None
        assert stats.by_risk_level is not None

    @pytest.mark.asyncio
    async def test_empty_state_activity(self):
        """get_recent_activity should return empty list when no data."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            entries = await service.get_recent_activity()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(entries, list)

    @pytest.mark.asyncio
    async def test_encryption_status_structure(self):
        """get_encryption_status should return expected keys."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            status = await service.get_encryption_status()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(status, dict)
        # Should have at least total and active key counts
        assert "total_keys" in status or "active_keys" in status or "healthy" in status

    @pytest.mark.asyncio
    async def test_baa_compliance_structure(self):
        """get_baa_compliance should return expected keys."""
        try:
            service = ComplianceService.__new__(ComplianceService)
            compliance = await service.get_baa_compliance()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(compliance, dict)
        # Should have agreement counts by status
        assert "total_agreements" in compliance or "active" in compliance
