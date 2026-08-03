"""Live transcription service — TDD RED-phase stub contract.

The constructor and exception types are *real* (interface). Every behavior
method raises ``NotImplementedError`` until the developer implements it
against ``tests/test_live_session.py``:

- ``create_session`` / ``get_session`` / ``resume_session`` — session
  lifecycle; a session must survive client disconnects and be resumable.
- ``ingest_chunk`` / ``get_partials`` — streaming audio ingestion producing
  incremental partial transcripts with monotonic sequence numbers and
  timestamps.
- ``finalize`` — runs the accumulated audio through the existing
  ``services/transcription.py`` pipeline, extracts action items/decisions via
  the existing LLM ``services/extraction.py``, and persists the meeting record
  (transcript + summary).
- ``transcribe_file`` — REST fallback for a full audio upload, returning the
  same transcript shape.

Rate limiting reuses the existing ``TokenBucketRateLimiter`` keyed per user;
an exhausted bucket raises :class:`LiveRateLimitExceeded`, which the route
layer maps to HTTP 429.
"""

from __future__ import annotations

from meeting_notes_ai.live_session import (
    LiveChunk,
    LivePartial,
    LiveSession,
    LiveTranscriptResponse,
)
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.transcription import TranscriptionService


class LiveRateLimitExceeded(Exception):
    """Raised when a user's live-transcription token bucket is empty."""


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
        raise NotImplementedError("live_session.create_session (TDD RED phase)")

    async def get_session(self, session_id: str) -> LiveSession | None:
        """Return the session by id, or None if it does not exist."""
        raise NotImplementedError("live_session.get_session (TDD RED phase)")

    async def resume_session(self, session_id: str) -> LiveSession | None:
        """Rehydrate a session after a client disconnect (same id/state)."""
        raise NotImplementedError("live_session.resume_session (TDD RED phase)")

    # ── Streaming ingestion ─────────────────────────────────────────────────

    async def ingest_chunk(self, session_id: str, chunk: LiveChunk) -> LivePartial | None:
        """Append one audio chunk; return the latest partial transcript.

        Rejects chunks over ``max_chunk_bytes`` and raises
        :class:`LiveRateLimitExceeded` when the user's token bucket is empty.
        """
        raise NotImplementedError("live_session.ingest_chunk (TDD RED phase)")

    async def get_partials(self, session_id: str) -> list[LivePartial]:
        """Return partial transcripts with strictly increasing sequences."""
        raise NotImplementedError("live_session.get_partials (TDD RED phase)")

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
        raise NotImplementedError("live_session.finalize (TDD RED phase)")

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
        raise NotImplementedError("live_session.transcribe_file (TDD RED phase)")
