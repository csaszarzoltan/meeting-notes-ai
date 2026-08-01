"""Integration tests for S3StorageBackend against a local MinIO.

Requires the dev MinIO stack:  docker compose -f docker-compose.dev.yml up -d minio
(brief Section 10). Skips with a clear message when MinIO is unreachable so
the quick suite and CI stay green on infra alone (AC6/AC7).
"""

from __future__ import annotations

import socket

import pytest

pytestmark = pytest.mark.integration

storage_s3 = pytest.importorskip(
    "meeting_notes_ai.storage.s3",
    reason="implementation pending: meeting_notes_ai/storage/s3.py",
)

MINIO_PORT = 9000


def _minio_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", MINIO_PORT), timeout=2.0):
            return True
    except OSError:
        return False


if not _minio_reachable():
    pytest.skip(
        "MinIO unreachable at 127.0.0.1:9000 — start it with: "
        "docker compose -f docker-compose.dev.yml up -d minio",
        allow_module_level=True,
    )


def _minio_settings(monkeypatch):
    """Settings pointed at the local MinIO dev stack (brief Section 10)."""
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "true")
    monkeypatch.setenv("S3_BUCKET", "meeting-notes-ai-test")
    from meeting_notes_ai.config import Settings

    return Settings()


class TestS3StorageBackendIntegration:
    """Real MinIO roundtrip + full flow (AC1/AC7)."""

    @pytest.fixture
    def backend(self, monkeypatch):
        S3StorageBackend = storage_s3.S3StorageBackend
        return S3StorageBackend(_minio_settings(monkeypatch))

    async def test_put_get_roundtrip(self, backend):
        await backend.put("itest/roundtrip.txt", b"hello minio", "text/plain")
        assert await backend.get("itest/roundtrip.txt") == b"hello minio"

    async def test_exists(self, backend):
        await backend.put("itest/exists.txt", b"x", "text/plain")
        assert await backend.exists("itest/exists.txt") is True
        assert await backend.exists("itest/never-was") is False

    async def test_list_prefix(self, backend):
        await backend.put("itest/list/a.txt", b"a", "text/plain")
        await backend.put("itest/list/b.txt", b"b", "text/plain")
        keys = await backend.list("itest/list/")
        assert sorted(keys) == ["itest/list/a.txt", "itest/list/b.txt"]

    async def test_delete(self, backend):
        await backend.put("itest/delete.txt", b"bye", "text/plain")
        await backend.delete("itest/delete.txt")
        assert await backend.exists("itest/delete.txt") is False
