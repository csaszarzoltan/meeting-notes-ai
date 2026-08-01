"""Pre-development tests for get_storage_backend() factory selection.

The factory reads the STORAGE_BACKEND setting (or env var) and returns the
matching backend: "local" -> LocalStorageBackend, "s3" -> S3StorageBackend,
anything else -> raises. RED phase: skips until storage/factory.py exists.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.quick

storage_factory = pytest.importorskip(
    "meeting_notes_ai.storage.factory",
    reason="implementation pending: meeting_notes_ai/storage/factory.py",
)
storage_local = pytest.importorskip(
    "meeting_notes_ai.storage.local",
    reason="implementation pending: meeting_notes_ai/storage/local.py",
)
storage_s3 = pytest.importorskip(
    "meeting_notes_ai.storage.s3",
    reason="implementation pending: meeting_notes_ai/storage/s3.py",
)

get_storage_backend = storage_factory.get_storage_backend
LocalStorageBackend = storage_local.LocalStorageBackend
S3StorageBackend = storage_s3.S3StorageBackend


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorageFactoryInterface:
    """Verify the factory contract."""

    def test_factory_callable(self):
        assert callable(get_storage_backend)

    def test_factory_signature_optional_settings(self):
        sig = inspect.signature(get_storage_backend)
        params = sig.parameters
        # Either no-arg or an optional settings/backend param.
        assert len(params) <= 1, f"unexpected params: {list(params)}"

    def test_local_backend_importable(self):
        assert LocalStorageBackend is not None

    def test_s3_backend_importable(self):
        assert S3StorageBackend is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorageFactoryBehavioral:
    """Selection per backend setting; unknown backends raise.

    The factory may read STORAGE_BACKEND from the env or from the module-level
    Settings singleton; these tests set both so the contract holds either way.
    """

    def _set_backend(self, monkeypatch, value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        else:
            monkeypatch.setenv("STORAGE_BACKEND", value)
        # Also patch the Settings singleton if it exposes the field.
        from meeting_notes_ai import config

        monkeypatch.setattr(
            config.settings, "storage_backend", value, raising=False
        )

    def test_default_is_local(self, monkeypatch):
        self._set_backend(monkeypatch, None)
        backend = get_storage_backend()
        assert isinstance(backend, LocalStorageBackend)

    def test_local_selection(self, monkeypatch):
        self._set_backend(monkeypatch, "local")
        backend = get_storage_backend()
        assert isinstance(backend, LocalStorageBackend)

    def test_s3_selection(self, monkeypatch):
        self._set_backend(monkeypatch, "s3")
        backend = get_storage_backend()
        assert isinstance(backend, S3StorageBackend)

    def test_unknown_backend_raises(self, monkeypatch):
        self._set_backend(monkeypatch, "ftp")
        with pytest.raises(ValueError):
            get_storage_backend()
