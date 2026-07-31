"""HIPAA middleware — FastAPI dependencies and request interceptors."""
from __future__ import annotations

from typing import Any

from fastapi import Request


async def get_phi_redactor(request: Request) -> Any:
    """FastAPI dependency that provides a PHIRedactor instance."""
    from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

    return PHIRedactor()


async def get_audit_logger(request: Request) -> Any:
    """FastAPI dependency that provides an AuditLogger instance."""
    from meeting_notes_ai.hipaa.audit_logger import AuditLogger

    return AuditLogger()


async def get_encryption_service(request: Request) -> Any:
    """FastAPI dependency that provides an EncryptionService instance."""
    from meeting_notes_ai.hipaa.encryption import EncryptionService

    return EncryptionService()
