"""Object storage abstraction for MeetingNotesAI v0.7.0.

Defines the :class:`ObjectStorageBackend` protocol implemented by the
local-filesystem backend (:mod:`meeting_notes_ai.storage.local`) and the
S3/R2/MinIO backend (:mod:`meeting_notes_ai.storage.s3`). Every backend is
async and stores opaque byte blobs under string keys; all metadata that
matters (checksums, sizes, content types) lives in the ``storage_files``
DB table, not in the object store.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorageBackend(Protocol):
    """Async object-storage contract (put/get/delete/exists/list).

    Implementations must be safe against path traversal (keys are caller
    controlled only through the routes layer) and must never block the
    event loop for long I/O.
    """

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Store *data* under *key*.

        Args:
            key: Object key, e.g. ``"audio/{meeting_id}/{file_id}"``.
            data: Raw bytes to store (possibly an encrypted blob).
            content_type: MIME type of the payload.
            metadata: Optional caller-supplied metadata dict.
        """
        ...

    async def get(self, key: str) -> bytes:
        """Return the bytes stored under *key*.

        Raises:
            KeyError: If no object exists for *key*.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove the object under *key* (idempotent)."""
        ...

    async def exists(self, key: str) -> bool:
        """Return True when an object exists under *key*."""
        ...

    async def list(self, prefix: str) -> list[str]:
        """Return all object keys under *prefix*."""
        ...
