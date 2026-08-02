"""Secure file storage for MeetingNotesAI v0.7.0.

Backend-agnostic object storage (local filesystem, S3, Cloudflare R2,
MinIO) with optional AES-256-GCM encryption at rest and a HIPAA
retention engine with audit logging.

Public API:
- :func:`get_storage_backend` — backend factory from ``STORAGE_BACKEND``
- :class:`FileEncryptor` — AES-256-GCM per-file envelope encryption
- :class:`RetentionPolicy` / :func:`sweep_expired` — HIPAA retention
"""

from meeting_notes_ai.storage.base import ObjectStorageBackend
from meeting_notes_ai.storage.encryption import (
    EncryptionError,
    FileEncryptor,
    MODE_AES256GCM,
    MODE_NONE,
)
from meeting_notes_ai.storage.factory import get_storage_backend
from meeting_notes_ai.storage.local import LocalStorageBackend
from meeting_notes_ai.storage.retention import (
    DEFAULT_RETENTION_DAYS,
    RetentionPolicy,
    SweepResult,
    sweep_expired,
)

try:  # aiobotocore is an optional dep for pure-local deployments
    from meeting_notes_ai.storage.s3 import S3StorageBackend
except ImportError:  # pragma: no cover - s3 backend unavailable
    S3StorageBackend = None  # type: ignore[assignment]

__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "EncryptionError",
    "FileEncryptor",
    "LocalStorageBackend",
    "MODE_AES256GCM",
    "MODE_NONE",
    "ObjectStorageBackend",
    "RetentionPolicy",
    "S3StorageBackend",
    "SweepResult",
    "get_storage_backend",
    "sweep_expired",
]
