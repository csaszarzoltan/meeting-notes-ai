"""Storage backend factory — selects the backend from configuration.

``get_storage_backend()`` reads ``STORAGE_BACKEND`` (via the Settings
singleton or an explicit :class:`Settings` instance) and returns the
matching backend: ``"local"`` → :class:`LocalStorageBackend`,
``"s3"`` → :class:`S3StorageBackend` (also covers Cloudflare R2 and
MinIO via ``S3_ENDPOINT_URL``). Unknown values raise :class:`ValueError`.
"""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.config import Settings
from meeting_notes_ai.config import settings as default_settings
from meeting_notes_ai.storage.base import ObjectStorageBackend
from meeting_notes_ai.storage.local import LocalStorageBackend


def get_storage_backend(settings: Settings | None = None) -> ObjectStorageBackend:
    """Return the configured storage backend instance.

    Args:
        settings: Optional Settings override (defaults to the module
            singleton, which reads ``STORAGE_BACKEND`` from the env).

    Raises:
        ValueError: If ``STORAGE_BACKEND`` is not ``local`` or ``s3``.
    """
    cfg: Any = settings if settings is not None else default_settings
    name = str(getattr(cfg, "storage_backend", "") or "local").lower()

    if name == "local":
        local_dir = getattr(cfg, "storage_local_dir", "data/storage")
        return LocalStorageBackend(local_dir)
    if name == "s3":
        from meeting_notes_ai.storage.s3 import S3StorageBackend

        return S3StorageBackend(cfg)
    raise ValueError(f"Unknown storage backend: {name!r} (expected 'local' or 's3')")
