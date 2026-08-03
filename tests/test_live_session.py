"""Pre-development TDD tests for the LiveSession model + live transcription service.

RED phase: interface tests PASS immediately (the stub modules are importable
and the schemas are constructible); behavioral tests FAIL with
NotImplementedError because ``services/live_transcription.py`` methods are
stubbed. After the developer implements the service, the behavioral tests
become the GREEN contract.

The behavioral tests are real integration tests where it matters: the
finalize / transcribe_file persistence tests run against the seeded in-memory
SQLite DB and exercise the existing TranscriptionService/ExtractionService
call contract via plain fake implementations at the service seam (no mocks of
the endpoint or the service itself).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from meeting_notes_ai.live_session import (
    LiveChunk,
    LiveChunkFormat,
    LivePartial,
    LiveSession,
    LiveSessionStatus,
    LiveTranscriptResponse,
)
from meeting_notes_ai.models import (
    ActionItem,
    ExtractionResult,
    MeetingMode,
    TranscriptionResult,
    TranscriptSegment,
)
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.live_transcription import (
    LiveRateLimitExceeded,
    LiveTranscriptionService,
)

pytestmark = pytest.mark.quick

# ── Plain fake implementations of the external AI seam ─────────────────────────
# These mirror the call contract of the real services (transcribe/extract) so
# the finalize pipeline can be exercised end-to-end without network calls.


class _FakeTranscription:
    async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None):
        return TranscriptionResult(
            text="hello world this is a live test",
            language=language or "en",
            duration_seconds=1.0,
            segments=[
                TranscriptSegment(start=0.0, end=1.0, text="hello world this is a live test")
            ],
        )


class _FakeExtraction:
    async def extract(self, transcript: str, mode: MeetingMode = MeetingMode.GENERAL):
        return ExtractionResult(
            summary="Test summary",
            action_items=[ActionItem(assignee="Mike", description="Ship live transcription")],
            decisions=["Deploy on Friday"],
            key_points=["Live transcription works"],
        )


def _pcm_chunk(sequence: int) -> LiveChunk:
    return LiveChunk(sequence=sequence, format=LiveChunkFormat.PCM16K, data=b"\x00" * 3200)


def _webm_chunk(sequence: int) -> LiveChunk:
    return LiveChunk(
        sequence=sequence,
        format=LiveChunkFormat.WEBM_OPUS,
        data=b"\x1a\x45\xdf\xa3opustream",
    )


async def _fetch_meeting(meeting_id: str):
    """Fetch a Meeting row from the seeded test DB."""
    from meeting_notes_ai.db.models import Meeting
    from meeting_notes_ai.db.session import get_db_session

    async for session in get_db_session():
        result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
        return result.scalar_one_or_none()
    return None


async def _create_fresh_meeting(user_id: str = "test-user-id") -> str:
    """Create a fresh meeting owned by *user_id* (no team) and return its id."""
    from meeting_notes_ai.db.models import Meeting
    from meeting_notes_ai.db.session import get_db_session

    meeting_id = f"live-{uuid4().hex[:12]}"
    async for session in get_db_session():
        session.add(
            Meeting(
                id=meeting_id,
                title="Live Session Test",
                user_id=user_id,
                filename="live_test.wav",
                mode="general",
                transcript="",
            )
        )
        await session.commit()
    return meeting_id


def _meeting_summary(row) -> str | None:
    """Resolve the persisted summary (row attribute or metadata_json)."""
    if hasattr(row, "summary") and getattr(row, "summary", None):
        return row.summary
    meta = json.loads(row.metadata_json or "{}")
    return meta.get("summary")


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests — must PASS immediately against the stubs
# ═══════════════════════════════════════════════════════════════════════════════


class TestLiveSessionStatusEnum:
    def test_values(self):
        assert LiveSessionStatus.LIVE.value == "live"
        assert LiveSessionStatus.FINALIZED.value == "finalized"


class TestLiveChunkFormatEnum:
    def test_values(self):
        assert LiveChunkFormat.PCM16K.value == "pcm16k"
        assert LiveChunkFormat.WEBM_OPUS.value == "webm_opus"


class TestLiveChunkModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel

        assert issubclass(LiveChunk, BaseModel)

    def test_fields_exist(self):
        fields = LiveChunk.model_fields
        assert "sequence" in fields
        assert "format" in fields
        assert "data" in fields
        assert "received_at" in fields

    def test_defaults(self):
        chunk = LiveChunk()
        assert chunk.sequence == 0
        assert chunk.format is LiveChunkFormat.PCM16K
        assert chunk.data == b""
        assert chunk.received_at is None

    def test_construct_with_pcm16k(self):
        chunk = LiveChunk(sequence=1, format=LiveChunkFormat.PCM16K, data=b"\x00" * 1600)
        assert chunk.sequence == 1
        assert chunk.format is LiveChunkFormat.PCM16K
        assert len(chunk.data) == 1600


class TestLivePartialModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel

        assert issubclass(LivePartial, BaseModel)

    def test_fields_exist(self):
        fields = LivePartial.model_fields
        assert "sequence" in fields
        assert "text" in fields
        assert "timestamp" in fields
        assert "is_final" in fields

    def test_defaults(self):
        partial = LivePartial()
        assert partial.sequence == 0
        assert partial.text == ""
        assert partial.timestamp is None
        assert partial.is_final is False


class TestLiveSessionModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel

        assert issubclass(LiveSession, BaseModel)

    def test_fields_exist(self):
        fields = LiveSession.model_fields
        expected = {
            "id",
            "meeting_id",
            "user_id",
            "team_id",
            "room_id",
            "status",
            "chunks",
            "partials",
            "retention_days",
            "hipaa",
            "phi_classification",
            "created_at",
            "updated_at",
        }
        assert expected <= set(fields), f"missing fields: {expected - set(fields)}"

    def test_default_status_is_live(self):
        session = LiveSession(meeting_id="m1", user_id="u1")
        assert session.status is LiveSessionStatus.LIVE

    def test_chunks_and_partials_default_to_empty(self):
        session = LiveSession(meeting_id="m1", user_id="u1")
        assert session.chunks == []
        assert session.partials == []

    def test_retention_and_hipaa_defaults(self):
        session = LiveSession(meeting_id="m1", user_id="u1")
        assert session.retention_days is None
        assert session.hipaa is False
        assert session.phi_classification is None

    def test_team_and_room_default_to_none(self):
        session = LiveSession(meeting_id="m1", user_id="u1")
        assert session.team_id is None
        assert session.room_id is None

    def test_construct_with_full_metadata(self):
        now = datetime.now(timezone.utc)
        session = LiveSession(
            id="sess-1",
            meeting_id="m1",
            user_id="u1",
            team_id="team-1",
            room_id="room-1",
            retention_days=365,
            hipaa=True,
            phi_classification="phi",
            created_at=now,
        )
        assert session.id == "sess-1"
        assert session.retention_days == 365
        assert session.hipaa is True
        assert session.phi_classification == "phi"


class TestLiveTranscriptResponseModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel

        assert issubclass(LiveTranscriptResponse, BaseModel)

    def test_fields_exist(self):
        fields = LiveTranscriptResponse.model_fields
        expected = {
            "session_id",
            "meeting_id",
            "transcript",
            "summary",
            "action_items",
            "decisions",
            "key_points",
            "chunk_count",
            "partial_count",
            "duration_seconds",
        }
        assert expected <= set(fields), f"missing fields: {expected - set(fields)}"

    def test_defaults(self):
        resp = LiveTranscriptResponse(meeting_id="m1")
        assert resp.transcript == ""
        assert resp.summary == ""
        assert resp.action_items == []
        assert resp.decisions == []
        assert resp.key_points == []
        assert resp.chunk_count == 0
        assert resp.duration_seconds == 0.0

    def test_construct_with_content(self):
        resp = LiveTranscriptResponse(
            meeting_id="m1",
            transcript="hello",
            summary="sum",
            action_items=[ActionItem(assignee="A", description="B")],
            decisions=["d1"],
            chunk_count=3,
            partial_count=2,
            duration_seconds=1.5,
        )
        assert resp.summary == "sum"
        assert resp.action_items[0].assignee == "A"
        assert resp.decisions == ["d1"]
        assert resp.chunk_count == 3
        assert resp.partial_count == 2


class TestLiveTranscriptionServiceInterface:
    def test_class_importable(self):
        assert LiveTranscriptionService is not None

    def test_rate_limit_exception_importable(self):
        assert issubclass(LiveRateLimitExceeded, Exception)

    def test_init_accepts_service_and_limiter_deps(self):
        import inspect

        sig = inspect.signature(LiveTranscriptionService.__init__)
        params = sig.parameters
        assert "transcription_service" in params
        assert "extraction_service" in params
        assert "rate_limiter" in params

    def test_init_defaults_to_real_limiter(self):
        service = LiveTranscriptionService()
        assert isinstance(service.rate_limiter, TokenBucketRateLimiter)

    def test_init_accepts_injected_deps(self):
        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        assert service.rate_limiter.capacity == 1

    def test_methods_exist(self):
        for name in (
            "create_session",
            "get_session",
            "resume_session",
            "ingest_chunk",
            "get_partials",
            "finalize",
            "transcribe_file",
        ):
            assert hasattr(LiveTranscriptionService, name), f"missing method {name}"

    def test_methods_are_async(self):
        import inspect

        for name in (
            "create_session",
            "get_session",
            "resume_session",
            "ingest_chunk",
            "get_partials",
            "finalize",
            "transcribe_file",
        ):
            assert inspect.iscoroutinefunction(getattr(LiveTranscriptionService, name)), name

    def test_create_session_signature(self):
        import inspect

        sig = inspect.signature(LiveTranscriptionService.create_session)
        params = sig.parameters
        assert "meeting_id" in params
        assert "user_id" in params
        assert "team_id" in params
        assert "room_id" in params
        assert "retention_days" in params
        assert "hipaa" in params
        assert "phi_classification" in params

    def test_ingest_chunk_signature(self):
        import inspect

        sig = inspect.signature(LiveTranscriptionService.ingest_chunk)
        params = sig.parameters
        assert "session_id" in params
        assert "chunk" in params

    def test_finalize_signature(self):
        import inspect

        sig = inspect.signature(LiveTranscriptionService.finalize)
        params = sig.parameters
        assert "session_id" in params
        assert "language" in params
        assert sig.return_annotation == "LiveTranscriptResponse"

    def test_transcribe_file_signature(self):
        import inspect

        sig = inspect.signature(LiveTranscriptionService.transcribe_file)
        params = sig.parameters
        assert "audio_bytes" in params
        assert "filename" in params
        assert "user_id" in params
        assert "meeting_id" in params
        assert sig.return_annotation == "LiveTranscriptResponse"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests — FAIL with NotImplementedError during RED phase
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def live_service(_setup_test_db):
    return LiveTranscriptionService(
        transcription_service=_FakeTranscription(),
        extraction_service=_FakeExtraction(),
    )


@pytest.fixture
def meeting_id(_setup_test_db):
    return asyncio.run(_create_fresh_meeting())


class TestLiveSessionLifecycle:
    """Session create → ingest → partials → resume → finalize contract."""

    async def test_create_session_returns_live_session(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        assert isinstance(session, LiveSession)
        assert session.meeting_id == meeting_id
        assert session.user_id == "test-user-id"
        assert session.status is LiveSessionStatus.LIVE

    async def test_ingest_chunk_appends_and_returns_partial(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        partial = await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        assert partial is not None
        assert isinstance(partial, LivePartial)
        assert partial.text  # non-empty incremental transcript

    async def test_partials_sequences_are_monotonic(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        for i in range(1, 4):
            await live_service.ingest_chunk(session.id, _pcm_chunk(i))
        partials = await live_service.get_partials(session.id)
        sequences = [p.sequence for p in partials]
        assert len(sequences) >= 2
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # strictly increasing

    async def test_partials_have_timestamps(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        partials = await live_service.get_partials(session.id)
        assert all(p.timestamp is not None for p in partials)

    async def test_accepts_webm_opus_chunks(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        partial = await live_service.ingest_chunk(session.id, _webm_chunk(1))
        assert partial is not None

    async def test_resume_session_restores_state(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        resumed = await live_service.resume_session(session.id)
        assert resumed is not None
        assert resumed.id == session.id
        assert resumed.meeting_id == meeting_id
        assert resumed.status is LiveSessionStatus.LIVE
        assert len(resumed.chunks) == len(session.chunks)

    async def test_resume_unknown_session_returns_none(self, live_service):
        assert await live_service.resume_session("no-such-session") is None

    async def test_finalize_marks_session_finalized(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        await live_service.finalize(session.id)
        stored = await live_service.get_session(session.id)
        assert stored is not None
        assert stored.status is LiveSessionStatus.FINALIZED

    async def test_finalize_returns_transcript_response(self, live_service, meeting_id):
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        result = await live_service.finalize(session.id)
        assert isinstance(result, LiveTranscriptResponse)
        assert result.meeting_id == meeting_id
        assert result.transcript == "hello world this is a live test"
        assert result.summary == "Test summary"
        assert result.action_items[0].description == "Ship live transcription"
        assert result.decisions == ["Deploy on Friday"]

    async def test_finalize_persists_meeting_record(self, live_service, meeting_id):
        """Real integration: finalize writes transcript + summary to the meeting row."""
        session = await live_service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        await live_service.ingest_chunk(session.id, _pcm_chunk(1))
        await live_service.finalize(session.id)
        row = await _fetch_meeting(meeting_id)
        assert row is not None
        assert row.transcript == "hello world this is a live test"
        assert _meeting_summary(row) == "Test summary"

    async def test_transcribe_file_returns_response(self, live_service, meeting_id):
        result = await live_service.transcribe_file(
            b"\x00" * 3200,
            "live_upload.wav",
            user_id="test-user-id",
            meeting_id=meeting_id,
        )
        assert isinstance(result, LiveTranscriptResponse)
        assert result.meeting_id == meeting_id
        assert result.transcript == "hello world this is a live test"
        assert result.summary == "Test summary"

    async def test_transcribe_file_creates_meeting_record(self, live_service, meeting_id):
        """Real integration: upload fallback creates a meeting with transcript + summary."""
        result = await live_service.transcribe_file(
            b"\x00" * 3200,
            "live_upload.wav",
            user_id="test-user-id",
        )
        row = await _fetch_meeting(result.meeting_id)
        assert row is not None
        assert row.transcript == "hello world this is a live test"
        assert _meeting_summary(row) == "Test summary"

    async def test_ingest_rate_limited_raises(self, _setup_test_db):
        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        meeting = await _create_fresh_meeting()
        session = await service.create_session(meeting_id=meeting, user_id="test-user-id")
        await service.ingest_chunk(session.id, _pcm_chunk(1))  # consumes the only token
        with pytest.raises(LiveRateLimitExceeded):
            await service.ingest_chunk(session.id, _pcm_chunk(2))

    async def test_transcribe_file_rate_limited_raises(self, _setup_test_db):
        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        await service.transcribe_file(b"\x00" * 3200, "a.wav", user_id="test-user-id")
        with pytest.raises(LiveRateLimitExceeded):
            await service.transcribe_file(b"\x00" * 3200, "b.wav", user_id="test-user-id")

    async def test_rate_limit_keyed_per_user(self, _setup_test_db):
        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        await service.transcribe_file(b"\x00" * 3200, "a.wav", user_id="test-user-id")
        # A different user has their own bucket and must not be denied.
        result = await service.transcribe_file(b"\x00" * 3200, "b.wav", user_id="other-user-id")
        assert result.transcript == "hello world this is a live test"
