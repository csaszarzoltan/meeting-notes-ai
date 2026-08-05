"""HIPAA middleware — FastAPI dependencies and request interceptors.

The dependencies resolve to process-wide singletons so stateful HIPAA
services (audit log file handles, in-memory key store, redactor stats)
survive across requests. A per-request instance would write to a
different audit file and lose the key store on every call.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

# Module-level singletons (lazily constructed on first request).
_phi_redactor: Any | None = None
_audit_logger: Any | None = None
_encryption_service: Any | None = None


async def get_phi_redactor(request: Request) -> Any:
    """FastAPI dependency that provides the shared PHIRedactor instance."""
    global _phi_redactor
    if _phi_redactor is None:
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        _phi_redactor = PHIRedactor()
    return _phi_redactor


async def get_audit_logger(request: Request) -> Any:
    """FastAPI dependency that provides the shared AuditLogger instance."""
    global _audit_logger
    if _audit_logger is None:
        from meeting_notes_ai.hipaa.audit_logger import AuditLogger

        _audit_logger = AuditLogger()
    return _audit_logger


async def get_encryption_service(request: Request) -> Any:
    """FastAPI dependency that provides the shared EncryptionService instance.

    Requires the ``HIPAA_MASTER_KEY`` environment variable (the KEK seed).
    When it is missing, returns HTTP 503 with a clear message instead of
    leaking the underlying EncryptionError as a 500.
    """
    global _encryption_service
    if _encryption_service is None:
        from meeting_notes_ai.hipaa.encryption import EncryptionError, EncryptionService

        try:
            _encryption_service = EncryptionService()
        except EncryptionError:
            raise HTTPException(
                status_code=503,
                detail="Encryption unavailable: set HIPAA_MASTER_KEY",
            )
    return _encryption_service
