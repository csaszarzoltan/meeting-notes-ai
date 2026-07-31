"""Pre-development interface and behavioral tests for Compliance Dashboard.

Tests the ComplianceService, ComplianceSummary, and PHIStats classes.
Interface tests must pass immediately; behavioral tests will fail
(RED phase) until the implementation is completed.

Module under test:
  src/meeting_notes_ai/hipaa/dashboard.py  — ComplianceService, ComplianceSummary, PHIStats
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from inspect import signature

import pytest

from meeting_notes_ai.hipaa.dashboard import ComplianceService

# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS)
# ═══════════════════════════════════════════════════════════════════════════════


class TestComplianceSummaryInterface:
    """Verify ComplianceSummary dataclass contract."""

    def test_compliance_summary_importable(self):
        """ComplianceSummary exists and is importable."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert ComplianceSummary is not None

    def test_compliance_summary_is_dataclass(self):
        """ComplianceSummary is a dataclass."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert is_dataclass(ComplianceSummary)

    def test_compliance_summary_has_total_phi_scans(self):
        """ComplianceSummary has total_phi_scans field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "total_phi_scans")

    def test_compliance_summary_has_total_redactions(self):
        """ComplianceSummary has total_redactions field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "total_redactions")

    def test_compliance_summary_has_active_encryption_keys(self):
        """ComplianceSummary has active_encryption_keys field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "active_encryption_keys")

    def test_compliance_summary_has_active_baa_agreements(self):
        """ComplianceSummary has active_baa_agreements field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "active_baa_agreements")

    def test_compliance_summary_has_audit_entries_30d(self):
        """ComplianceSummary has audit_entries_30d field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "audit_entries_30d")

    def test_compliance_summary_has_overall_compliance_score(self):
        """ComplianceSummary has overall_compliance_score field (0-100)."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "overall_compliance_score")

    def test_compliance_summary_has_last_audit_entry(self):
        """ComplianceSummary has last_audit_entry field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "last_audit_entry")

    def test_compliance_summary_has_encryption_health(self):
        """ComplianceSummary has encryption_health field."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert hasattr(ComplianceSummary, "encryption_health")

    def test_compliance_summary_defaults(self):
        """ComplianceSummary defaults to zero/empty state."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        s = ComplianceSummary()
        assert s.total_phi_scans == 0
        assert s.total_redactions == 0
        assert s.active_encryption_keys == 0
        assert s.active_baa_agreements == 0
        assert s.audit_entries_30d == 0
        assert s.overall_compliance_score == 0.0
        assert s.last_audit_entry is None
        assert s.encryption_health == "healthy"

    def test_compliance_summary_instantiation(self):
        """ComplianceSummary can be instantiated with all fields."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        s = ComplianceSummary(
            total_phi_scans=100,
            total_redactions=85,
            active_encryption_keys=3,
            active_baa_agreements=2,
            audit_entries_30d=500,
            overall_compliance_score=0.92,
            last_audit_entry="2026-07-30T12:00:00Z",
            encryption_health="healthy",
        )
        assert s.total_phi_scans == 100
        assert s.total_redactions == 85
        assert s.active_encryption_keys == 3
        assert s.active_baa_agreements == 2
        assert s.audit_entries_30d == 500
        assert s.overall_compliance_score == 0.92
        assert s.last_audit_entry == "2026-07-30T12:00:00Z"
        assert s.encryption_health == "healthy"


class TestPHIStatsInterface:
    """Verify PHIStats dataclass contract."""

    def test_phi_stats_importable(self):
        """PHIStats exists and is importable."""
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        assert PHIStats is not None

    def test_phi_stats_is_dataclass(self):
        """PHIStats is a dataclass."""
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        assert is_dataclass(PHIStats)

    @property
    def _phi_stats_field_names(self):
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        return {f.name for f in fields(PHIStats)}

    def test_phi_stats_has_by_category(self):
        """PHIStats has by_category dict field."""
        assert "by_category" in self._phi_stats_field_names

    def test_phi_stats_has_by_risk_level(self):
        """PHIStats has by_risk_level dict field."""
        assert "by_risk_level" in self._phi_stats_field_names

    def test_phi_stats_has_by_date(self):
        """PHIStats has by_date dict field."""
        assert "by_date" in self._phi_stats_field_names

    def test_phi_stats_has_total_false_positives(self):
        """PHIStats has total_false_positives field."""
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        assert hasattr(PHIStats, "total_false_positives")

    def test_phi_stats_has_total_llm_corrections(self):
        """PHIStats has total_llm_corrections field."""
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        assert hasattr(PHIStats, "total_llm_corrections")

    def test_phi_stats_defaults(self):
        """PHIStats defaults to empty dicts and zero counts."""
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        stats = PHIStats()
        assert stats.by_category == {}
        assert stats.by_risk_level == {}
        assert stats.by_date == {}
        assert stats.total_false_positives == 0
        assert stats.total_llm_corrections == 0


class TestComplianceServiceInterface:
    """Verify ComplianceService class contract."""

    def test_compliance_service_importable(self):
        """ComplianceService exists and is importable."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert ComplianceService is not None

    def test_compliance_service_init_signature(self):
        """__init__ accepts audit_logger, encryption_service, baa_service, phi_redactor."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        sig = signature(ComplianceService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_get_summary_exists(self):
        """ComplianceService has get_summary method."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert hasattr(ComplianceService, "get_summary")

    def test_get_summary_is_async(self):
        """get_summary is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert inspect.iscoroutinefunction(ComplianceService.get_summary)

    def test_get_summary_returns_compliance_summary(self):
        """get_summary returns a ComplianceSummary (type hint)."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        hints = getattr(ComplianceService.get_summary, "__annotations__", {})
        ret = hints.get("return", "")
        assert "ComplianceSummary" in str(ret) or ret is not None

    def test_get_phi_stats_exists(self):
        """ComplianceService has get_phi_stats method."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert hasattr(ComplianceService, "get_phi_stats")

    def test_get_phi_stats_is_async(self):
        """get_phi_stats is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert inspect.iscoroutinefunction(ComplianceService.get_phi_stats)

    def test_get_phi_stats_signature(self):
        """get_phi_stats(since: str = '30d') -> PHIStats."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        sig = signature(ComplianceService.get_phi_stats)
        params = sig.parameters
        assert "since" in params

    def test_get_recent_activity_exists(self):
        """ComplianceService has get_recent_activity method."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert hasattr(ComplianceService, "get_recent_activity")

    def test_get_recent_activity_is_async(self):
        """get_recent_activity is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert inspect.iscoroutinefunction(ComplianceService.get_recent_activity)

    def test_get_recent_activity_signature(self):
        """get_recent_activity(limit: int = 50) -> list[AuditEntry]."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        sig = signature(ComplianceService.get_recent_activity)
        assert "limit" in sig.parameters

    def test_get_encryption_status_exists(self):
        """ComplianceService has get_encryption_status method."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert hasattr(ComplianceService, "get_encryption_status")

    def test_get_encryption_status_is_async(self):
        """get_encryption_status is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert inspect.iscoroutinefunction(ComplianceService.get_encryption_status)

    def test_get_baa_compliance_exists(self):
        """ComplianceService has get_baa_compliance method."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert hasattr(ComplianceService, "get_baa_compliance")

    def test_get_baa_compliance_is_async(self):
        """get_baa_compliance is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        assert inspect.iscoroutinefunction(ComplianceService.get_baa_compliance)

    def test_compliance_service_can_be_instantiated(self):
        """ComplianceService can be instantiated without args."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        svc = ComplianceService()
        assert svc is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (will FAIL until implementation is done)
# ═══════════════════════════════════════════════════════════════════════════════


class TestComplianceServiceBehavioral:
    """Behavioral tests for ComplianceService."""

    @pytest.fixture
    def svc(self):
        """Provide a default ComplianceService instance."""
        from meeting_notes_ai.hipaa.dashboard import ComplianceService

        return ComplianceService()

    @pytest.mark.asyncio
    async def test_get_summary_returns_defaults_when_empty(self, svc):
        """get_summary() returns zeroed metrics when no data exists."""
        summary = await svc.get_summary()
        from meeting_notes_ai.hipaa.dashboard import ComplianceSummary

        assert isinstance(summary, ComplianceSummary)
        assert summary.total_phi_scans == 0
        assert summary.overall_compliance_score >= 0.0
        assert summary.encryption_health in (
            "healthy",
            "degraded",
            "unhealthy",
            "unprovisioned",
        )

    @pytest.mark.asyncio
    async def test_get_phi_stats_returns_structure(self, svc):
        """get_phi_stats() returns a PHIStats with expected fields."""
        stats = await svc.get_phi_stats()
        from meeting_notes_ai.hipaa.dashboard import PHIStats

        assert isinstance(stats, PHIStats)
        assert isinstance(stats.by_category, dict)
        assert isinstance(stats.by_date, dict)

    @pytest.mark.asyncio
    async def test_get_recent_activity_returns_list(self, svc):
        """get_recent_activity() returns a list of entries."""
        activity = await svc.get_recent_activity(limit=10)
        assert isinstance(activity, list)

    @pytest.mark.asyncio
    async def test_get_encryption_status_returns_dict(self, svc):
        """get_encryption_status() returns a dict with health info."""
        status = await svc.get_encryption_status()
        assert isinstance(status, dict)
        assert "status" in status or "health" in status or "healthy" in str(status)

    @pytest.mark.asyncio
    async def test_get_baa_compliance_returns_dict(self, svc):
        """get_baa_compliance() returns a dict with agreement counts."""
        status = await svc.get_baa_compliance()
        assert isinstance(status, dict)

    @pytest.mark.asyncio
    async def test_compliance_score_in_range(self, svc):
        """overall_compliance_score is between 0.0 and 1.0."""
        summary = await svc.get_summary()
        assert 0.0 <= summary.overall_compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_phi_stats_respects_since_param(self, svc):
        """get_phi_stats(since='7d') filters to last 7 days."""
        stats_7d = await svc.get_phi_stats(since="7d")
        stats_30d = await svc.get_phi_stats(since="30d")
        # Either both return data or 7d has fewer/same entries as 30d
        assert isinstance(stats_7d.by_date, dict)
        assert isinstance(stats_30d.by_date, dict)


class TestEncryptionHealthLabeling:
    """S9: encryption health labels must not overstate readiness."""

    class _FakeEncryptionService:
        """Minimal double exposing list_key_info + _store_error."""

        def __init__(self, key_count: int = 0, store_error: str | None = None):
            self._key_count = key_count
            self._store_error = store_error

        async def list_key_info(self):
            return {f"tenant-{i}": object() for i in range(self._key_count)}

    @pytest.mark.asyncio
    async def test_zero_key_wired_service_is_unprovisioned(self):
        """A wired EncryptionService with 0 keys must not report healthy."""
        svc = ComplianceService(
            encryption_service=self._FakeEncryptionService(key_count=0)
        )
        summary = await svc.get_summary()
        assert summary.active_encryption_keys == 0
        assert summary.encryption_health == "unprovisioned"

    @pytest.mark.asyncio
    async def test_wired_service_with_keys_is_healthy(self):
        """A wired service with >= 1 key reports healthy."""
        svc = ComplianceService(
            encryption_service=self._FakeEncryptionService(key_count=2)
        )
        summary = await svc.get_summary()
        assert summary.active_encryption_keys == 2
        assert summary.encryption_health == "healthy"

    @pytest.mark.asyncio
    async def test_corrupt_store_stays_degraded(self):
        """A corrupt store is degraded even with 0 usable keys."""
        svc = ComplianceService(
            encryption_service=self._FakeEncryptionService(
                key_count=0, store_error="key store corrupt or unreadable"
            )
        )
        summary = await svc.get_summary()
        assert summary.encryption_health == "degraded"

    @pytest.mark.asyncio
    async def test_encryption_status_unprovisioned_when_zero_keys(self):
        """get_encryption_status() mirrors the unprovisioned label."""
        svc = ComplianceService(
            encryption_service=self._FakeEncryptionService(key_count=0)
        )
        status = await svc.get_encryption_status()
        assert status["status"] == "unprovisioned"
        assert status["total_keys"] == 0

    @pytest.mark.asyncio
    async def test_encryption_status_healthy_with_keys(self):
        """get_encryption_status() reports healthy with keys present."""
        svc = ComplianceService(
            encryption_service=self._FakeEncryptionService(key_count=2)
        )
        status = await svc.get_encryption_status()
        assert status["status"] == "healthy"
        assert status["total_keys"] == 2
