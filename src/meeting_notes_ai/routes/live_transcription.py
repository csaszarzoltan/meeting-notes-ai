"""Live transcription routes — WebSocket + REST upload fallback.

Endpoints:
- WebSocket ``/api/v1/meetings/live`` — JWT-authenticated (token query
  param, since browsers cannot set headers on WebSocket handshakes),
  meeting/room-scoped and team-workspace-aware. Accepts streaming audio
  chunks (16 kHz PCM or WebM/Opus binary frames), streams partial transcripts
  back with monotonic sequence numbers and timestamps, and accepts a
  ``{"type": "finalize"}`` control frame to persist the session.
- ``POST /api/v1/meetings/live/upload`` — REST fallback accepting a full
  audio file and returning the same transcript shape.

Session state lives in the ``LiveTranscriptionService`` (persisted to the
``live_sessions`` table), so a dropped WebSocket can be resumed with the same
session id — state survives the disconnect.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import decode_access_token, get_current_user
from meeting_notes_ai.config import settings
from meeting_notes_ai.db.models import Meeting, Team, TeamMember
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.live_session import (
    LiveChunk,
    LiveChunkFormat,
    LiveStartResponse,
    LiveTranscriptResponse,
)
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.live_transcription import (
    LiveRateLimitExceeded,
    LiveTranscriptionService,
)
from meeting_notes_ai.services.transcription import TranscriptionService

router = APIRouter(prefix="/api/v1/meetings/live", tags=["live-transcription"])

_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"

# WebSocket close codes (4000-4999 are application-defined per RFC 6455).
_WS_UNAUTHORIZED = 4401
_WS_FORBIDDEN = 4403
_WS_NOT_FOUND = 4404


def get_live_service() -> LiveTranscriptionService:
    """FastAPI dependency constructing the live transcription service.

    Built from the same OpenAI-backed services the REST pipeline uses
    (``routes/meetings.py::_build_services``). Tests override this dependency
    with a service wired to fake transcription/extraction implementations so
    the endpoint stack (auth, WS protocol, DB) is exercised for real.
    """
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    return LiveTranscriptionService(
        transcription_service=TranscriptionService(api_key=api_key, model=settings.whisper_model),
        extraction_service=ExtractionService(
            provider=settings.llm_provider, model=settings.llm_model, api_key=api_key
        ),
        rate_limiter=TokenBucketRateLimiter(),
    )


@router.websocket("")
async def websocket_live(
    websocket: WebSocket,
    token: str = Query(...),
    meeting_id: str = Query(...),
    team_id: str | None = Query(None),
    room_id: str | None = Query(None),
    service: LiveTranscriptionService = Depends(get_live_service),
) -> None:
    """Streaming live transcription endpoint (see module docstring)."""
    await websocket.accept()

    try:
        payload = await decode_access_token(token)
    except HTTPException:
        await websocket.close(code=_WS_UNAUTHORIZED)
        return
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=_WS_UNAUTHORIZED)
        return

    # Meeting/room scoping + team-workspace awareness.
    resolved_team_id: str | None = None
    retention_days: int | None = None
    async for db in get_db_session():
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            await websocket.close(code=_WS_NOT_FOUND)
            return
        if meeting.team_id is not None:
            if team_id is not None and team_id != meeting.team_id:
                await websocket.close(code=_WS_FORBIDDEN)
                return
            membership = await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == meeting.team_id,
                    TeamMember.user_id == user_id,
                )
            )
            if membership.scalar_one_or_none() is None:
                await websocket.close(code=_WS_FORBIDDEN)
                return
            # Carry the team's HIPAA retention policy into the session.
            team = await db.get(Team, meeting.team_id)
            retention_days = team.retention_days if team is not None else None
            resolved_team_id = meeting.team_id
        else:
            if meeting.user_id != user_id:
                await websocket.close(code=_WS_FORBIDDEN)
                return

    session = await service.create_session(
        meeting_id=meeting_id,
        user_id=user_id,
        team_id=resolved_team_id,
        room_id=room_id,
        retention_days=retention_days,
    )

    client_gone = False
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                client_gone = True
                break  # session stays persisted; client can resume
            if message["type"] != "websocket.receive":
                continue

            if message.get("bytes") is not None:
                data = message["bytes"]
                chunk = LiveChunk(
                    format=(
                        LiveChunkFormat.WEBM_OPUS
                        if data.startswith(_WEBM_MAGIC)
                        else LiveChunkFormat.PCM16K
                    ),
                    data=data,
                )
                try:
                    partial = await service.ingest_chunk(session.id, chunk)
                except LiveRateLimitExceeded:
                    await websocket.send_json({"type": "error", "code": "rate_limited"})
                    break
                if partial is not None:
                    await websocket.send_json(
                        {
                            "type": "partial",
                            "sequence": partial.sequence,
                            "text": partial.text,
                            "timestamp": (
                                partial.timestamp.isoformat() if partial.timestamp else None
                            ),
                        }
                    )
            elif message.get("text") is not None:
                try:
                    control = json.loads(message["text"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if control.get("type") == "finalize":
                    result = await service.finalize(session.id)
                    await websocket.send_json(
                        {"type": "finalized", **result.model_dump(mode="json")}
                    )
                    break
    finally:
        if not client_gone:
            try:
                await websocket.close()
            except RuntimeError:
                # Connection already torn down by the peer; nothing to do.
                pass


@router.post("/start", response_model=LiveStartResponse, status_code=201)
async def start_live_session(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> LiveStartResponse:
    """Create a draft meeting the live UI connects to.

    The WebSocket handler scopes sessions to an existing ``Meeting`` row
    (owner check / team membership), so the browser view needs a meeting to
    exist before it can open the socket. This endpoint provisions one owned
    by the authenticated user; the live session then attaches to it and
    finalize persists the transcript + summary onto the same row.
    """
    meeting = Meeting(
        user_id=user["user_id"],
        title="Live transcription session",
        filename="live_session.webm",
        mode="general",
        transcript=None,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return LiveStartResponse(meeting_id=meeting.id)


@router.post("/upload", response_model=LiveTranscriptResponse, status_code=200)
async def upload_live_audio(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: LiveTranscriptionService = Depends(get_live_service),
) -> LiveTranscriptResponse:
    """REST fallback: transcribe a full audio upload (same result shape)."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
    if file.content_type not in settings.SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format: {file.content_type}",
        )
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_audio_size_mb} MB limit.",
        )
    try:
        return await service.transcribe_file(
            contents,
            file.filename or "recording.wav",
            user_id=user["user_id"],
        )
    except LiveRateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail="Rate limit exceeded") from exc
