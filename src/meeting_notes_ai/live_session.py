"""Live session domain models and WebSocket message schemas — MeetingNotesAI v0.7.0.

Pre-development TDD contract (RED phase): the model/schema definitions in this
module are the *interface* — they must be importable and constructible
immediately so interface tests pass. All session *behavior* (persistence,
chunk ingestion, partial generation, finalize pipeline, rate limiting) lives in
``meeting_notes_ai.services.live_transcription`` and raises
``NotImplementedError`` until the developer implements it.

Module placement note: the task brief suggested ``models/live_session.py``, but
a ``models/`` package would shadow the existing ``models.py`` module that every
router/service imports (``from meeting_notes_ai.models import ...`` — packages
take precedence over same-named modules). The flat ``live_session.py`` module
preserves the same intent without breaking the existing import graph.

Wire contract (WebSocket endpoint /api/v1/meetings/live):
- Client connects with query params: token (JWT), meeting_id, optional
  team_id / room_id.
- Client sends **binary frames** = streaming audio chunks (16 kHz PCM or
  WebM/Opus).
- Client sends a **text control frame** to finalize:
  ``{"type": "finalize"}``.
- Server replies with JSON text frames of type ``partial`` carrying a
  monotonically increasing ``sequence`` and a ``timestamp``, then a
  ``finalized`` frame carrying the persisted result (session_id, meeting_id,
  transcript, summary, ...).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from meeting_notes_ai.models import ActionItem

# ── Enums ──────────────────────────────────────────────────────────────────────


class LiveSessionStatus(str, Enum):
    """Lifecycle of a live transcription session."""

    LIVE = "live"
    FINALIZED = "finalized"


class LiveChunkFormat(str, Enum):
    """Accepted streaming audio encodings."""

    PCM16K = "pcm16k"  # 16 kHz, 16-bit little-endian mono PCM
    WEBM_OPUS = "webm_opus"  # WebM container with Opus codec


# ── Streaming schemas ──────────────────────────────────────────────────────────


class LiveChunk(BaseModel):
    """One streaming audio chunk received over the WebSocket."""

    sequence: int = 0
    format: LiveChunkFormat = LiveChunkFormat.PCM16K
    data: bytes = b""
    received_at: datetime | None = None


class LivePartial(BaseModel):
    """One incremental transcript fragment pushed over the WebSocket."""

    sequence: int = 0
    text: str = ""
    timestamp: datetime | None = None
    is_final: bool = False


# ── Session model ──────────────────────────────────────────────────────────────


class LiveSession(BaseModel):
    """A resumable live transcription session, scoped to a meeting/room.

    Survives client disconnects: the service persists chunks and partials so a
    client can reconnect and resume via ``resume_session``.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    meeting_id: str
    user_id: str
    team_id: str | None = None
    room_id: str | None = None
    status: LiveSessionStatus = LiveSessionStatus.LIVE
    chunks: list[LiveChunk] = Field(default_factory=list)
    partials: list[LivePartial] = Field(default_factory=list)
    retention_days: int | None = None
    hipaa: bool = False
    phi_classification: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


# ── Response schema (shared by WS finalize + REST upload fallback) ────────────


class LiveTranscriptResponse(BaseModel):
    """Full transcript result returned after finalize / file upload.

    Mirrors ``MeetingResponse`` so the REST fallback
    ``POST /api/v1/meetings/live/upload`` returns the same shape as a
    finalized WebSocket session.
    """

    session_id: str | None = None
    meeting_id: str
    transcript: str = ""
    summary: str = ""
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    chunk_count: int = 0
    partial_count: int = 0
    duration_seconds: float = 0.0


class LiveStartResponse(BaseModel):
    """Response for creating a draft meeting the live UI connects to.

    The WebSocket endpoint requires the ``meeting_id`` row to already exist
    (owner/team scoping is checked before the session is created), so the
    live view calls ``POST /api/v1/meetings/live/start`` first and uses the
    returned ``meeting_id`` as the WS ``meeting_id`` query parameter.
    """

    meeting_id: str
    status: str = "live_ready"
