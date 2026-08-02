"""Local filesystem storage backend.

Stores blobs under ``STORAGE_LOCAL_DIR`` (default ``data/storage``) with
``0600`` permissions. Keys are validated against path traversal before any
filesystem access — keys containing ``..`` path components, absolute paths,
or backslash separators are rejected with :class:`ValueError`.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


class LocalStorageBackend:
    """Filesystem implementation of the ObjectStorageBackend contract.

    Every blob is written with ``0600`` permissions so stored audio and
    transcripts are never world-readable on a shared host.
    """

    def __init__(self, dir: str | os.PathLike[str] = "data/storage") -> None:
        """Initialise the backend rooted at *dir* (created if missing)."""
        self.root = Path(dir)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Key safety ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_key(key: str) -> None:
        """Reject keys that could escape the storage root.

        Raises:
            ValueError: For empty keys, absolute paths, and keys containing
                ``..`` or ``.`` path components or backslash separators.
        """
        if not key:
            raise ValueError("Storage key must not be empty")
        if key.startswith("/") or key.startswith("\\"):
            raise ValueError(f"Storage key must be relative: {key!r}")
        normalized = key.replace("\\", "/")
        parts = normalized.split("/")
        if any(part in ("..", ".") for part in parts):
            raise ValueError(f"Storage key must not contain path traversal: {key!r}")

    def _resolve(self, key: str) -> Path:
        """Return the on-disk path for *key* after validating it."""
        self._validate_key(key)
        return self.root / key

    # ── Async I/O helpers (keep the event loop responsive) ───────────────────

    async def _write_bytes(self, path: Path, data: bytes) -> None:
        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(path, 0o600)
            finally:
                pass

        await asyncio.to_thread(_write)

    # ── ObjectStorageBackend implementation ──────────────────────────────────

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Store *data* under *key* with 0600 permissions."""
        path = self._resolve(key)
        await self._write_bytes(path, data)

    async def get(self, key: str) -> bytes:
        """Return the bytes stored under *key*.

        Raises:
            KeyError: If no object exists for *key*.
        """
        path = self._resolve(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise KeyError(key) from None

    async def delete(self, key: str) -> None:
        """Remove the object under *key* (idempotent)."""
        path = self._resolve(key)

        def _delete() -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        """Return True when an object exists under *key*."""
        path = self._resolve(key)
        return await asyncio.to_thread(path.exists)

    async def list(self, prefix: str) -> list[str]:
        """Return all object keys under *prefix* (e.g. ``"audio/"``)."""
        prefix = prefix or ""

        def _list() -> list[str]:
            if not self.root.exists():
                return []
            keys: list[str] = []
            for path in sorted(self.root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.root).as_posix()
                if rel.startswith(prefix):
                    keys.append(rel)
            return keys

        return await asyncio.to_thread(_list)
