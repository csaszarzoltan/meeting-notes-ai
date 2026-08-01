"""Pre-development tests for LocalStorageBackend (S3/R2 storage abstraction).

Interface tests verify the ObjectStorageBackend protocol contract and the
LocalStorageBackend constructor/method signatures. Behavioral tests exercise
the put/get/delete/exists/list roundtrip, overwrite semantics, missing-key
errors, path-traversal rejection, and 0600 file permissions.

RED phase: the module skips cleanly with an "implementation pending" reason
until the developer implements meeting_notes_ai/storage/{base,local}.py.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.quick

# Guard: un-implemented modules produce skips, NOT collection errors.
storage_base = pytest.importorskip(
    "meeting_notes_ai.storage.base",
    reason="implementation pending: meeting_notes_ai/storage/base.py",
)
storage_local = pytest.importorskip(
    "meeting_notes_ai.storage.local",
    reason="implementation pending: meeting_notes_ai/storage/local.py",
)

ObjectStorageBackend = storage_base.ObjectStorageBackend
LocalStorageBackend = storage_local.LocalStorageBackend


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS once implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestObjectStorageBackendInterface:
    """Verify the storage backend protocol contract."""

    def test_protocol_importable(self):
        from typing import Protocol

        assert ObjectStorageBackend is not None
        assert issubclass(ObjectStorageBackend, Protocol)

    def test_protocol_has_async_put(self):
        assert hasattr(ObjectStorageBackend, "put")
        assert inspect.iscoroutinefunction(ObjectStorageBackend.put)

    def test_protocol_has_async_get(self):
        assert hasattr(ObjectStorageBackend, "get")
        assert inspect.iscoroutinefunction(ObjectStorageBackend.get)

    def test_protocol_has_async_delete(self):
        assert hasattr(ObjectStorageBackend, "delete")
        assert inspect.iscoroutinefunction(ObjectStorageBackend.delete)

    def test_protocol_has_async_exists(self):
        assert hasattr(ObjectStorageBackend, "exists")
        assert inspect.iscoroutinefunction(ObjectStorageBackend.exists)

    def test_protocol_has_async_list(self):
        assert hasattr(ObjectStorageBackend, "list")
        assert inspect.iscoroutinefunction(ObjectStorageBackend.list)

    def test_put_signature(self):
        sig = inspect.signature(ObjectStorageBackend.put)
        params = sig.parameters
        assert "key" in params
        assert "data" in params
        assert "content_type" in params
        # metadata is optional
        md = params.get("metadata")
        assert md is None or md.default is not inspect.Parameter.empty

    def test_get_signature(self):
        sig = inspect.signature(ObjectStorageBackend.get)
        assert "key" in sig.parameters


class TestLocalStorageBackendInterface:
    """Verify LocalStorageBackend constructor and async methods."""

    def test_class_exists(self):
        assert LocalStorageBackend is not None
        assert inspect.isclass(LocalStorageBackend)

    def test_constructor_accepts_dir(self):
        sig = inspect.signature(LocalStorageBackend.__init__)
        params = sig.parameters
        assert any(p in ("dir", "path", "root", "storage_dir") for p in params), (
            f"LocalStorageBackend.__init__ should accept a dir/path, got {list(params)}"
        )

    def test_methods_are_async(self):
        for name in ("put", "get", "delete", "exists", "list"):
            assert hasattr(LocalStorageBackend, name), f"missing method {name}"
            assert inspect.iscoroutinefunction(getattr(LocalStorageBackend, name)), (
                f"{name} should be async"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (roundtrip + safety, run once implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalStorageBehavioral:
    """Roundtrip, overwrite, missing-key, traversal and permission behavior."""

    @pytest.fixture
    def backend(self, tmp_path):
        return LocalStorageBackend(str(tmp_path / "storage"))

    async def test_put_get_roundtrip(self, backend):
        await backend.put("audio/1.wav", b"hello", "audio/wav")
        assert await backend.get("audio/1.wav") == b"hello"

    async def test_put_accepts_metadata(self, backend):
        await backend.put("k", b"data", "text/plain", metadata={"owner": "test"})
        assert await backend.get("k") == b"data"

    async def test_overwrite_same_key(self, backend):
        await backend.put("k", b"first", "text/plain")
        await backend.put("k", b"second", "text/plain")
        assert await backend.get("k") == b"second"

    async def test_exists_true_after_put(self, backend):
        await backend.put("k", b"x", "text/plain")
        assert await backend.exists("k") is True

    async def test_exists_false_for_missing(self, backend):
        assert await backend.exists("nope") is False

    async def test_delete_removes_key(self, backend):
        await backend.put("k", b"x", "text/plain")
        await backend.delete("k")
        assert await backend.exists("k") is False

    async def test_get_missing_key_raises(self, backend):
        with pytest.raises((KeyError, FileNotFoundError)):
            await backend.get("missing")

    async def test_delete_missing_key_is_idempotent(self, backend):
        # Deleting a non-existent key must not raise.
        await backend.delete("missing")

    async def test_list_returns_keys_under_prefix(self, backend):
        await backend.put("a/1", b"1", "text/plain")
        await backend.put("a/2", b"2", "text/plain")
        await backend.put("b/1", b"3", "text/plain")
        keys = await backend.list("a/")
        assert sorted(keys) == ["a/1", "a/2"]

    async def test_path_traversal_put_rejected(self, backend):
        with pytest.raises(ValueError):
            await backend.put("../escape.txt", b"x", "text/plain")

    async def test_path_traversal_get_rejected(self, backend):
        with pytest.raises(ValueError):
            await backend.get("../../etc/passwd")

    async def test_absolute_path_rejected(self, backend):
        with pytest.raises(ValueError):
            await backend.put("/etc/passwd", b"x", "text/plain")

    async def test_file_permissions_0600(self, backend, tmp_path):
        await backend.put("secret.txt", b"sensitive", "text/plain")
        stored = tmp_path / "storage" / "secret.txt"
        assert stored.exists()
        mode = stored.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0600 perms, got {oct(mode)}"
