"""HIPAA compliance REST endpoints — MeetingNotesAI v0.5.0.

Wires the ``hipaa`` compliance suite (PHI redaction, audit logging,
encryption, BAA, compliance dashboard) into the REST API. The endpoints
use the FastAPI dependencies from :mod:`meeting_notes_ai.hipaa.middleware`
plus the standard ``get_current_user`` auth dependency.

Endpoints:
    POST /api/v1/transcribe                       — transcribe audio, optional PHI redaction
    GET  /api/v1/audit-logs                       — query audit log entries (filterable)
    GET  /api/v1/audit-logs/stats                 — audit log aggregate statistics
    GET  /api/v1/audit-logs/export                — export audit entries for a date range
    POST /api/v1/encryption/rotate-key            — rotate the master key (re-wraps all DEKs)
    POST /api/v1/compliance/baa/generate          — generate + store a BAA agreement
    GET  /api/v1/compliance/dashboard             — combined summary / phi-stats / activity
    GET  /api/v1/compliance/dashboard/summary     — compliance summary card
    GET  /api/v1/compliance/dashboard/phi-stats   — PHI detection statistics
    GET  /api/v1/compliance/dashboard/activity    — recent audit activity
    GET  /api/v1/compliance/dashboard/html        — server-rendered dashboard page
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.hipaa.audit_logger import AuditEntry
from meeting_notes_ai.hipaa.middleware import (
    get_audit_logger,
    get_encryption_service,
    get_phi_redactor,
)
from meeting_notes_ai.models import TranscriptSegment

router = APIRouter(tags=["hipaa"])

# ── Module-level singletons ─────────────────────────────────────────────────────
# BAAService is a process-wide singleton whose agreements are persisted to
# ~/.meeting-notes-ai/baa_agreements.json (S7) — a per-request instance would
# lose the in-memory cache between calls.

_baa_service: Any | None = None

# ── Templates ───────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "hipaa" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_baa_service() -> Any:
    """Return the process-wide BAAService instance (created lazily)."""
    global _baa_service
    if _baa_service is None:
        from meeting_notes_ai.hipaa.baa import BAAService

        # Persist signed agreements to disk so they survive restarts
        # (S7); the store lives next to EncryptionService's key_store.json.
        _baa_service = BAAService(
            store_path=Path.home() / ".meeting-notes-ai" / "baa_agreements.json"
        )
    return _baa_service


def _client_ip(request: Request) -> str:
    """Best-effort client IP for HIPAA audit trails (who/what/when/WHERE)."""
    if request.client is not None and request.client.host:
        return request.client.host
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else ""


def _client_user_agent(request: Request) -> str:
    """Best-effort client User-Agent for HIPAA audit trails (truncated)."""
    return (request.headers.get("user-agent") or "")[:512]


async def get_transcription_service(request: Request) -> Any:
    """FastAPI dependency providing the transcription service.

    Uses OPENAI_API_KEY from the environment, mirroring the meetings and
    batches routers. Tests override this dependency with a fake.
    """
    from meeting_notes_ai.services.transcription import TranscriptionService

    api_key = os.getenv("OPENAI_API_KEY", "")
    return TranscriptionService(api_key=api_key)


# ── Request/Response Schemas ────────────────────────────────────────────────────


class TranscribeResponse(BaseModel):
    """Result of a transcription, optionally PHI-redacted."""

    text: str = ""
    language: str = ""
    duration_seconds: float = 0.0
    segments: list[TranscriptSegment] = Field(default_factory=list)
    phi_redacted: bool = False
    redaction_matches: int = 0


class AuditLogEntryResponse(BaseModel):
    """A single HIPAA audit log entry."""

    timestamp: str = ""
    actor: str = ""
    action: str = ""
    resource: str = ""
    phi_classification: str = "none"
    details: dict[str, Any] = Field(default_factory=dict)
    outcome: str = "success"
    ip_address: str = ""
    user_agent: str = ""


class RotateKeyRequest(BaseModel):
    """Request body for master-key rotation."""

    new_master_key: str = Field(..., min_length=1, description="New KEK seed secret")


class RotateKeyResponse(BaseModel):
    """Result of a master-key rotation."""

    re_wrapped_keys: int = 0
    rotated_at: str = ""


class BAAGenerateRequest(BaseModel):
    """Request body for BAA agreement generation."""

    org_name: str = Field(..., min_length=1, description="Covered entity name")
    ba_name: str = Field(..., min_length=1, description="Business associate name")
    signed_by: str = Field(..., min_length=1, description="Signatory identifier")


class BAAGenerateResponse(BaseModel):
    """A stored (immutable) BAA agreement."""

    agreement_id: str = ""
    org_name: str = ""
    ba_name: str = ""
    effective_date: str = ""
    status: str = "active"
    content_md: str = ""


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.post("/api/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(None),
    phi_redaction: bool = Form(False),
    user: dict = Depends(get_current_user),
    redactor: Any = Depends(get_phi_redactor),
    audit: Any = Depends(get_audit_logger),
    transcriber: Any = Depends(get_transcription_service),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file, optionally redacting PHI.

    When ``phi_redaction=true`` the transcript text is scanned with the
    PHI redactor and every match is masked before the text is returned.
    Every transcription is recorded in the HIPAA audit log.
    """
    filename = file.filename or "recording"
    content = await file.read()

    try:
        result = await transcriber.transcribe(
            audio_bytes=content,
            filename=filename,
            language=language,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Transcription failed")

    text = result.text
    segments = list(result.segments)
    phi_redacted = False
    redaction_matches = 0
    if phi_redaction:
        redacted_text, matches = redactor.redact(text)
        text = redacted_text
        phi_redacted = True
        redaction_matches = len(matches)
        # N1: segments must never leak plaintext PHI — redact every segment
        # the same way the top-level text is redacted. Without this the
        # response certifies phi_redaction=true while segments[] still
        # carries the original patient identifiers.
        redacted_segments: list[TranscriptSegment] = []
        for segment in segments:
            seg_text, seg_matches = redactor.redact(segment.text)
            redaction_matches += len(seg_matches)
            redacted_segments.append(
                segment.model_copy(update={"text": seg_text})
            )
        segments = redacted_segments

    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user["user_id"],
            action="transcribe",
            resource=filename,
            phi_classification="phi" if phi_redacted else "none",
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={
                "phi_redaction": phi_redaction,
                "redaction_matches": redaction_matches,
            },
        )
    )

    return TranscribeResponse(
        text=text,
        language=result.language,
        duration_seconds=result.duration_seconds,
        segments=segments,
        phi_redacted=phi_redacted,
        redaction_matches=redaction_matches,
    )


