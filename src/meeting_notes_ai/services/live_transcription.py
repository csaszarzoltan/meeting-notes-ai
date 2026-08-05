"""Live transcription service — streaming session orchestration.

Implements the TDD GREEN contract from ``tests/test_live_session.py``:

- ``create_session`` / ``get_session`` / ``resume_session`` — session
  lifecycle; every session is persisted to the ``live_sessions`` table so it
  survives client disconnects and can be resumed.
- ``ingest_chunk`` / ``get_partials`` — streaming audio ingestion producing
  incremental partial transcripts with monotonic sequence numbers and
  timestamps. Each chunk triggers an incremental transcription pass over the
  session's accumulated audio via the injected ``TranscriptionService``.
- ``finalize`` — runs the accumulated audio through the existing
  ``services/transcription.py`` pipeline, extracts action items/decisions via
  the existing LLM ``services/extraction.py``, persists the meeting record
  (transcript + summary in ``metadata_json``), and marks the session
  finalized.
- ``transcribe_file`` — REST fallback for a full audio upload, returning the
  same transcript shape and creating the meeting record.

Rate limiting reuses the existing ``TokenBucketRateLimiter`` keyed per user;
an exhausted bucket raises :class:`LiveRateLimitExceeded`, which the route
layer maps to HTTP 429 (or a WS error frame).
"""

from __future__ import annotations

import base64
import binascii
import json
import struct
from datetime import datetime, timezone
from uuid import uuid4

from meeting_notes_ai.db.models import LiveSessionRecord, Meeting
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.live_session import (
    LiveChunk,
    LiveChunkFormat,
    LivePartial,
    LiveSession,
    LiveSessionStatus,
    LiveTranscriptResponse,
)
from meeting_notes_ai.models import ExtractionResult, MeetingMode
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.transcription import TranscriptionService

_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"


def _chunk_to_json(chunk: LiveChunk) -> dict:
    """Serialize a chunk for DB storage with base64-encoded audio bytes.

    ``LiveChunk.data`` is arbitrary binary (WebM/Opus or PCM), which is not
    valid UTF-8 — ``model_dump(mode="json")`` would raise UnicodeDecodeError.
    Base64 keeps the column JSON-safe and round-trippable.
    """
    dumped = chunk.model_dump(mode="python")  # bytes stay bytes — no utf-8 decode
    dumped["data"] = base64.b64encode(chunk.data).decode("ascii")
    if dumped.get("received_at") is not None:
        # mode="python" keeps datetime objects; JSON storage needs an ISO string.
        dumped["received_at"] = dumped["received_at"].isoformat()
    return dumped


def _chunk_from_json(raw: dict) -> LiveChunk:
    """Rehydrate a chunk from DB JSON, tolerating both base64 and legacy rows.

    Rows written before the base64 fix stored ``data`` as a UTF-8-decoded
    string (valid for ASCII-ish test bytes only). We prefer base64 and fall
    back to utf-8 encoding for those legacy rows.
    """
    data = raw.get("data")
    if isinstance(data, str):
        try:
            decoded = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            decoded = data.encode("utf-8")
        raw = {**raw, "data": decoded}
    return LiveChunk.model_validate(raw)


class LiveRateLimitExceeded(Exception):
    """Raised when a user's live-transcription token bucket is empty."""


def _pcm16_to_wav(
    data: bytes, sample_rate: int = 16_000, channels: int = 1, bits: int = 16
) -> bytes:
    """Wrap raw 16-bit PCM in a minimal RIFF/WAVE container.

    Whisper does not accept headerless PCM, so streamed 16 kHz PCM chunks are
    framed as WAV before being handed to the transcription service.
    """
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM (linear quantization)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        len(data),
    )
    return header + data


