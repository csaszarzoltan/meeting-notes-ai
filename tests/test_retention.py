"""Pre-development tests for HIPAA retention (storage/retention.py + routes).

Covers expires_at computation (1y/3y/7y/inherit), sweep_expired() deleting
expired objects + soft-deleting rows + writing audit entries
(action=storage.expire), the PUT/GET /api/v1/teams/{id}/retention endpoints
with expires_at recompute, and POST /api/v1/admin/retention/sweep.

RED phase: skips until meeting_notes_ai/storage/retention.py exists.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.quick

storage_retention = pytest.importorskip(
    "meeting_notes_ai.storage.retention",
    reason="implementation pending: meeting_notes_ai/storage/retention.py",
)

DEFAULT_RETENTION_DAYS = 2190  # brief: 6-yr HIPAA default (repo convention)


def _auth_headers(user_id: str) -> dict:
    import asyncio as _asyncio

    from meeting_notes_ai.auth import create_access_token

    token = _asyncio.run(create_access_token(user_id))
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRetentionInterface:
    """RetentionPolicy / SweepResult / sweep_expired contracts."""

    def test_sweep_expired_callable(self):
        assert callable(storage_retention.sweep_expired)

    def test_sweep_expired_is_async(self):
        import inspect

        assert inspect.iscoroutinefunction(storage_retention.sweep_expired)

    def test_sweep_expired_signature(self):
        import inspect

        sig = inspect.signature(storage_retention.sweep_expired)
        params = sig.parameters
        assert "db" in params
        assert "storage" in params
        assert "audit" in params

    def test_sweep_result_fields(self):
        SweepResult = storage_retention.SweepResult
        import dataclasses

        assert dataclasses.is_dataclass(SweepResult)
        fields = {f.name for f in dataclasses.fields(SweepResult)}
        assert {"expired", "deleted", "failed"} <= fields

    def test_sweep_result_defaults_zero(self):
        SweepResult = storage_retention.SweepResult
        result = SweepResult()
        assert result.expired == 0
        assert result.deleted == 0
        assert result.failed == 0

    def test_retention_policy_exists(self):
        assert hasattr(storage_retention, "RetentionPolicy")

    def test_default_retention_days_constant(self):
        assert storage_retention.DEFAULT_RETENTION_DAYS == DEFAULT_RETENTION_DAYS


# ═══════════════════════════════════════════════════════════════════════════════
# expires_at computation
# ═══════════════════════════════════════════════════════════════════════════════


class TestExpiresAtComputation:
    """1y/3y/7y/inherit retention -> expires_at (brief AC4)."""

    def test_one_year(self):
        assert _expires_days(365) == 365

    def test_three_years(self):
        assert _expires_days(1095) == 1095

    def test_seven_years(self):
        assert _expires_days(2555) == 2555

    def test_inherit_uses_default(self):
        assert _expires_days(None) == DEFAULT_RETENTION_DAYS


def _expires_days(retention_days: int | None) -> int:
    """Compute expires_at offset days via the retention module contract."""
    RetentionPolicy = storage_retention.RetentionPolicy
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = RetentionPolicy(retention_days=retention_days)
    expires_at = policy.compute_expires_at(now)
    return round((expires_at - now).total_seconds() / 86400)


# ═══════════════════════════════════════════════════════════════════════════════
# sweep_expired() behavioral
# ═══════════════════════════════════════════════════════════════════════════════


class TestSweepExpiredBehavioral:
    """sweep_expired deletes expired objects, soft-deletes rows, audits."""

    def test_sweep_deletes_expired_and_soft_deletes(self, tmp_path):
        backend, rows, engine = _seed_sweep_rows(tmp_path, expired_count=1, live_count=1)

        async def _run():

            from meeting_notes_ai.db.engine import create_session_factory
            from meeting_notes_ai.db.models import StoredFile
            from meeting_notes_ai.hipaa.audit_logger import AuditLogger
            from meeting_notes_ai.hipaa.config import HIPAAConfig

            factory = create_session_factory(engine)

            audit = AuditLogger(config=HIPAAConfig(audit_log_dir=str(tmp_path / "audit")))

            async with factory() as session:
                result = await storage_retention.sweep_expired(
                    db=session, storage=backend, audit=audit
                )
                assert result.expired == 1
                assert result.deleted == 1
                assert result.failed == 0

                # Expired row soft-deleted; live row untouched.
                expired = await session.get(StoredFile, rows["expired"])
                live = await session.get(StoredFile, rows["live"])
                assert expired.deleted_at is not None
                assert live.deleted_at is None

            # Object bytes removed from the backend for the expired file.
            assert await backend.exists(rows["expired_key"]) is False
            assert await backend.exists(rows["live_key"]) is True

            # Audit entries written with action=storage.expire.
            entries = await audit.query({"action": "storage.expire"})
            assert len(entries) >= 1
            assert entries[0].action == "storage.expire"
            assert entries[0].resource  # object key recorded

            await engine.dispose()

        asyncio.run(_run())

    def test_sweep_skips_soft_deleted_rows(self, tmp_path):
        backend, rows, engine = _seed_sweep_rows(tmp_path, expired_count=1, live_count=0)

        async def _run():

            from meeting_notes_ai.db.engine import create_session_factory
            from meeting_notes_ai.db.models import StoredFile
            from meeting_notes_ai.hipaa.audit_logger import AuditLogger
            from meeting_notes_ai.hipaa.config import HIPAAConfig

            factory = create_session_factory(engine)
            audit = AuditLogger(config=HIPAAConfig(audit_log_dir=str(tmp_path / "audit2")))

            async with factory() as session:
                # Pre-soft-delete the expired row: sweep must not touch it.
                row = await session.get(StoredFile, rows["expired"])
                row.deleted_at = datetime.now(timezone.utc)
                await session.commit()

                result = await storage_retention.sweep_expired(
                    db=session, storage=backend, audit=audit
                )
                assert result.expired == 0
                assert result.deleted == 0
                assert result.failed == 0

            await engine.dispose()

        asyncio.run(_run())


def _seed_sweep_rows(tmp_path, expired_count: int, live_count: int):
    """Seed StoredFile rows (expired + live) with real backend bytes.

    Returns ``(backend, merged, engine)`` — the caller must use the same
    engine's session factory for the sweep so the rows are visible (an
    in-memory SQLite DB lives per-engine, not per-process).
    """
    from meeting_notes_ai.storage.local import LocalStorageBackend

    from meeting_notes_ai.db.engine import (
        create_db_engine,
        create_session_factory,
        init_db,
    )
    from meeting_notes_ai.db.models import (
        Meeting,
        StorageEncryption,
        StorageFileKind,
        StoredFile,
        User,
    )

    backend = LocalStorageBackend(str(tmp_path / "storage"))
    now = datetime.now(timezone.utc)

    async def _seed():
        engine = create_db_engine("sqlite+aiosqlite://", echo=False)
        await init_db(engine)
        factory = create_session_factory(engine)
        rows: dict[str, str] = {}
        keys: dict[str, str] = {}

        async with factory() as session:
            session.add(
                User(
                    id="retention-user",
                    email="retention@example.com",
                    hashed_password="hash",
                    display_name="Retention User",
                )
            )
            session.add(
                Meeting(
                    id="retention-meeting",
                    title="Retention Meeting",
                    user_id="retention-user",
                    filename="retention.wav",
                    mode="general",
                )
            )
            await session.flush()

            for i in range(expired_count):
                row_id = f"expired-{i}"
                key = f"audio/retention-meeting/{row_id}"
                payload = f"expired-{i}".encode()
                await backend.put(key, payload, "audio/wav")
                session.add(
                    StoredFile(
                        id=row_id,
                        meeting_id="retention-meeting",
                        team_id=None,
                        uploaded_by="retention-user",
                        kind=StorageFileKind.AUDIO,
                        object_key=key,
                        bucket="local",
                        size_bytes=len(payload),
                        sha256=hashlib.sha256(payload).hexdigest(),
                        content_type="audio/wav",
                        encryption=StorageEncryption.NONE,
                        expires_at=now - timedelta(days=1),
                    )
                )
                rows[f"expired_{i}"] = row_id
                keys[f"expired_{i}_key"] = key

            for i in range(live_count):
                row_id = f"live-{i}"
                key = f"audio/retention-meeting/{row_id}"
                payload = f"live-{i}".encode()
                await backend.put(key, payload, "audio/wav")
                session.add(
                    StoredFile(
                        id=row_id,
                        meeting_id="retention-meeting",
                        team_id=None,
                        uploaded_by="retention-user",
                        kind=StorageFileKind.AUDIO,
                        object_key=key,
                        bucket="local",
                        size_bytes=len(payload),
                        sha256=hashlib.sha256(payload).hexdigest(),
                        content_type="audio/wav",
                        encryption=StorageEncryption.NONE,
                        expires_at=now + timedelta(days=30),
                    )
                )
                rows[f"live_{i}"] = row_id
                keys[f"live_{i}_key"] = key

            await session.commit()
        return rows, keys, engine

    rows, keys, engine = asyncio.run(_seed())
    merged = {**rows, **keys}
    # The behavioral tests address the single seeded row via singular keys
    # ("expired"/"live"/"expired_key"/"live_key"); expose aliases for the
    # count-1 case the tests actually use.
    if "expired_0" in merged:
        merged["expired"] = merged["expired_0"]
        merged["expired_key"] = merged["expired_0_key"]
    if "live_0" in merged:
        merged["live"] = merged["live_0"]
        merged["live_key"] = merged["live_0_key"]
    return backend, merged, engine


# ═══════════════════════════════════════════════════════════════════════════════
# Retention endpoints
# ═══════════════════════════════════════════════════════════════════════════════


_HAS_ROUTES_MODULE = True
try:
    pytest.importorskip(
        "meeting_notes_ai.routes.storage",
        reason="implementation pending: meeting_notes_ai/routes/storage.py",
    )
except Exception:  # pragma: no cover - importorskip raises Skipped
    _HAS_ROUTES_MODULE = False


class TestRetentionEndpoints:
    """PUT/GET /api/v1/teams/{id}/retention + admin sweep endpoint."""

    pytestmark = pytest.mark.skipif(
        not _HAS_ROUTES_MODULE,
        reason="implementation pending: meeting_notes_ai/routes/storage.py",
    )

    @pytest.fixture
    def client(self, _setup_test_db, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.config import settings
        from meeting_notes_ai.main import app

        monkeypatch.setattr(
            settings, "storage_local_dir", str(tmp_path / "storage"), raising=False
        )
        return TestClient(app)

    def test_put_retention_requires_admin(self, client):
        resp = client.put(
            "/api/v1/teams/test-team/retention",
            json={"retention_days": 365},
            headers=_auth_headers("viewer-user-id"),
        )
        assert resp.status_code == 403

    def test_put_retention_accepts_valid_values(self, client):
        for days in (365, 1095, 2555):
            resp = client.put(
                "/api/v1/teams/test-team/retention",
                json={"retention_days": days},
                headers=_auth_headers("admin-user-id"),
            )
            assert resp.status_code == 200, resp.text

    def test_put_retention_rejects_invalid_value(self, client):
        resp = client.put(
            "/api/v1/teams/test-team/retention",
            json={"retention_days": 100},
            headers=_auth_headers("admin-user-id"),
        )
        assert resp.status_code == 422

    def test_put_retention_null_inherits(self, client):
        resp = client.put(
            "/api/v1/teams/test-team/retention",
            json={"retention_days": None},
            headers=_auth_headers("admin-user-id"),
        )
        assert resp.status_code == 200

    def test_get_retention_returns_policy(self, client):
        resp = client.get(
            "/api/v1/teams/test-team/retention",
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "retention_days" in data
        assert "effective_days" in data
        assert "expires_at_example" in data

    def test_sweep_endpoint_requires_admin_token(self, client):
        resp = client.post("/api/v1/admin/retention/sweep")
        assert resp.status_code in (401, 403)

    def test_sweep_endpoint_returns_counts(self, client, monkeypatch):
        from meeting_notes_ai.config import settings

        monkeypatch.setattr(settings, "admin_api_enabled", True)
        monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
        resp = client.post(
            "/api/v1/admin/retention/sweep",
            headers={"Authorization": "Bearer test-admin-token"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "expired" in data
        assert "deleted" in data
        assert "failed" in data
