"""Live transcription routes — WebSocket + REST upload fallback (TDD RED stub).

Endpoints:
- WebSocket ``/api/v1/meetings/live`` — JWT-authenticated (token query
  param, since browsers cannot set headers on WebSocket handshakes),
  meeting/room-scoped and team-workspace-aware. Accepts streaming audio
  chunks (16 kHz PCM or WebM/Opus binary frames), streams partial transcripts
  back with monotonic sequence numbers and timestamps, and accepts a
  ``{"type": "finalize"}`` control frame to persist the session.
- ``POST /api/v1/meetings/live/upload`` — REST fallback accepting a full
  audio file and returning the same transcript shape.

Handlers raise ``NotImplementedError`` during the RED phase; the developer
implements them against ``tests/test_live_transcription.py``. The
``get_live_service`` dependency and the router registration are real so the
routes are reachable and tests can override the service seam.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Query, UploadFile, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.config import settings
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.live_session import LiveTranscriptResponse
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.live_transcription import LiveTranscriptionService
from meeting_notes_ai.services.transcription import TranscriptionService

router = APIRouter(prefix="/api/v1/meetings/live", tags=["live-transcription"])


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
    raise NotImplementedError("routes.live_transcription.websocket_live (TDD RED phase)")


@router.post("/upload", response_model=LiveTranscriptResponse, status_code=200)
async def upload_live_audio(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: LiveTranscriptionService = Depends(get_live_service),
) -> LiveTranscriptResponse:
    """REST fallback: transcribe a full audio upload (same result shape)."""
    raise NotImplementedError("routes.live_transcription.upload_live_audio (TDD RED phase)")