class LiveTranscriptionService:
    """Streaming session orchestration for live transcription."""

    def __init__(
        self,
        transcription_service: TranscriptionService | None = None,
        extraction_service: ExtractionService | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        max_chunk_bytes: int = 64 * 1024,
    ) -> None:
        self.transcription_service = transcription_service or TranscriptionService(api_key="")
        self.extraction_service = extraction_service or ExtractionService(provider="openai")
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter()
        self.max_chunk_bytes = max_chunk_bytes
        # Canonical in-memory working set. Every mutation is mirrored to the
        # ``live_sessions`` table (durable storage), so a session object keeps
        # its identity within the service while surviving process restarts and
        # client disconnects via ``resume_session``.
        self._sessions: dict[str, LiveSession] = {}

    # ── Session lifecycle ───────────────────────────────────────────────────

    async def create_session(
        self,
        meeting_id: str,
        user_id: str,
        *,
        team_id: str | None = None,
        room_id: str | None = None,
        retention_days: int | None = None,
        hipaa: bool = False,
        phi_classification: str | None = None,
    ) -> LiveSession:
        """Create a new live session scoped to an existing meeting/room."""
        now = datetime.now(timezone.utc)
        session = LiveSession(
            meeting_id=meeting_id,
            user_id=user_id,
            team_id=team_id,
            room_id=room_id,
            retention_days=retention_days,
            hipaa=hipaa,
            phi_classification=phi_classification,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session.id] = session
        await self._save(session)
        return session

    async def get_session(self, session_id: str) -> LiveSession | None:
        """Return the session by id, or None if it does not exist."""
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached
        row = await self._load_row(session_id)
        if row is None:
            return None
        session = self._row_to_session(row)
        self._sessions[session_id] = session
        return session

    async def resume_session(self, session_id: str) -> LiveSession | None:
        """Rehydrate a session after a client disconnect (same id/state)."""
        return await self.get_session(session_id)

    # ── Streaming ingestion ─────────────────────────────────────────────────

    async def ingest_chunk(self, session_id: str, chunk: LiveChunk) -> LivePartial | None:
        """Append one audio chunk; return the latest partial transcript.

        Rejects chunks over ``max_chunk_bytes`` and raises
        :class:`LiveRateLimitExceeded` when the user's token bucket is empty.
        """
        if len(chunk.data) > self.max_chunk_bytes:
            raise ValueError(f"chunk exceeds max_chunk_bytes={self.max_chunk_bytes}")

        session = await self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown live session: {session_id}")
        if not self.rate_limiter.allow(self._rate_key(session.user_id)):
            raise LiveRateLimitExceeded("live transcription rate limit exceeded")

        if chunk.received_at is None:
            chunk.received_at = datetime.now(timezone.utc)
        if chunk.format is LiveChunkFormat.PCM16K and chunk.data.startswith(_WEBM_MAGIC):
            chunk.format = LiveChunkFormat.WEBM_OPUS
        session.chunks.append(chunk)

        # Incremental STT: transcribe the session's accumulated audio and
        # emit the next monotonic partial.
        audio = self._assemble_audio(session)
        result = await self.transcription_service.transcribe(audio, self._filename_for(session))
        partial = LivePartial(
            sequence=len(session.partials) + 1,
            text=result.text,
            timestamp=datetime.now(timezone.utc),
            is_final=False,
        )
        session.partials.append(partial)
        session.updated_at = partial.timestamp
        await self._save(session)
        return partial

    async def get_partials(self, session_id: str) -> list[LivePartial]:
        """Return partial transcripts with strictly increasing sequences."""
        session = await self.get_session(session_id)
        if session is None:
            return []
        return sorted(session.partials, key=lambda p: p.sequence)

    # ── Finalize / fallback ─────────────────────────────────────────────────

    async def finalize(
        self,
        session_id: str,
        *,
        language: str | None = None,
    ) -> LiveTranscriptResponse:
        """Run the full pipeline and persist the meeting record.

        Concatenates the session's audio, transcribes via
        ``TranscriptionService``, extracts via ``ExtractionService``, updates
        the meeting row (transcript + summary), and marks the session
        finalized.
        """
        session = await self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown live session: {session_id}")
        if not self.rate_limiter.allow(self._rate_key(session.user_id)):
            raise LiveRateLimitExceeded("live transcription rate limit exceeded")

        audio = self._assemble_audio(session)
        result = await self.transcription_service.transcribe(
            audio, self._filename_for(session), language
        )
        extraction = await self.extraction_service.extract(result.text, mode=MeetingMode.GENERAL)
        await self._persist_meeting(
            meeting_id=session.meeting_id,
            user_id=session.user_id,
            team_id=session.team_id,
            filename=self._filename_for(session),
            mode="general",
            transcript=result.text,
            extraction=extraction,
            create_if_missing=False,
        )

        session.status = LiveSessionStatus.FINALIZED
        session.updated_at = datetime.now(timezone.utc)
        await self._save(session)
        return LiveTranscriptResponse(
            session_id=session.id,
            meeting_id=session.meeting_id,
            transcript=result.text,
            summary=extraction.summary,
            action_items=extraction.action_items,
            decisions=extraction.decisions,
            key_points=extraction.key_points,
            chunk_count=len(session.chunks),
            partial_count=len(session.partials),
            duration_seconds=result.duration_seconds,
        )

    async def transcribe_file(
        self,
        audio_bytes: bytes,
        filename: str,
        *,
        user_id: str,
        team_id: str | None = None,
        meeting_id: str | None = None,
        mode: str = "general",
        language: str | None = None,
    ) -> LiveTranscriptResponse:
        """REST fallback: transcribe a full audio file (same result shape).

        Creates the meeting record with transcript + summary. Raises
        :class:`LiveRateLimitExceeded` when the user's bucket is empty.
        """
        if not self.rate_limiter.allow(self._rate_key(user_id)):
            raise LiveRateLimitExceeded("live transcription rate limit exceeded")

        result = await self.transcription_service.transcribe(audio_bytes, filename, language)
        try:
            meeting_mode = MeetingMode(mode)
        except ValueError:
            meeting_mode = MeetingMode.GENERAL
        extraction = await self.extraction_service.extract(result.text, mode=meeting_mode)

        resolved_meeting_id = meeting_id or str(uuid4())
        await self._persist_meeting(
            meeting_id=resolved_meeting_id,
            user_id=user_id,
            team_id=team_id,
            filename=filename,
            mode=mode,
            transcript=result.text,
            extraction=extraction,
            create_if_missing=True,
        )
        return LiveTranscriptResponse(
            meeting_id=resolved_meeting_id,
            transcript=result.text,
            summary=extraction.summary,
            action_items=extraction.action_items,
            decisions=extraction.decisions,
            key_points=extraction.key_points,
            chunk_count=0,
            partial_count=0,
            duration_seconds=result.duration_seconds,
        )

    # ── Persistence helpers ─────────────────────────────────────────────────

    async def _load_row(self, session_id: str) -> LiveSessionRecord | None:
        async for db in get_db_session():
            return await db.get(LiveSessionRecord, session_id)
        return None

    async def _save(self, session: LiveSession) -> None:
        """Upsert the session row; explicit commit (see repo test pattern)."""
        async for db in get_db_session():
            row = await db.get(LiveSessionRecord, session.id)
            if row is None:
                row = LiveSessionRecord(id=session.id)
                db.add(row)
            self._apply_to_row(session, row)
            await db.commit()

    def _apply_to_row(self, session: LiveSession, row: LiveSessionRecord) -> None:
        row.meeting_id = session.meeting_id
        row.user_id = session.user_id
        row.team_id = session.team_id
        row.room_id = session.room_id
        row.status = session.status.value
        row.chunks_json = json.dumps([_chunk_to_json(c) for c in session.chunks])
        row.partials_json = json.dumps([p.model_dump(mode="json") for p in session.partials])
        row.retention_days = session.retention_days
        row.hipaa = session.hipaa
        row.phi_classification = session.phi_classification

    def _row_to_session(self, row: LiveSessionRecord) -> LiveSession:
        chunks = [_chunk_from_json(c) for c in json.loads(row.chunks_json or "[]")]
        partials = [LivePartial.model_validate(p) for p in json.loads(row.partials_json or "[]")]
        return LiveSession(
            id=row.id,
            meeting_id=row.meeting_id,
            user_id=row.user_id,
            team_id=row.team_id,
            room_id=row.room_id,
            status=LiveSessionStatus(row.status),
            chunks=chunks,
            partials=partials,
            retention_days=row.retention_days,
            hipaa=row.hipaa,
            phi_classification=row.phi_classification,
            created_at=row.created_at or datetime.now(timezone.utc),
            updated_at=row.updated_at,
        )

    async def _persist_meeting(
        self,
        *,
        meeting_id: str,
        user_id: str,
        team_id: str | None,
        filename: str,
        mode: str,
        transcript: str,
        extraction: ExtractionResult,
        create_if_missing: bool,
    ) -> None:
        """Write transcript + summary (+ extracted notes) to the meeting row.

        The Meeting model has no ``summary`` column, so the summary is
        persisted inside ``metadata_json`` (the pre-tester's documented
        decision); action items / decisions / key points are stored as JSON
        text columns, matching the existing meeting pipeline.
        """
        action_items_json = json.dumps([a.model_dump() for a in extraction.action_items])
        decisions_json = json.dumps(extraction.decisions)
        key_points_json = json.dumps(extraction.key_points)

        async for db in get_db_session():
            meeting = await db.get(Meeting, meeting_id)
            if meeting is None:
                if not create_if_missing:
                    raise KeyError(f"meeting not found: {meeting_id}")
                meeting = Meeting(
                    id=meeting_id,
                    user_id=user_id,
                    team_id=team_id,
                    filename=filename,
                    mode=mode,
                    transcript=transcript,
                )
                db.add(meeting)
            meeting.transcript = transcript
            meeting.action_items = action_items_json
            meeting.decisions = decisions_json
            meeting.key_points = key_points_json
            metadata = json.loads(meeting.metadata_json or "{}")
            metadata["summary"] = extraction.summary
            meeting.metadata_json = json.dumps(metadata)
            await db.commit()

    def _assemble_audio(self, session: LiveSession) -> bytes:
        """Concatenate chunks (by sequence); frame PCM as WAV for Whisper."""
        ordered = sorted(session.chunks, key=lambda c: c.sequence)
        if not ordered:
            return b""
        if any(c.format is LiveChunkFormat.WEBM_OPUS for c in ordered):
            return b"".join(c.data for c in ordered)
        return _pcm16_to_wav(b"".join(c.data for c in ordered))

    @staticmethod
    def _filename_for(session: LiveSession) -> str:
        fmt = session.chunks[0].format if session.chunks else LiveChunkFormat.PCM16K
        ext = "webm" if fmt is LiveChunkFormat.WEBM_OPUS else "wav"
        return f"{session.meeting_id}.{ext}"

    @staticmethod
    def _rate_key(user_id: str) -> str:
        return f"live:{user_id}"
