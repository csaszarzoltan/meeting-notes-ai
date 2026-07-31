"""Append-only audit logging module.

Writes immutable JSONL audit entries to the filesystem with automatic
rotation and HIPAA-mandated tracking fields.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meeting_notes_ai.hipaa.config import HIPAAConfig


@dataclass
class AuditEntry:
    """A single HIPAA audit log entry — immutable after write."""

    timestamp: str = ""
    actor: str = ""
    action: str = ""
    resource: str = ""
    phi_classification: str = "none"
    details: dict[str, Any] = field(default_factory=dict)
    outcome: str = "success"
    ip_address: str = ""
    user_agent: str = ""


class AuditLogger:
    """Append-only JSONL audit logger.

    Writes HIPAA-compliant audit entries to a rotating JSONL file. Every
    entry captures who, what, when, where, and outcome.
    """

    def __init__(self, config: HIPAAConfig | None = None) -> None:
        """Initialise logger with optional HIPAAConfig."""
        self.config = config or HIPAAConfig()
        self._lock = asyncio.Lock()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_log_dir(self) -> Path:
        """Return the audit log directory, creating it if needed."""
        log_dir = Path(self.config.audit_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _current_log_path(self) -> Path:
        """Return the path to the current active log file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._get_log_dir() / f"audit-{today}.jsonl"

    def _read_all(self) -> list[AuditEntry]:
        """Read all entries from the current active JSONL file."""
        entries: list[AuditEntry] = []
        current = self._current_log_path()
        if current.exists():
            try:
                with open(current) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            entries.append(AuditEntry(**data))
                        except (json.JSONDecodeError, TypeError):
                            pass
            except OSError:
                pass
        return entries

    # ── Logging ────────────────────────────────────────────────────────────────

    async def log(self, entry: AuditEntry) -> None:
        """Persist a single audit entry (append-only).

        Validates that HIPAA-mandatory fields (timestamp, actor, action,
        resource) are populated.
        """
        # Validate required fields
        missing = []
        if not entry.timestamp:
            missing.append("timestamp")
        if not entry.actor:
            missing.append("actor")
        if not entry.action:
            missing.append("action")
        if not entry.resource:
            missing.append("resource")
        if missing:
            raise ValueError(
                f"Missing required fields: {', '.join(missing)}"
            )

        async with self._lock:
            log_path = self._current_log_path()
            # Use a synchronous write in a thread executor to keep it simple
            loop = asyncio.get_running_loop()

            def _write() -> None:
                with open(log_path, "a") as f:
                    f.write(json.dumps(asdict(entry)) + "\n")

            await loop.run_in_executor(None, _write)

    # ── Query ──────────────────────────────────────────────────────────────────

    async def query(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters and limit."""
        loop = asyncio.get_running_loop()

        def _query() -> list[AuditEntry]:
            all_entries = self._read_all()
            if filters:
                filtered = []
                for e in all_entries:
                    match = True
                    for key, val in filters.items():
                        entry_val = getattr(e, key, None)
                        if entry_val is None or entry_val != val:
                            match = False
                            break
                    if match:
                        filtered.append(e)
                all_entries = filtered
            # Sort by timestamp descending (most recent first)
            all_entries.sort(key=lambda x: x.timestamp, reverse=True)
            return all_entries[:limit]

        return await loop.run_in_executor(None, _query)

    # ── Stats ──────────────────────────────────────────────────────────────────

    async def get_stats(self, since: str | None = None) -> dict[str, Any]:
        """Return aggregate statistics over audit entries."""
        loop = asyncio.get_running_loop()

        def _stats() -> dict[str, Any]:
            all_entries = self._read_all()

            if since:
                try:
                    since_dt = datetime.fromisoformat(since)
                    all_entries = [
                        e
                        for e in all_entries
                        if e.timestamp and e.timestamp >= since
                    ]
                except (ValueError, TypeError):
                    pass

            action_counts: dict[str, int] = {}
            actor_counts: dict[str, int] = {}
            outcome_counts: dict[str, int] = {}
            phi_counts: dict[str, int] = {}
            timestamps = [e.timestamp for e in all_entries if e.timestamp]
            timestamps.sort()

            for e in all_entries:
                action_counts[e.action] = action_counts.get(e.action, 0) + 1
                actor_counts[e.actor] = actor_counts.get(e.actor, 0) + 1
                outcome_counts[e.outcome] = (
                    outcome_counts.get(e.outcome, 0) + 1
                )
                phi_counts[e.phi_classification] = (
                    phi_counts.get(e.phi_classification, 0) + 1
                )

            return {
                "total_entries": len(all_entries),
                "unique_actors": len(actor_counts),
                "actions": action_counts,
                "actors": actor_counts,
                "outcomes": outcome_counts,
                "phi_classifications": phi_counts,
                "earliest": timestamps[0] if timestamps else None,
                "latest": timestamps[-1] if timestamps else None,
            }

        return await loop.run_in_executor(None, _stats)

    # ── Rotation ───────────────────────────────────────────────────────────────

    async def rotate(self) -> Path:
        """Force a manual log rotation. Returns path to the archived file."""
        loop = asyncio.get_running_loop()

        def _rotate() -> Path:
            current = self._current_log_path()
            if current.exists() and current.stat().st_size > 0:
                archive_name = (
                    f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                    f"-{uuid.uuid4().hex[:8]}.jsonl"
                )
                archive_path = self._get_log_dir() / archive_name
                current.rename(archive_path)
                return archive_path
            # Create empty archive if nothing to rotate
            archive_name = (
                f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                f"-{uuid.uuid4().hex[:8]}.jsonl"
            )
            archive_path = self._get_log_dir() / archive_name
            archive_path.touch()
            return archive_path

        return await loop.run_in_executor(None, _rotate)

    # ── Export ─────────────────────────────────────────────────────────────────

    async def export_range(self, start: str, end: str) -> Path:
        """Export audit entries within a date range. Returns export file path."""
        loop = asyncio.get_running_loop()

        def _export() -> Path:
            all_entries = self._read_all()
            filtered = [
                e
                for e in all_entries
                if e.timestamp and start <= e.timestamp <= end
            ]

            export_dir = self._get_log_dir() / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            export_path = (
                export_dir
                / f"audit-export-{start}-{end}-{uuid.uuid4().hex[:8]}.jsonl"
            )
            with open(export_path, "w") as f:
                for entry in filtered:
                    f.write(json.dumps(asdict(entry)) + "\n")

            return export_path

        return await loop.run_in_executor(None, _export)
