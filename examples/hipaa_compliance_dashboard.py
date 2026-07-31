#!/usr/bin/env python3
"""Compliance dashboard example — aggregate HIPAA metrics across modules.

Uses the library API:

    from meeting_notes_ai.hipaa.dashboard import ComplianceService

Wire the audit logger, encryption service, BAA service, and PHI redactor
into a ComplianceService to get the same summary the compliance dashboard
renders.

Run from the repository root:

    HIPAA_MASTER_KEY=dev-master-key PYTHONPATH=src .venv/bin/python \
        examples/hipaa_compliance_dashboard.py
"""

import asyncio
import os
import tempfile
from pathlib import Path

from meeting_notes_ai.hipaa.audit_logger import AuditEntry, AuditLogger
from meeting_notes_ai.hipaa.baa import BAAService
from meeting_notes_ai.hipaa.config import HIPAAConfig
from meeting_notes_ai.hipaa.dashboard import ComplianceService
from meeting_notes_ai.hipaa.encryption import EncryptionService
from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor


async def main() -> None:
    if not os.environ.get("HIPAA_MASTER_KEY"):
        raise SystemExit("set HIPAA_MASTER_KEY first (e.g. HIPAA_MASTER_KEY=dev-master-key)")

    # ── Build each module with real data ────────────────────────────────────
    redactor = PHIRedactor()
    redactor.scan("Patient John Smith, SSN 123-45-6789, DOB 03/14/1985, 555-123-4567")

    audit_logger = AuditLogger(
        config=HIPAAConfig(audit_log_dir=tempfile.mkdtemp(prefix="hipaa-audit-"))
    )
    await audit_logger.log(
        AuditEntry(
            timestamp="2026-07-31T08:00:00Z",
            actor="user-42",
            action="phi.redact",
            resource="meeting:abc-123",
            phi_classification="high",
        )
    )

    encryption = EncryptionService(config=HIPAAConfig())
    await encryption.generate_tenant_key("tenant-1")

    # File-backed store (0600 + atomic writes) so agreements survive
    # restarts — same location convention as EncryptionService's key store.
    baa = BAAService(
        store_path=Path.home() / ".meeting-notes-ai" / "baa_agreements.json"
    )
    await baa.store_agreement("Acme Health Systems", "CloudNotes Inc.", "Dr. Jane Smith")

    # ── Aggregate ───────────────────────────────────────────────────────────
    compliance = ComplianceService(
        audit_logger=audit_logger,
        encryption_service=encryption,
        baa_service=baa,
        phi_redactor=redactor,
    )

    print("== Summary ==")
    summary = await compliance.get_summary()
    print(f"  phi scans (matches seen) : {summary.total_phi_scans}")
    print(f"  redactions               : {summary.total_redactions}")
    print(f"  encryption keys          : {summary.active_encryption_keys}")
    print(f"  active BAA agreements    : {summary.active_baa_agreements}")
    print(f"  audit entries            : {summary.audit_entries_30d}")
    print(f"  compliance score         : {summary.overall_compliance_score:.2f}")
    print(f"  encryption health        : {summary.encryption_health}")

    print("\n== PHI stats (chart data) ==")
    phi_stats = await compliance.get_phi_stats()
    print(f"  by category : {phi_stats.by_category}")
    print(f"  by risk     : {phi_stats.by_risk_level}")

    print("\n== Recent activity ==")
    for entry in await compliance.get_recent_activity(limit=5):
        print(f"  {entry}")


if __name__ == "__main__":
    asyncio.run(main())
