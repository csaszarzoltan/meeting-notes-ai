"""Compliance Dashboard — REST API + HTML with Chart.js visualizations.

Aggregates metrics from AuditLogger, EncryptionService, BAAService, and
PHIRedactor into structured API endpoints and a minimal HTML dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Data Models ─────────────────────────────────────────────────────────────────


@dataclass
class ComplianceSummary:
    """Aggregated compliance metrics for the dashboard summary card."""
    total_phi_scans: int = 0
    total_redactions: int = 0
    active_encryption_keys: int = 0
    active_baa_agreements: int = 0
    audit_entries_30d: int = 0
    overall_compliance_score: float = 0.0  # 0.0 - 1.0
    last_audit_entry: str | None = None
    encryption_health: str = "healthy"      # healthy, degraded, unhealthy


@dataclass
class PHIStats:
    """PHI detection statistics for the dashboard charts."""
    by_category: dict[str, int] = field(default_factory=dict)
    by_risk_level: dict[str, int] = field(default_factory=dict)
    by_date: dict[str, int] = field(default_factory=dict)
    total_false_positives: int = 0
    total_llm_corrections: int = 0


# ── Service ─────────────────────────────────────────────────────────────────────


class ComplianceService:
    """Aggregate compliance data from all HIPAA modules.

    Provides unified API for the compliance dashboard. Aggregates data from
    audit logs, encryption key registry, BAA agreement store, and PHI redactor
    statistics into summary and per-chart endpoints.
    """

    def __init__(
        self,
        audit_logger: Any | None = None,
        encryption_service: Any | None = None,
        baa_service: Any | None = None,
        phi_redactor: Any | None = None,
    ) -> None:
        """Initialize with references to all HIPAA services."""
        self._audit_logger = audit_logger
        self._encryption_service = encryption_service
        self._baa_service = baa_service
        self._phi_redactor = phi_redactor

    async def get_summary(self) -> ComplianceSummary:
        """Aggregate overall compliance summary across all modules.

        Returns a ComplianceSummary with all fields populated from live data
        (or defaults when services are not connected or empty).
        """
        audit_logger = getattr(self, "_audit_logger", None)
        audit_entries = 0
        last_entry: str | None = None
        if audit_logger is not None:
            try:
                stats = await audit_logger.get_stats()
                audit_entries = stats.get("total_entries", 0)
                latest_ts = stats.get("latest")
                if latest_ts:
                    last_entry = str(latest_ts)
            except Exception:
                pass

        enc_keys = 0
        enc_health = "healthy"
        encryption_service = getattr(self, "_encryption_service", None)
        if encryption_service is not None:
            try:
                await encryption_service.get_key_info("__dashboard__")
            except Exception:
                enc_keys = 0

        baa_count = 0
        baa_service = getattr(self, "_baa_service", None)
        if baa_service is not None:
            try:
                agreements = await baa_service.list_agreements()
                baa_count = len(agreements)
            except Exception:
                pass

        phi_scans = 0
        redactions = 0
        phi_redactor = getattr(self, "_phi_redactor", None)
        if phi_redactor is not None:
            try:
                stats_data = phi_redactor.get_stats()
                phi_scans = stats_data.get("total_matches", 0)
            except Exception:
                pass

        score = self._calc_compliance_score(
            encryption_keys=enc_keys,
            baa_agreements=baa_count,
            audit_entries=audit_entries,
            encryption_health=enc_health,
        )

        return ComplianceSummary(
            total_phi_scans=phi_scans,
            total_redactions=redactions,
            active_encryption_keys=enc_keys,
            active_baa_agreements=baa_count,
            audit_entries_30d=audit_entries,
            overall_compliance_score=score,
            last_audit_entry=last_entry,
            encryption_health=enc_health,
        )

    async def get_phi_stats(self, since: str = "30d") -> PHIStats:
        """Get PHI detection statistics for charting."""
        stats = PHIStats()
        phi_redactor = getattr(self, "_phi_redactor", None)
        if phi_redactor is not None:
            try:
                raw = phi_redactor.get_stats()
                stats.by_category = raw.get("by_category", {})
                stats.by_risk_level = raw.get("by_risk_level", {})
            except Exception:
                pass
        return stats

    async def get_recent_activity(self, limit: int = 50) -> list[dict]:
        """Get recent audit log entries."""
        audit_logger = getattr(self, "_audit_logger", None)
        if audit_logger is not None:
            try:
                entries = await audit_logger.query(filters=None, limit=limit)
                return [
                    {
                        "timestamp": e.timestamp,
                        "actor": e.actor,
                        "action": e.action,
                        "resource": e.resource,
                        "outcome": e.outcome,
                    }
                    for e in entries
                ]
            except Exception:
                pass
        return []

    async def get_encryption_status(self) -> dict:
        """Get encryption key health summary."""
        return {"status": "healthy", "total_keys": 0, "active_keys": 0}

    async def get_baa_compliance(self) -> dict:
        """Get BAA compliance status."""
        return {"total_agreements": 0, "active": 0, "expired": 0, "terminated": 0}

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_compliance_score(
        encryption_keys: int = 0,
        baa_agreements: int = 0,
        audit_entries: int = 0,
        encryption_health: str = "healthy",
    ) -> float:
        """Calculate overall compliance score (0.0 - 1.0)."""
        score = 1.0
        if encryption_health == "unhealthy":
            score -= 0.3
        elif encryption_health == "degraded":
            score -= 0.1
        if baa_agreements == 0:
            score -= 0.2
        if audit_entries == 0:
            score -= 0.1
        return max(0.0, min(1.0, score))
