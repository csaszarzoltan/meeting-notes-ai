"""Unified meeting processing endpoint with safe defaults and actionable feedback."""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from meeting_notes_ai.config import settings
from meeting_notes_ai.models import CaseMetadata, MeetingMode, MeetingResponse
from meeting_notes_ai.services.export import ExportService
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.healthcare import HealthcareService
from meeting_notes_ai.services.legal import LegalService
from meeting_notes_ai.services.transcription import TranscriptionService
from meeting_notes_ai.services.workflow import resolve_processing_policy, workflow_telemetry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/meetings", tags=["meetings"])


def _build_services() -> dict:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    transcription = TranscriptionService(api_key=api_key)
    extraction = ExtractionService(
        provider=settings.llm_provider, model=settings.llm_model, api_key=api_key
    )
    return {
        "transcription": transcription,
        "extraction": extraction,
        "healthcare": HealthcareService(extraction_service=extraction),
        "legal": LegalService(extraction_service=extraction),
        "export": ExportService(),
    }


def _error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


@router.post("", response_model=MeetingResponse, status_code=200)
async def process_meeting(
    file: UploadFile = File(...),
    mode: str = Form("general"),
    language: str | None = Form(None),
    patient_id: str | None = Form(None),
    consent_confirmed: bool = Form(False),
    case_number: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    phi_redaction: bool | None = Form(None),
) -> MeetingResponse:
    """Process one meeting through a single workflow.

    Healthcare meetings default to PHI redaction and human review. The response
    exposes review state and warnings so clients can prevent premature sharing.
    """
    try:
        meeting_mode = MeetingMode(mode)
    except ValueError as exc:
        raise _error(
            422,
            "invalid_mode",
            "Choose a supported meeting type.",
            supported_modes=[m.value for m in MeetingMode],
        ) from exc

    contents = await file.read()
    if not contents:
        raise _error(
            400, "empty_file", "The uploaded audio file is empty. Choose another recording."
        )
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise _error(
            413,
            "file_too_large",
            f"The file exceeds the {settings.max_audio_size_mb} MB limit.",
            max_size_mb=settings.max_audio_size_mb,
        )
    if file.content_type not in settings.SUPPORTED_AUDIO_FORMATS:
        raise _error(
            415,
            "unsupported_audio_format",
            "Use WAV, MP3, MP4, or WebM audio.",
            received=file.content_type,
            supported=sorted(settings.SUPPORTED_AUDIO_FORMATS),
        )

    policy = resolve_processing_policy(meeting_mode, phi_redaction)
    workflow_telemetry.record("started", mode=meeting_mode)
    services = _build_services()
    meeting_id = str(uuid4())

    try:
        transcript_result = await services["transcription"].transcribe(
            audio_bytes=contents, filename=file.filename or "recording", language=language
        )
    except Exception as exc:
        workflow_telemetry.record("failed", mode=meeting_mode)
        logger.exception(
            "Transcription failed meeting_id=%s mode=%s", meeting_id, meeting_mode.value
        )
        raise _error(
            502,
            "transcription_failed",
            "We could not transcribe this recording. Try again or use a different audio format.",
            stage="transcription",
            correlation_id=meeting_id,
        ) from exc

    transcript = transcript_result.text
    redaction_matches = 0
    if policy.phi_redaction:
        from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

        transcript, matches = PHIRedactor().redact(transcript, mode="mask")
        redaction_matches = len(matches)
        workflow_telemetry.record("redacted", mode=meeting_mode)

    try:
        extraction_result = await services["extraction"].extract(
            transcript=transcript, mode=meeting_mode
        )
    except Exception as exc:
        workflow_telemetry.record("failed", mode=meeting_mode)
        logger.exception("Extraction failed meeting_id=%s mode=%s", meeting_id, meeting_mode.value)
        raise _error(
            502,
            "extraction_failed",
            "The transcript was created, but notes could not be generated. Retry note generation.",
            stage="extraction",
            correlation_id=meeting_id,
        ) from exc

    metadata: dict = {}
    warnings: list[str] = []
    if meeting_mode is MeetingMode.HEALTHCARE:
        healthcare_note = await services["healthcare"].process(
            transcript=transcript, patient_id=patient_id, consent_confirmed=consent_confirmed
        )
        metadata["healthcare"] = healthcare_note.model_dump()
        if not consent_confirmed:
            warnings.append("Recording consent has not been confirmed.")
    elif meeting_mode is MeetingMode.LEGAL:
        case_meta = (
            CaseMetadata(case_number=case_number or "", jurisdiction=jurisdiction)
            if (case_number or jurisdiction)
            else None
        )
        legal_note = await services["legal"].process(transcript=transcript, case_metadata=case_meta)
        metadata["legal"] = legal_note.model_dump()

    if policy.review_required:
        workflow_telemetry.record("needs_review", mode=meeting_mode)
        warnings.append("Human review is required before sharing or final use.")
    workflow_telemetry.record("completed", mode=meeting_mode)
    return MeetingResponse(
        id=meeting_id,
        transcript=transcript,
        summary=extraction_result.summary,
        action_items=extraction_result.action_items,
        decisions=extraction_result.decisions,
        key_points=extraction_result.key_points,
        mode=meeting_mode,
        review_status="needs_review" if policy.review_required else "ready",
        phi_redacted=policy.phi_redaction,
        redaction_matches=redaction_matches,
        warnings=warnings,
        metadata=metadata,
    )