@router.get("/api/v1/audit-logs", response_model=list[AuditLogEntryResponse])
async def list_audit_logs(
    actor: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
) -> list[AuditLogEntryResponse]:
    """Query HIPAA audit log entries, newest first.

    Optional filters: ``actor``, ``action``, ``resource``. ``limit`` caps
    the number of returned entries (default 100, max 1000).
    """
    filters: dict[str, Any] = {}
    if actor:
        filters["actor"] = actor
    if action:
        filters["action"] = action
    if resource:
        filters["resource"] = resource

    entries = await audit.query(filters=filters or None, limit=limit)
    return [AuditLogEntryResponse(**asdict(e)) for e in entries]


@router.get("/api/v1/audit-logs/stats")
async def audit_log_stats(
    since: str | None = None,
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
) -> dict[str, Any]:
    """Return aggregate audit log statistics (counts by action/actor/outcome)."""
    return await audit.get_stats(since=since)


@router.get("/api/v1/audit-logs/export")
async def export_audit_logs(
    start: str,
    end: str,
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
) -> Response:
    """Export audit entries within an ISO date range as a JSONL attachment."""
    export_path = await audit.export_range(start, end)
    return Response(
        content=export_path.read_text(encoding="utf-8"),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{export_path.name}"'
        },
    )


