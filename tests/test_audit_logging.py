"""Pre-development interface and behavioral tests for Audit Logging.

Tests the AuditLogger and AuditEntry classes from the hipaa module.
Interface tests must pass immediately; behavioral tests will fail
(RED phase) until the implementation is completed.

Module under test:
  src/meeting_notes_ai/hipaa/audit_logger.py  — AuditEntry, AuditLogger
  src/meeting_notes_ai/hipaa/config.py        — HIPAAConfig
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from inspect import signature
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditEntryInterface:
    """Verify AuditEntry dataclass contract."""

    def test_audit_entry_importable(self):
        """AuditEntry exists and is importable."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert AuditEntry is not None

    def test_audit_entry_is_dataclass(self):
        """AuditEntry is a dataclass."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert is_dataclass(AuditEntry)

    @property
    def _audit_entry_field_names(self):
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        return {f.name for f in fields(AuditEntry)}

    def test_audit_entry_has_timestamp(self):
        """AuditEntry has timestamp field."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "timestamp")

    def test_audit_entry_has_actor(self):
        """AuditEntry has actor field (who)."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "actor")

    def test_audit_entry_has_action(self):
        """AuditEntry has action field (what)."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "action")

    def test_audit_entry_has_resource(self):
        """AuditEntry has resource field (where/what resource)."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "resource")

    def test_audit_entry_has_phi_classification(self):
        """AuditEntry has phi_classification field."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "phi_classification")

    def test_audit_entry_has_details(self):
        """AuditEntry has details dict field."""
        assert "details" in self._audit_entry_field_names

    def test_audit_entry_has_outcome(self):
        """AuditEntry has outcome field."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "outcome")

    def test_audit_entry_has_ip_address(self):
        """AuditEntry has ip_address field."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "ip_address")

    def test_audit_entry_has_user_agent(self):
        """AuditEntry has user_agent field."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        assert hasattr(AuditEntry, "user_agent")

    def test_audit_entry_defaults(self):
        """AuditEntry has sensible defaults."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        entry = AuditEntry()
        assert entry.timestamp == ""
        assert entry.actor == ""
        assert entry.action == ""
        assert entry.resource == ""
        assert entry.phi_classification == "none"
        assert entry.details == {}
        assert entry.outcome == "success"
        assert entry.ip_address == ""
        assert entry.user_agent == ""

    def test_audit_entry_instantiation(self):
        """AuditEntry can be instantiated with all fields."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        entry = AuditEntry(
            timestamp="2026-07-30T12:00:00Z",
            actor="user-42",
            action="phi.scan",
            resource="meeting:abc-123",
            phi_classification="high",
            details={"pattern_count": 3},
            outcome="success",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        assert entry.timestamp == "2026-07-30T12:00:00Z"
        assert entry.actor == "user-42"
        assert entry.action == "phi.scan"
        assert entry.resource == "meeting:abc-123"
        assert entry.phi_classification == "high"
        assert entry.details == {"pattern_count": 3}
        assert entry.outcome == "success"
        assert entry.ip_address == "192.168.1.1"
        assert entry.user_agent == "Mozilla/5.0"


class TestAuditLoggerInterface:
    """Verify AuditLogger class contract."""

    def test_audit_logger_importable(self):
        """AuditLogger exists and is importable."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert AuditLogger is not None

    def test_audit_logger_init_signature(self):
        """AuditLogger.__init__ accepts optional config."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        sig = signature(AuditLogger.__init__)
        assert "self" in sig.parameters

    def test_audit_logger_log_method_exists(self):
        """AuditLogger has a log method."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert hasattr(AuditLogger, "log")

    def test_audit_logger_log_is_async(self):
        """AuditLogger.log is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert inspect.iscoroutinefunction(AuditLogger.log)

    def test_audit_logger_log_signature(self):
        """log(entry: AuditEntry) -> None."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        sig = signature(AuditLogger.log)
        assert "entry" in sig.parameters

    def test_audit_logger_query_method_exists(self):
        """AuditLogger has a query method."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert hasattr(AuditLogger, "query")

    def test_audit_logger_query_is_async(self):
        """AuditLogger.query is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert inspect.iscoroutinefunction(AuditLogger.query)

    def test_audit_logger_query_signature(self):
        """query(filters: dict, limit: int = 100) -> list[AuditEntry]."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        sig = signature(AuditLogger.query)
        params = sig.parameters
        assert "filters" in params or "kwargs" in str(params)
        assert "limit" in params

    def test_audit_logger_get_stats_exists(self):
        """AuditLogger has a get_stats method."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert hasattr(AuditLogger, "get_stats")

    def test_audit_logger_get_stats_is_async(self):
        """AuditLogger.get_stats is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert inspect.iscoroutinefunction(AuditLogger.get_stats)

    def test_audit_logger_rotate_exists(self):
        """AuditLogger has a rotate method."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert hasattr(AuditLogger, "rotate")

    def test_audit_logger_rotate_is_async(self):
        """AuditLogger.rotate is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert inspect.iscoroutinefunction(AuditLogger.rotate)

    def test_audit_logger_export_range_exists(self):
        """AuditLogger has an export_range method."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert hasattr(AuditLogger, "export_range")

    def test_audit_logger_export_range_is_async(self):
        """AuditLogger.export_range is a coroutine function."""
        import inspect

        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        assert inspect.iscoroutinefunction(AuditLogger.export_range)

    def test_audit_logger_can_be_instantiated(self):
        """AuditLogger can be instantiated (with default config)."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        logger = AuditLogger()
        assert logger is not None

    def test_audit_logger_accepts_config(self):
        """AuditLogger accepts a HIPAAConfig instance."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        cfg = HIPAAConfig(audit_log_dir="/custom/logs/")
        logger = AuditLogger(config=cfg)
        assert logger is not None
        assert logger.config.audit_log_dir == "/custom/logs/"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (will FAIL until implementation is done)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditLoggerBehavioral:
    """Behavioral tests for AuditLogger."""

    @pytest.fixture
    def logger(self):
        """Provide a default AuditLogger instance."""
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        return AuditLogger()

    @pytest.fixture
    def sample_entry(self):
        """Provide a sample AuditEntry."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        return AuditEntry(
            timestamp="2026-07-30T12:00:00Z",
            actor="user-42",
            action="phi.scan",
            resource="meeting:abc-123",
            phi_classification="high",
            outcome="success",
        )

    @pytest.mark.asyncio
    async def test_log_writes_entry(self, logger, sample_entry, tmp_path):
        """log() writes an entry to the JSONL file."""
        await logger.log(sample_entry)
        # Verify the file exists and has content
        log_dir = Path(logger.config.audit_log_dir)
        # Should have at least one JSONL file
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) >= 1

    @pytest.mark.asyncio
    async def test_log_does_not_raise(self, logger, sample_entry):
        """log() accepts a valid AuditEntry without error."""
        await logger.log(sample_entry)

    @pytest.mark.asyncio
    async def test_log_validates_required_fields(self, logger):
        """log() validates that HIPAA-mandatory fields are populated."""
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        empty = AuditEntry()
        with pytest.raises(ValueError, match="timestamp|actor|action|resource"):
            await logger.log(empty)

    @pytest.mark.asyncio
    async def test_query_returns_filtered_results(self, logger, sample_entry):
        """query() with actor filter returns only matching entries."""
        await logger.log(sample_entry)
        from meeting_notes_ai.hipaa.audit_logger import AuditEntry

        other = AuditEntry(
            timestamp="2026-07-30T13:00:00Z",
            actor="user-99",
            action="encryption.key_generate",
            resource="tenant:xyz",
            phi_classification="none",
            outcome="success",
        )
        await logger.log(other)
        results = await logger.query(filters={"actor": "user-42"})
        assert all(e.actor == "user-42" for e in results)

    @pytest.mark.asyncio
    async def test_query_respects_limit(self, logger, sample_entry):
        """query() with a limit returns at most that many entries."""
        for i in range(5):
            from meeting_notes_ai.hipaa.audit_logger import AuditEntry

            await logger.log(
                AuditEntry(
                    timestamp=f"2026-07-30T{12+i:02d}:00:00Z",
                    actor=f"user-{i}",
                    action="test",
                    resource="test",
                    phi_classification="none",
                    outcome="success",
                )
            )
        results = await logger.query(limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_get_stats_returns_summary(self, logger, sample_entry):
        """get_stats() returns a dict with action counts, date range, etc."""
        await logger.log(sample_entry)
        stats = await logger.get_stats()
        assert isinstance(stats, dict)
        assert "total_entries" in stats or "count" in stats

    @pytest.mark.asyncio
    async def test_rotate_creates_archive(self, logger, sample_entry, tmp_path):
        """rotate() creates a timestamped archive file."""
        await logger.log(sample_entry)
        archive_path = await logger.rotate()
        assert archive_path.exists()

    @pytest.mark.asyncio
    async def test_export_range_returns_path(self, logger, sample_entry):
        """export_range() returns a file with entries in the date range."""
        await logger.log(sample_entry)
        export_path = await logger.export_range(
            start="2026-07-01", end="2026-07-31"
        )
        assert isinstance(export_path, Path) or isinstance(export_path, str)

    @pytest.mark.asyncio
    async def test_concurrent_writes_do_not_corrupt(self, logger, sample_entry):
        """Multiple concurrent log() calls produce valid JSONL."""
        import asyncio

        async def write_many(n):
            for _ in range(n):
                from meeting_notes_ai.hipaa.audit_logger import AuditEntry

                await logger.log(
                    AuditEntry(
                        timestamp="2026-07-30T12:00:00Z",
                        actor="concurrent-test",
                        action="test",
                        resource="concurrent",
                        phi_classification="none",
                        outcome="success",
                    )
                )

        await asyncio.gather(write_many(10), write_many(10), write_many(10))
        # All 30 entries should be readable
        entries = await logger.query(limit=100)
        assert len(entries) == 30
