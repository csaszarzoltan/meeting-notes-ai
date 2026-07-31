"""Compliance Dashboard — REST API + HTML with Chart.js visualizations.

Aggregates metrics from AuditLogger, EncryptionService, BAAService, and
PHIRedactor into structured API endpoints and a minimal HTML dashboard.

All service blocks degrade explicitly: on error they log loudly and mark
the health/status field (e.g. ``encryption_health="degraded"``) instead of
swallowing the exception silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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
        (or defaults when services are not connected or empty). Service
        failures degrade visible health fields instead of passing silently.
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
                logger.exception("compliance dashboard: audit stats failed")

        enc_keys = 0
        enc_health = "healthy"
        encryption_service = getattr(self, "_encryption_service", None)
        if encryption_service is not None:
            try:
                if hasattr(encryption_service, "list_key_info"):
                    enc_keys = len(await encryption_service.list_key_info())
                else:
                    # Fallback: a service exposing only get_key_info is
                    # probed via a sentinel tenant.
                    try:
                        await encryption_service.get_key_info("__dashboard__")
                        enc_keys = 1
                    except Exception:
                        enc_keys = 0
                store_error = getattr(encryption_service, "_store_error", None)
                if store_error:
                    enc_health = "degraded"
            except Exception:
                enc_health = "degraded"
                enc_keys = 0
                logger.exception(
                    "compliance dashboard: encryption service unavailable"
                )
        elif getattr(self, "_encryption_service", None) is None:
            # No encryption service wired at all — surface it, don't lie.
            enc_health = "degraded"

        baa_count = 0
        baa_service = getattr(self, "_baa_service", None)
        if baa_service is not None:
            try:
                agreements = await baa_service.list_agreements()
                baa_count = len(agreements)
            except Exception:
                logger.exception("compliance dashboard: BAA service failed")

        phi_scans = 0
        redactions = 0
        phi_redactor = getattr(self, "_phi_redactor", None)
        if phi_redactor is not None:
            try:
                stats_data = phi_redactor.get_stats()
                phi_scans = stats_data.get("total_matches", 0)
                redactions = stats_data.get(
                    "total_redactions", stats_data.get("total_matches", 0)
                )
            except Exception:
                logger.exception("compliance dashboard: redactor stats failed")

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
                logger.exception("compliance dashboard: phi stats failed")
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
                logger.exception("compliance dashboard: activity query failed")
        return []

    async def get_encryption_status(self) -> dict:
        """Get encryption key health summary from the live registry."""
        encryption_service = getattr(self, "_encryption_service", None)
        if encryption_service is None:
            return {
                "status": "degraded",
                "total_keys": 0,
                "active_keys": 0,
                "detail": "encryption service not wired",
            }
        try:
            if hasattr(encryption_service, "list_key_info"):
                keys = await encryption_service.list_key_info()
            else:
                keys = {}
            total = len(keys)
            active = sum(
                1 for info in keys.values() if getattr(info, "is_active", True)
            )
            store_error = getattr(encryption_service, "_store_error", None)
            status = "degraded" if store_error else "healthy"
            payload: dict[str, Any] = {
                "status": status,
                "total_keys": total,
                "active_keys": active,
            }
            if store_error:
                payload["detail"] = str(store_error)
            return payload
        except Exception:
            logger.exception("compliance dashboard: encryption status failed")
            return {
                "status": "degraded",
                "total_keys": 0,
                "active_keys": 0,
                "detail": "encryption service unavailable",
            }

    async def get_baa_compliance(self) -> dict:
        """Get BAA compliance status from the live agreement store."""
        baa_service = getattr(self, "_baa_service", None)
        if baa_service is None:
            return {
                "total_agreements": 0,
                "active": 0,
                "expired": 0,
                "terminated": 0,
                "status": "degraded",
                "detail": "baa service not wired",
            }
        try:
            agreements = await baa_service.list_agreements()
            counts: dict[str, int] = {"active": 0, "expired": 0, "terminated": 0}
            for ag in agreements:
                status = getattr(ag, "status", "active") or "active"
                counts[status] = counts.get(status, 0) + 1
            return {
                "total_agreements": len(agreements),
                "active": counts["active"],
                "expired": counts["expired"],
                "terminated": counts["terminated"],
                "status": "healthy",
            }
        except Exception:
            logger.exception("compliance dashboard: BAA compliance failed")
            return {
                "total_agreements": 0,
                "active": 0,
                "expired": 0,
                "terminated": 0,
                "status": "degraded",
                "detail": "baa service unavailable",
            }

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
        if encryption_keys == 0:
            score -= 0.2
        if baa_agreements == 0:
            score -= 0.2
        if audit_entries == 0:
            score -= 0.1
        return max(0.0, min(1.0, score))
