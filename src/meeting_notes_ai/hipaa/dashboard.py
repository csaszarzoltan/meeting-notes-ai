"""Compliance Dashboard — REST API + HTML with Chart.js visualizations.

Aggregates metrics from AuditLogger, EncryptionService, BAAService, and
PHIRedactor into structured API endpoints and a minimal HTML dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

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
        audit_logger: Callable | None = None,
        encryption_service: Callable | None = None,
        baa_service: Callable | None = None,
        phi_redactor: Callable | None = None,
    ) -> None:
        """Initialize with references to all HIPAA services.

        Args:
            audit_logger: AuditLogger instance for querying audit entries.
            encryption_service: EncryptionService for key status.
            baa_service: BAAService for agreement listings.
            phi_redactor: PHIRedactor for redaction statistics.
        """
        self._audit_logger = audit_logger
        self._encryption_service = encryption_service
        self._baa_service = baa_service
        self._phi_redactor = phi_redactor
        raise NotImplementedError("ComplianceService.__init__")

    async def get_summary(self) -> ComplianceSummary:
        """Aggregate overall compliance summary across all modules.

        Returns:
            ComplianceSummary with all fields populated from live data.
        """
        raise NotImplementedError("ComplianceService.get_summary")

    async def get_phi_stats(self, since: str = "30d") -> PHIStats:
        """Get PHI detection statistics for charting.

        Args:
            since: Time range filter (e.g. '30d', '7d', '90d', 'all').

        Returns:
            PHIStats with counts by category, risk level, and date.
        """
        raise NotImplementedError("ComplianceService.get_phi_stats")

    async def get_recent_activity(self, limit: int = 50) -> list[dict]:
        """Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of audit entry dicts (timestamp, actor, action, resource, outcome).
        """
        raise NotImplementedError("ComplianceService.get_recent_activity")

    async def get_encryption_status(self) -> dict:
        """Get encryption key health summary.

        Returns:
            Dict with keys: total_keys, active_keys, healthy, last_rotation.
        """
        raise NotImplementedError("ComplianceService.get_encryption_status")

    async def get_baa_compliance(self) -> dict:
        """Get BAA compliance status.

        Returns:
            Dict with keys: total_agreements, active, expired, terminated.
        """
        raise NotImplementedError("ComplianceService.get_baa_compliance")
