#!/usr/bin/env python3
"""Audit logging example — write, query, summarize, rotate, and export.

Uses the library API:

    from meeting_notes_ai.hipaa.audit_logger import AuditLogger, AuditEntry

Run from the repository root:

    PYTHONPATH=src .venv/bin/python examples/hipaa_audit_logs.py
"""

import asyncio
import tempfile

from meeting_notes_ai.hipaa.audit_logger import AuditEntry, AuditLogger
from meeting_notes_ai.hipaa.config import HIPAAConfig


async def main() -> None:
    # Use a temp dir so the example never touches the production log store.
    log_dir = tempfile.mkdtemp(prefix="hipaa-audit-")
    logger = AuditLogger(config=HIPAAConfig(audit_log_dir=log_dir))

    await logger.log(
        AuditEntry(
            timestamp="2026-07-31T08:00:00Z",
            actor="user-42",
            action="phi.redact",
            resource="meeting:abc-123",
            phi_classification="high",
            outcome="success",
            ip_address="10.0.0.1",
        )
    )
    await logger.log(
        AuditEntry(
            timestamp="2026-07-31T08:05:00Z",
            actor="user-7",
            action="phi.scan",
            resource="meeting:def-456",
            phi_classification="medium",
            outcome="success",
        )
    )

    print("== Query (all) ==")
    for e in await logger.query(limit=10):
        print(f"  {e.timestamp} {e.actor:8s} {e.action:10s} {e.resource} [{e.outcome}]")

    print("\n== Query (filtered by actor) ==")
    for e in await logger.query(filters={"actor": "user-42"}):
        print(f"  {e.action} on {e.resource}")

    print("\n== Stats ==")
    print(f"  {await logger.get_stats()}")

    print("\n== Rotate (archive current file) ==")
    print(f"  archived -> {await logger.rotate()}")

    print("\n== Export date range ==")
    print(f"  export -> {await logger.export_range('2026-07-01', '2026-12-31')}")


if __name__ == "__main__":
    asyncio.run(main())
