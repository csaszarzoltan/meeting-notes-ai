"""Meeting processing endpoint.

POST /api/v1/meetings — accept audio, return structured notes.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, UploadFile

from meeting_notes_ai.config import settings
from meeting_notes_ai.models import (
    MeetingMode,
    MeetingResponse,
)
from meeting_notes_ai.services.export import ExportService
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.healthcare import HealthcareService
from meeting_notes_ai.services.legal import LegalService
from meeting_notes_ai.services.transcription import TranscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meetings", tags=["meetings"])


def _build_services() -> dict:
    """Build and cache service instances."""
    # Use settings or env vars for API keys
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")

    transcription = TranscriptionService(api_key=api_key)
    extraction = ExtractionService(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=api_key,
    )
    healthcare = HealthcareService(extraction_service=extraction)
    legal = LegalService(extraction_service=extraction)
    export_svc = ExportService()

    return {
        "transcription": transcription,
        "extraction": extraction,
        "healthcare": healthcare,
        "legal": legal,
        "export": export_svc,
    }


@router.post("", response_model=MeetingResponse, status_code=200)
async def process_meeting(
    file: UploadFile,
    mode: str = "general",
    language: str | None = None,
    patient_id: str | None = None,
    consent_confirmed: bool = False,
    case_number: str | None = None,
    jurisdiction: str | None = None,
) -> MeetingResponse:
    """Accept audio, return structured notes.

    Supported audio formats: WAV, MP3, MP4, WebM
    Max file size: 25 MB (configurable)
    """
    # Validate file size
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.max_audio_size_mb} MB",
        )

    # Validate content type
    if file.content_type not in settings.SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {file.content_type}. "
            f"Supported: {', '.join(settings.SUPPORTED_AUDIO_FORMATS)}",
        )

    meeting_mode = MeetingMode(mode)
    services = _build_services()

    # Step 1: Transcribe
    try:
        transcript_result = await services["transcription"].transcribe(
            audio_bytes=contents,
            filename=file.filename or "recording",
            language=language,
        )
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(
            status_code=500,
            detail="Transcription failed",
        )

    # Step 2: Extract
    try:
        extraction_result = await services["extraction"].extract(
            transcript=transcript_result.text,
            mode=meeting_mode,
        )
    except Exception:
        logger.exception("Extraction failed")
        raise HTTPException(
            status_code=500,
            detail="Extraction failed",
        )

    # Step 3: Mode-specific processing
    metadata: dict = {}

    if meeting_mode == MeetingMode.HEALTHCARE:
        healthcare_note = await services["healthcare"].process(
            transcript=transcript_result.text,
            patient_id=patient_id,
            consent_confirmed=consent_confirmed,
        )
        metadata["healthcare"] = healthcare_note.model_dump()

    elif meeting_mode == MeetingMode.LEGAL:
        from meeting_notes_ai.models import CaseMetadata

        case_meta = None
        if case_number or jurisdiction:
            case_meta = CaseMetadata(
                case_number=case_number or "",
                jurisdiction=jurisdiction,
            )
        legal_note = await services["legal"].process(
            transcript=transcript_result.text,
            case_metadata=case_meta,
        )
        metadata["legal"] = legal_note.model_dump()

    return MeetingResponse(
        transcript=transcript_result.text,
        action_items=extraction_result.action_items,
        decisions=extraction_result.decisions,
        key_points=extraction_result.key_points,
        mode=meeting_mode,
        metadata=metadata,
    )