@router.post("/api/v1/encryption/rotate-key", response_model=RotateKeyResponse)
async def rotate_key(
    request: Request,
    request_body: RotateKeyRequest,
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
    encryption: Any = Depends(get_encryption_service),
) -> RotateKeyResponse:
    """Rotate the master key (KEK), re-wrapping all tenant DEKs.

    Requires the new key seed secret in the body. The old wrapped keys
    are re-encrypted with the new KEK; returns how many were re-wrapped.
    """
    count = await encryption.rotate_master_key(request_body.new_master_key)
    rotated_at = datetime.now(timezone.utc).isoformat()

    await audit.log(
        AuditEntry(
            timestamp=rotated_at,
            actor=user["user_id"],
            action="encryption.rotate_key",
            resource="master-key",
            phi_classification="none",
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={"re_wrapped_keys": count},
        )
    )

    return RotateKeyResponse(re_wrapped_keys=count, rotated_at=rotated_at)


@router.post(
    "/api/v1/compliance/baa/generate", response_model=BAAGenerateResponse
)
async def generate_baa(
    request: Request,
    baa_request: BAAGenerateRequest,
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
) -> BAAGenerateResponse:
    """Generate and store a Business Associate Agreement (HIPAA §164.504(e)).

    The rendered markdown agreement (with all required clauses) is stored
    immutably and returned together with its id.
    """
    baa_service = _get_baa_service()
    agreement_id = await baa_service.store_agreement(
        org_name=baa_request.org_name,
        ba_name=baa_request.ba_name,
        signed_by=baa_request.signed_by,
    )
    agreement = await baa_service.get_agreement(agreement_id)

    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user["user_id"],
            action="baa.generate",
            resource=agreement_id,
            phi_classification="none",
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={"ba_name": baa_request.ba_name},
        )
    )

    return BAAGenerateResponse(
        agreement_id=agreement.id,
        org_name=agreement.org_name,
        ba_name=agreement.ba_name,
        effective_date=agreement.effective_date,
        status=agreement.status,
        content_md=agreement.content_md,
    )


@router.get("/api/v1/compliance/dashboard")
async def compliance_dashboard(
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
    redactor: Any = Depends(get_phi_redactor),
    encryption: Any = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Return the combined compliance dashboard payload.

    Aggregates the summary card, PHI detection statistics, and recent
    audit activity in one response.
    """
    from meeting_notes_ai.hipaa.dashboard import ComplianceService

    service = ComplianceService(encryption_service=encryption,
                                audit_logger=audit, phi_redactor=redactor,
                                baa_service=_get_baa_service())
    summary = await service.get_summary()
    phi_stats = await service.get_phi_stats()
    activity = await service.get_recent_activity(limit=50)

    return {
        "summary": asdict(summary),
        "phi_stats": asdict(phi_stats),
        "activity": activity,
    }


@router.get("/api/v1/compliance/dashboard/summary")
async def compliance_dashboard_summary(
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
    redactor: Any = Depends(get_phi_redactor),
    encryption: Any = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Return the compliance summary card data."""
    from meeting_notes_ai.hipaa.dashboard import ComplianceService

    service = ComplianceService(encryption_service=encryption,
                                audit_logger=audit, phi_redactor=redactor,
                                baa_service=_get_baa_service())
    return asdict(await service.get_summary())


@router.get("/api/v1/compliance/dashboard/phi-stats")
async def compliance_dashboard_phi_stats(
    user: dict = Depends(get_current_user),
    redactor: Any = Depends(get_phi_redactor),
    encryption: Any = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Return PHI detection statistics for the dashboard charts."""
    from meeting_notes_ai.hipaa.dashboard import ComplianceService

    service = ComplianceService(encryption_service=encryption,
                                phi_redactor=redactor)
    return asdict(await service.get_phi_stats())


@router.get("/api/v1/compliance/dashboard/activity")
async def compliance_dashboard_activity(
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
    audit: Any = Depends(get_audit_logger),
    encryption: Any = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Return recent audit activity (newest first)."""
    from meeting_notes_ai.hipaa.dashboard import ComplianceService

    service = ComplianceService(encryption_service=encryption,
                                audit_logger=audit)
    return await service.get_recent_activity(limit=limit)


@router.get(
    "/api/v1/compliance/dashboard/html",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def compliance_dashboard_html(request: Request) -> HTMLResponse:
    """Serve the client-side compliance dashboard page (Chart.js)."""
    return templates.TemplateResponse(
        request=request, name="dashboard.html.jinja"
    )
