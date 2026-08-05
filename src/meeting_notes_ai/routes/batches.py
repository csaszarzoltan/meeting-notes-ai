"""Batch processing endpoints for MeetingNotesAI v0.2.0.

Endpoints:
    POST /api/v1/batches          — Upload multiple audio files for processing
    GET  /api/v1/batches/{id}     — Get batch job status and per-file results
    GET  /api/v1/batches/{id}/export — Export batch results in specified format
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import (
    BatchFileResult,
    BatchJob,
    BatchStatus,
    Meeting,
)
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.models import MeetingMode
from meeting_notes_ai.services.export import ExportService

router = APIRouter(prefix="/api/v1/batches", tags=["batches"])

MAX_BATCH_FILES = 10


# ── Request/Response Schemas ────────────────────────────────────────────────────


class BatchFileResultSummary(BaseModel):
    filename: str
    status: BatchStatus
    meeting_id: str | None = None
    transcript_summary: str | None = None
    error_message: str | None = None
    processing_time_ms: float | None = None


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: BatchStatus
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    file_results: list[BatchFileResultSummary] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None


class BatchCreateResponse(BaseModel):
    batch_id: str
    status: BatchStatus = BatchStatus.PENDING
    file_count: int
    created_at: datetime | None = None


class BatchExportResponse(BaseModel):
    """Response for batch export endpoint."""

    filename: str
    content_type: str
    content_length: int | None = None


# ── Helper: process a single file ──────────────────────────────────────────────


async def _process_single_file(
    file: UploadFile,
    mode: str,
    language: str | None,
    user_id: str,
    team_id: str | None,
    db: AsyncSession,
) -> tuple[BatchStatus, str | None, float, str | None]:
    """Process a single uploaded meeting file through the pipeline.

    Returns:
        Tuple of (status, meeting_id, processing_time_ms, error_message_or_summary)
    """
    start = time.monotonic()
    try:
        content = await file.read()
        filename = file.filename or "unknown"

        # Process through existing pipeline
        api_key = os.getenv("OPENAI_API_KEY", "")
        allowed_modes = [m.value for m in MeetingMode]
        meeting_mode = MeetingMode(mode) if mode in allowed_modes else MeetingMode.GENERAL

        # Transcribe
        from meeting_notes_ai.services.transcription import TranscriptionService

        transcriber = TranscriptionService(api_key=api_key)
        transcript_result = await transcriber.transcribe(
            audio_bytes=content,
            filename=filename,
            language=language,
        )

        # Extract
        from meeting_notes_ai.services.extraction import ExtractionService

        extractor = ExtractionService(provider="openai", api_key=api_key)
        extraction = await extractor.extract(
            transcript=transcript_result.text,
            mode=meeting_mode,
        )

        # Mode-specific processing
        summary = extraction.summary or ""

        if meeting_mode == MeetingMode.HEALTHCARE:
            from meeting_notes_ai.services.healthcare import HealthcareService

            hc = HealthcareService(extraction_service=extractor)
            healthcare_result = await hc.process(transcript_result.text)
            summary = healthcare_result.soap.assessment or summary

        elif meeting_mode == MeetingMode.LEGAL:
            from meeting_notes_ai.services.legal import LegalService

            legal = LegalService(extraction_service=extractor)
            legal_result = await legal.process(transcript_result.text)
            summary = legal_result.summary or summary

        # Save meeting
        meeting = Meeting(
            title=filename,
            user_id=user_id,
            team_id=team_id,
            filename=filename,
            mode=mode,
            transcript=transcript_result.text,
            action_items=json.dumps([a.model_dump() for a in extraction.action_items]),
            decisions=json.dumps(extraction.decisions),
            key_points=json.dumps(extraction.key_points),
        )
        db.add(meeting)
        await db.flush()

        elapsed = (time.monotonic() - start) * 1000
        return BatchStatus.COMPLETED, meeting.id, elapsed, summary

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return BatchStatus.FAILED, None, elapsed, str(e)


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.post("", response_model=BatchCreateResponse, status_code=201)
async def create_batch(
    files: list[UploadFile],
    team_id: str | None = None,
    mode: str = "general",
    language: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BatchCreateResponse:
    """Upload multiple audio files for batch processing.

    Accepts up to 10 audio files (multipart/form-data).
    Creates a BatchJob with status 'pending' and processes each file.
    Returns immediately with a batch tracking ID.

    Args:
        files: List of audio files to process (max 10, max 25 MB each).
        team_id: Optional team scope for the batch.
        mode: Processing mode (general, healthcare, legal).
        language: Optional language hint for transcription.

    Returns:
        BatchCreateResponse with tracking ID.
    """
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BATCH_FILES} files allowed per batch",
        )

    user_id = user["user_id"]
    batch = BatchJob(
        user_id=user_id,
        team_id=team_id,
        status=BatchStatus.PENDING,
        total_files=len(files),
    )
    db.add(batch)
    await db.flush()

    batch.status = BatchStatus.PROCESSING
    await db.flush()

    # Process each file sequentially
    for file in files:
        f_status, meeting_id, proc_time, summary_or_error = await _process_single_file(
            file=file,
            mode=mode,
            language=language,
            user_id=user_id,
            team_id=team_id,
            db=db,
        )

        file_result = BatchFileResult(
            batch_job_id=batch.id,
            filename=file.filename or "unknown",
            status=f_status,
            meeting_id=meeting_id,
            transcript_summary=summary_or_error if f_status == BatchStatus.COMPLETED else None,
            error_message=summary_or_error if f_status == BatchStatus.FAILED else None,
            processing_time_ms=proc_time,
        )
        db.add(file_result)

        if f_status == BatchStatus.COMPLETED:
            batch.completed_files += 1
        else:
            batch.failed_files += 1

    # Update batch status
    if batch.failed_files == batch.total_files:
        batch.status = BatchStatus.FAILED
        batch.error_message = "All files failed to process"
    elif batch.failed_files > 0:
        batch.status = BatchStatus.COMPLETED
    else:
        batch.status = BatchStatus.COMPLETED

    await db.flush()

    return BatchCreateResponse(
        batch_id=batch.id,
        status=batch.status,
        file_count=len(files),
        created_at=batch.created_at,
    )


@router.get("/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BatchStatusResponse:
    """Get batch job status and per-file results.

    Args:
        batch_id: The batch tracking ID.

    Returns:
        BatchStatusResponse with status and per-file details.
    """
    result = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    file_results_result = await db.execute(
        select(BatchFileResult).where(BatchFileResult.batch_job_id == batch_id)
    )
    file_results = file_results_result.scalars().all()

    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        total_files=batch.total_files,
        completed_files=batch.completed_files,
        failed_files=batch.failed_files,
        file_results=[
            BatchFileResultSummary(
                filename=fr.filename,
                status=fr.status,
                meeting_id=fr.meeting_id,
                transcript_summary=fr.transcript_summary,
                error_message=fr.error_message,
                processing_time_ms=fr.processing_time_ms,
            )
            for fr in file_results
        ],
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        error_message=batch.error_message,
    )


@router.get("/{batch_id}/export")
async def export_batch(
    batch_id: str,
    format: str = "json",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Export batch results in specified format.

    Args:
        batch_id: The batch tracking ID.
        format: Export format — 'json', 'markdown', 'pdf', or 'all' (ZIP).

    Returns:
        File response with exported content.
    """
    from fastapi.responses import Response

    result = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    file_results_result = await db.execute(
        select(BatchFileResult).where(BatchFileResult.batch_job_id == batch_id)
    )
    file_results = file_results_result.scalars().all()

    # Collect meeting data for each completed file
    meeting_data = []
    for fr in file_results:
        if fr.meeting_id and fr.status == BatchStatus.COMPLETED:
            meeting_result = await db.execute(select(Meeting).where(Meeting.id == fr.meeting_id))
            meeting = meeting_result.scalar_one_or_none()
            if meeting:
                meeting_data.append(
                    {
                        "id": meeting.id,
                        "title": meeting.title,
                        "filename": meeting.filename,
                        "mode": meeting.mode,
                        "transcript": meeting.transcript,
                        "summary": fr.transcript_summary or "",
                        "action_items": meeting.action_items,
                        "decisions": meeting.decisions,
                        "key_points": meeting.key_points,
                    }
                )

    export_service = ExportService()

    if format == "all":
        modes = [MeetingMode(m.get("mode", "general")) for m in meeting_data]
        zip_bytes = export_service.export_batch_zip(
            results=meeting_data,
            modes=modes,
        )
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.zip"'},
        )
    elif format == "pdf":
        import weasyprint

        html_parts = [f"<h1>Batch Export: {batch_id}</h1>"]
        for m in meeting_data:
            mode = MeetingMode(m.get("mode", "general"))
            md_content = export_service.export_markdown(m, mode)
            html_body = md_content.replace("\n", "<br>\n")
            html_parts.append(f"<div>{html_body}</div><hr>")

        html = f"<html><body>{''.join(html_parts)}</body></html>"
        pdf_bytes = weasyprint.from_string(html)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.pdf"'},
        )
    else:
        parts = []
        content_type = "text/plain"
        for m in meeting_data:
            if format == "markdown":
                mode_val = MeetingMode(m.get("mode", "general"))
                parts.append(export_service.export_markdown(m, mode_val))
                content_type = "text/markdown"
            else:
                parts.append(json.dumps(m, indent=2, default=str))
                content_type = "application/json"

        content = "\n---\n".join(parts) if len(parts) > 1 else (parts[0] if parts else "[]")
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.{format}"'},
        )
