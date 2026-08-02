"""HIPAA retention engine for stored files.

Defines the retention policy resolution (1y / 3y / 7y / inherit), the
``expires_at`` computation, and :func:`sweep_expired` — the job that
deletes expired objects from the backend, soft-deletes their
``storage_files`` rows, and writes ``storage.expire`` audit entries.

The sweep runs as an asyncio background task started in the FastAPI
``lifespan`` (interval ``RETENTION_SWEEP_INTERVAL_SECONDS``) and can be
triggered manually via ``POST /api/v1/admin/retention/sweep``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from meeting_notes_ai.db.models import StoredFile

logger = logging.getLogger(__name__)

# HIPAA default retention: 6 years (repo convention, matches the audit
# log default of 365 * 6 days).
DEFAULT_RETENTION_DAYS = 2190

# Allowed explicit retention periods (1y / 3y / 7y) — enforced by the
# routes layer with Pydantic validation; None means "inherit" (default).
ALLOWED_RETENTION_DAYS = {365, 1095, 2555}

# Actor recorded for automated sweep audit entries (HIPAA "who" field).
_SWEEP_ACTOR = "system"


@dataclass
class RetentionPolicy:
    """A team's retention policy.

    Args:
        retention_days: Explicit retention in days (365/1095/2555) or None
            to inherit the global ``DEFAULT_RETENTION_DAYS``.
    """

    retention_days: int | None = None

    def effective_days(self) -> int:
        """Resolve the effective retention in days (inherit → default)."""
        return self.retention_days or DEFAULT_RETENTION_DAYS

    def compute_expires_at(self, now: datetime) -> datetime:
        """Return *now* + effective retention (timezone-aware)."""
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now + timedelta(days=self.effective_days())


@dataclass
class SweepResult:
    """Counts from a single retention sweep run."""

    expired: int = 0
    """StoredFile rows found with ``expires_at`` in the past."""
    deleted: int = 0
    """Rows whose object was deleted and row soft-deleted."""
    failed: int = 0
    """Rows where deletion or audit failed (kept for retry)."""

    def as_dict(self) -> dict[str, int]:
        """JSON-serializable view for the admin sweep endpoint."""
        return {"expired": self.expired, "deleted": self.deleted, "failed": self.failed}


async def sweep_expired(
    db: Any,
    storage: Any,
    audit: Any,
    now: datetime | None = None,
) -> SweepResult:
    """Delete expired stored files and record the sweep.

    Finds non-soft-deleted ``storage_files`` rows whose ``expires_at`` is
    in the past, deletes the object from *storage*, soft-deletes the row,
    and writes one ``storage.expire`` audit entry per deletion. Rows that
    fail to delete are counted in ``failed`` and left in place for the
    next sweep (so a transient backend outage never destroys metadata).

    Args:
        db: Async SQLAlchemy session.
        storage: ObjectStorageBackend-compatible backend.
        audit: AuditLogger-compatible logger (``.log(AuditEntry)``).
        now: Clock override (tests); defaults to ``datetime.now(timezone.utc)``.

    Returns:
        A :class:`SweepResult` with expired/deleted/failed counts.
    """
    now = now or datetime.now(timezone.utc)

    result = await db.execute(
        select(StoredFile).where(
            StoredFile.deleted_at.is_(None),
            StoredFile.expires_at.is_not(None),
            StoredFile.expires_at <= now,
        )
    )
    rows = list(result.scalars().all())

    sweep = SweepResult(expired=len(rows))
    for row in rows:
        try:
            await storage.delete(row.object_key)
            row.deleted_at = now
            await audit.log(
                _expire_entry(row, now)
            )
            sweep.deleted += 1
        except Exception:  # noqa: BLE001 — one bad file must not kill the sweep
            sweep.failed += 1
            logger.exception("retention sweep failed for object_key=%s", row.object_key)
    if rows:
        await db.flush()
    return sweep


def _expire_entry(row: StoredFile, now: datetime) -> Any:
    """Build the ``storage.expire`` AuditEntry for *row*."""
    from meeting_notes_ai.hipaa.audit_logger import AuditEntry

    return AuditEntry(
        timestamp=now.isoformat(),
        actor=_SWEEP_ACTOR,
        action="storage.expire",
        resource=row.object_key,
        phi_classification="phi" if row.content_type.startswith("audio/") else "none",
        outcome="success",
        details={
            "file_id": row.id,
            "meeting_id": row.meeting_id,
            "kind": row.kind.value if hasattr(row.kind, "value") else str(row.kind),
        },
    )


async def run_storage_sweep_forever(
    interval_seconds: int = 86400,
    storage: Any | None = None,
    audit: Any | None = None,
) -> None:
    """Background retention sweep loop for the app lifespan.

    Sleeps for one full interval *before* the first sweep so a freshly
    started app never deletes anything during startup, then sweeps on
    every interval. The loop is cancelled by the lifespan shutdown.
    """
    from meeting_notes_ai.db.session import get_db_session
    from meeting_notes_ai.hipaa.audit_logger import AuditLogger
    from meeting_notes_ai.storage.factory import get_storage_backend

    interval = max(interval_seconds, 1)
    await asyncio.sleep(interval)
    while True:
        try:
            backend = storage or get_storage_backend()
            logger_instance = audit or AuditLogger()
            async for session in get_db_session():
                await sweep_expired(db=session, storage=backend, audit=logger_instance)
                await session.flush()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive backend outages
            logger.exception("retention sweep cycle failed")
        await asyncio.sleep(interval)
