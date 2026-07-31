"""Append-only audit logging module.

Writes immutable JSONL audit entries to the filesystem with automatic
rotation and HIPAA-mandated tracking fields.

Integrity model (B3): every line carries a ``_chain`` record with the
previous line's hash and a SHA-256 hash over the canonical serialization
of the entry. Each log file is an independent hash chain (first entry
chains from a genesis hash); ``fsync`` on every write and ``0600``
permissions make the trail durable and private. Rotated/archived files
(matched via ``audit-*.jsonl``) remain queryable, and corrupt or
tampered lines are counted and surfaced instead of silently dropped.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meeting_notes_ai.hipaa.config import HIPAAConfig

logger = logging.getLogger(__name__)

# Genesis hash anchoring the start of every file's chain.
_GENESIS_HASH = "0" * 64

# Plaintext PHI guard for AuditEntry.details (S8): refuse to write obvious
# PHI (US SSNs) into the audit trail unredacted.
_PHI_DETAILS_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


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


def _canonical(data: dict[str, Any]) -> str:
    """Deterministic serialization used as the hash-chain input.

    Byte-stable regardless of key insertion order, so the hash computed
    at write time can be re-verified after a JSON round-trip on read.
    """
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _chain_hash(prev_hash: str, data: dict[str, Any]) -> str:
    """SHA-256 of ``prev_hash + canonical(entry)``."""
    return hashlib.sha256(
        (prev_hash + _canonical(data)).encode("utf-8")
    ).hexdigest()


class AuditLogger:
    """Append-only JSONL audit logger.

    Writes HIPAA-compliant audit entries to a rotating JSONL file. Every
    entry captures who, what, when, where, and outcome. Lines are hash
    chained (SHA-256), fsynced, and stored with 0600 permissions.
    """

    def __init__(self, config: HIPAAConfig | None = None) -> None:
        """Initialise logger with optional HIPAAConfig."""
        self.config = config or HIPAAConfig()
        self._lock = asyncio.Lock()
        self._instance_id = uuid.uuid4().hex[:8]
        self._last_chain_head: str | None = None
        self._last_read_stats: dict[str, int] = {
            "corrupt_lines": 0,
            "tampered_lines": 0,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_log_dir(self) -> Path:
        """Return the audit log directory, creating it if needed."""
        log_dir = Path(self.config.audit_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _current_log_path(self) -> Path:
        """Return the path to the current active log file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._get_log_dir() / f"audit-{today}-{self._instance_id}.jsonl"

    @staticmethod
    def _tail_chain_hash(path: Path) -> str | None:
        """Return the ``_chain.hash`` of the last non-empty line, if any.

        Used to continue the hash chain when appending to an existing
        file (e.g. a second AuditLogger instance sharing the same file).
        """
        try:
            with open(path, encoding="utf-8") as f:
                last_line = None
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
                if last_line is None:
                    return None
                data = json.loads(last_line)
                chain = data.get("_chain") if isinstance(data, dict) else None
                if isinstance(chain, dict) and isinstance(chain.get("hash"), str):
                    return chain["hash"]
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        return None

    def _read_all(self) -> tuple[list[AuditEntry], int, int]:
        """Read every entry from all ``audit-*.jsonl`` files (incl. rotated).

        Returns ``(entries, corrupt_lines, tampered_lines)``. Corrupt
        lines (unparseable JSON) and tampered lines (hash-chain mismatch)
        are counted and reported, never silently dropped.
        """
        entries: list[AuditEntry] = []
        corrupt = 0
        tampered = 0
        log_dir = self._get_log_dir()
        files = sorted(
            p for p in log_dir.glob("audit-*.jsonl") if p.is_file()
        )
        for path in files:
            prev_hash = _GENESIS_HASH
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except (json.JSONDecodeError, TypeError):
                            corrupt += 1
                            continue
                        if not isinstance(data, dict):
                            corrupt += 1
                            continue
                        chain = data.pop("_chain", None)
                        try:
                            entry = AuditEntry(**data)
                        except TypeError:
                            corrupt += 1
                            continue
                        if isinstance(chain, dict) and isinstance(
                            chain.get("hash"), str
                        ):
                            # Verify the per-file hash chain.
                            computed = _chain_hash(
                                chain.get("prev", ""), data
                            )
                            if (
                                chain.get("prev") == prev_hash
                                and computed == chain["hash"]
                            ):
                                prev_hash = chain["hash"]
                            else:
                                tampered += 1
                                continue
                        # Legacy lines without a _chain record are accepted
                        # but do not advance the chain.
                        entries.append(entry)
            except OSError as exc:
                logger.warning(
                    "audit log read failed for %s: %s", path, exc
                )
        self._last_read_stats = {
            "corrupt_lines": corrupt,
            "tampered_lines": tampered,
        }
        if corrupt or tampered:
            logger.warning(
                "audit log integrity: %d corrupt line(s), %d tampered "
                "line(s) in %s",
                corrupt,
                tampered,
                log_dir,
            )
        return entries, corrupt, tampered

    # ── Logging ────────────────────────────────────────────────────────────────

    async def log(self, entry: AuditEntry) -> None:
        """Persist a single audit entry (append-only).

        Validates that HIPAA-mandatory fields (timestamp, actor, action,
        resource) are populated and that ``details`` does not carry
        plaintext PHI (S8). The line is hash-chained, fsynced, and the
        file is chmod'ed 0600.
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

        # S8: never write plaintext PHI into the audit trail unredacted.
        if entry.details and _PHI_DETAILS_RE.search(str(entry.details)):
            raise ValueError(
                "AuditEntry.details must not contain plaintext PHI (SSN)"
            )

        async with self._lock:
            log_path = self._current_log_path()
            # Use a synchronous write in a thread executor to keep it simple
            loop = asyncio.get_running_loop()

            def _write() -> None:
                with open(log_path, "a", encoding="utf-8") as f:
                    prev_hash = self._tail_chain_hash(log_path) or _GENESIS_HASH
                    entry_data = asdict(entry)
                    record = dict(entry_data)
                    record["_chain"] = {
                        "prev": prev_hash,
                        "hash": _chain_hash(prev_hash, entry_data),
                    }
                    f.write(json.dumps(record) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                    os.chmod(log_path, 0o600)
                    self._last_chain_head = record["_chain"]["hash"]

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
            all_entries, _, _ = self._read_all()
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
            all_entries, corrupt, tampered = self._read_all()

            if since:
                try:
                    datetime.fromisoformat(since)
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
                "corrupt_lines": corrupt,
                "tampered_lines": tampered,
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
                os.chmod(archive_path, 0o600)
                return archive_path
            # Create empty archive if nothing to rotate
            archive_name = (
                f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                f"-{uuid.uuid4().hex[:8]}.jsonl"
            )
            archive_path = self._get_log_dir() / archive_name
            archive_path.touch()
            os.chmod(archive_path, 0o600)
            return archive_path

        return await loop.run_in_executor(None, _rotate)

    # ── Export ─────────────────────────────────────────────────────────────────

    async def export_range(self, start: str, end: str) -> Path:
        """Export audit entries within a date range. Returns export file path."""
        loop = asyncio.get_running_loop()

        def _export() -> Path:
            all_entries, _, _ = self._read_all()
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
            with open(export_path, "w", encoding="utf-8") as f:
                for entry in filtered:
                    f.write(json.dumps(asdict(entry)) + "\n")
            os.chmod(export_path, 0o600)

            return export_path

        return await loop.run_in_executor(None, _export)
