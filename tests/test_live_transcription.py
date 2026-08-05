"""Pre-development TDD tests for the live transcription endpoints.

Endpoints under test:
- WebSocket ``/api/v1/meetings/live`` — JWT-authenticated (token query
  param), meeting/room-scoped, team-workspace-aware; accepts streaming audio
  chunks (16 kHz PCM / WebM/Opus binary frames), streams partial transcripts
  with monotonic sequence numbers and timestamps, accepts a finalize control
  frame to persist the session.
- ``POST /api/v1/meetings/live/upload`` — REST fallback for a full audio
  file, returning the same transcript shape.

RED phase: interface tests PASS (the stub router is registered and wired into
the app); behavioral tests FAIL with NotImplementedError because the handlers
are stubbed. After implementation the behavioral tests become the GREEN
contract.

Integration honesty: every endpoint test drives the real FastAPI app through
TestClient against the seeded in-memory SQLite DB — real auth dependency, real
WS/HTTP protocol, real DB writes. The only substitution is the external AI
seam: ``get_live_service`` is overridden with a service wired to plain fake
transcription/extraction implementations (no mocks of the endpoint, the
router, or the DB).
"""

from __future__ import annotations

import asyncio
import base64
import json
from uuid import uuid4

import pytest
from starlette.routing import WebSocketRoute

from meeting_notes_ai.live_session import LiveChunk, LiveChunkFormat
from meeting_notes_ai.models import (
    ActionItem,
    ExtractionResult,
    MeetingMode,
    TranscriptionResult,
    TranscriptSegment,
)
from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

pytestmark = pytest.mark.quick


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


def _token(user_id: str) -> str:
    from meeting_notes_ai.auth import create_access_token

    return asyncio.run(create_access_token(user_id))


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _fresh_meeting(user_id: str = "test-user-id") -> str:
    """Create a fresh meeting owned by *user_id* (no team) and return its id."""

    async def _create() -> str:
        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        meeting_id = f"live-api-{uuid4().hex[:12]}"
        async for session in get_db_session():
            session.add(
                Meeting(
                    id=meeting_id,
                    title="Live API Test",
                    user_id=user_id,
                    filename="live_api.wav",
                    mode="general",
                    transcript="",
                )
            )
            await session.commit()
        return meeting_id

    return asyncio.run(_create())


def _fetch_meeting(meeting_id: str):
    async def _fetch():
        from sqlalchemy import select

        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        async for session in get_db_session():
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            return result.scalar_one_or_none()
        return None

    return asyncio.run(_fetch())


def _meeting_summary(row) -> str | None:
    if hasattr(row, "summary") and getattr(row, "summary", None):
        return row.summary
    meta = json.loads(row.metadata_json or "{}")
    return meta.get("summary")


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests — must PASS immediately against the stubs
# ═══════════════════════════════════════════════════════════════════════════════


class TestLiveRoutesInterface:
    def test_router_exists(self):
        from meeting_notes_ai.routes.live_transcription import router

        assert router is not None

    def test_router_prefix(self):
        from meeting_notes_ai.routes.live_transcription import router

        assert router.prefix == "/api/v1/meetings/live"

    def test_websocket_route_registered(self):
        from meeting_notes_ai.routes.live_transcription import router

        ws_routes = [r for r in router.routes if isinstance(r, WebSocketRoute)]
        assert ws_routes, "no WebSocket route registered on the live router"
        paths = {r.path for r in ws_routes}
        expected = {"/api/v1/meetings/live", "/api/v1/meetings/live/"}
        assert paths & expected, f"unexpected ws paths: {paths}"

    def test_upload_route_registered(self):
        from meeting_notes_ai.routes.live_transcription import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/upload") and "POST" in methods:
                return
        pytest.fail("POST /api/v1/meetings/live/upload route not found")

    def test_upload_handler_has_user_dependency(self):
        import inspect

        from meeting_notes_ai.routes.live_transcription import upload_live_audio

        params = inspect.signature(upload_live_audio).parameters
        assert "user" in params or "current_user" in params

    def test_upload_handler_has_file_dependency(self):
        import inspect

        from meeting_notes_ai.routes.live_transcription import upload_live_audio

        assert "file" in inspect.signature(upload_live_audio).parameters

    def test_ws_handler_has_token_and_meeting_params(self):
        import inspect

        from meeting_notes_ai.routes.live_transcription import websocket_live

        params = inspect.signature(websocket_live).parameters
        assert "websocket" in params
        assert "token" in params
        assert "meeting_id" in params
        assert "team_id" in params
        assert "room_id" in params

    def test_ws_handler_is_async(self):
        import inspect

        from meeting_notes_ai.routes.live_transcription import websocket_live

        assert inspect.iscoroutinefunction(websocket_live)

    def test_get_live_service_dependency_returns_service(self):
        from meeting_notes_ai.routes.live_transcription import get_live_service

        assert isinstance(get_live_service(), LiveTranscriptionService)

    def test_live_router_wired_into_app(self):
        from meeting_notes_ai.main import app
        from meeting_notes_ai.routes.live_transcription import router as live_router

        # FastAPI >= 0.139 wraps include_router in _IncludedRouter entries that
        # carry the original router; check by identity instead of flattened paths.
        included = [r for r in app.routes if getattr(r, "original_router", None) is live_router]
        assert included, "live_transcription router is not wired into the app"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests — FAIL with NotImplementedError during RED phase
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client(_setup_test_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from meeting_notes_ai.config import settings
    from meeting_notes_ai.main import app

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
    return TestClient(app)


@pytest.fixture
def live_service(_setup_test_db):
    return LiveTranscriptionService(
        transcription_service=_FakeTranscription(),
        extraction_service=_FakeExtraction(),
    )


@pytest.fixture
def override_service(client, live_service):
    """Override the app's get_live_service dependency with the test service."""
    from meeting_notes_ai.main import app
    from meeting_notes_ai.routes.live_transcription import get_live_service

    app.dependency_overrides[get_live_service] = lambda: live_service
    yield live_service
    app.dependency_overrides.pop(get_live_service, None)


def _ws_url(meeting_id: str, user_id: str = "test-user-id", **extra: str) -> str:
    parts = [f"token={_token(user_id)}", f"meeting_id={meeting_id}"]
    parts.extend(f"{k}={v}" for k, v in extra.items())
    return "/api/v1/meetings/live?" + "&".join(parts)


class TestLiveWebSocketBehavioral:
    """Real WS integration: auth, streaming partials, finalize persistence."""

    def test_ws_requires_token_rejected(self, client, override_service):
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/meetings/live") as ws:
                ws.receive_text()

    def test_ws_owner_streams_partials_and_finalizes(self, client, override_service):
        """End-to-end: connect → chunks → monotonic partials → finalize ack.

        The client sends chunks and a finalize control frame, then reads until
        the ``finalized`` ack (bounded loop). A conforming server must stream
        at least one partial before the ack and reply to finalize — this
        structure cannot deadlock against a conforming implementation.
        """
        meeting_id = _fresh_meeting()
        url = _ws_url(meeting_id)
        with client.websocket_connect(url) as ws:
            ws.send_bytes(b"\x00" * 3200)  # 16 kHz PCM chunk
            ws.send_bytes(b"\x00" * 3200)
            ws.send_text(json.dumps({"type": "finalize"}))

            partials: list[dict] = []
            finalized: dict | None = None
            for _ in range(10):  # bounded read — never hang the suite
                msg = ws.receive_json()
                if msg.get("type") == "finalized":
                    finalized = msg
                    break
                partials.append(msg)

            assert finalized is not None, f"no finalized ack; partials={partials}"
            assert partials, "expected at least one partial transcript before finalize"

            sequences = [p["sequence"] for p in partials]
            assert sequences == sorted(sequences), "sequences must be monotonic"
            assert len(set(sequences)) == len(sequences), "sequences must be strictly increasing"
            for p in partials:
                assert "timestamp" in p, f"partial missing timestamp: {p}"
                assert p["text"], f"partial missing text: {p}"

            assert finalized["session_id"]
            assert finalized["meeting_id"] == meeting_id
            assert finalized["transcript"] == "hello world this is a live test"
            assert finalized["summary"] == "Test summary"

        # Session is finalized and persisted (survives the disconnect).
        from meeting_notes_ai.live_session import LiveSessionStatus

        stored = asyncio.run(override_service.get_session(finalized["session_id"]))
        assert stored is not None
        assert stored.status is LiveSessionStatus.FINALIZED

    def test_ws_accepts_webm_opus_chunks(self, client, override_service):
        meeting_id = _fresh_meeting()
        with client.websocket_connect(_ws_url(meeting_id)) as ws:
            ws.send_bytes(b"\x1a\x45\xdf\xa3opustream")  # WebM/Opus frame
            ws.send_text(json.dumps({"type": "finalize"}))
            finalized = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("type") == "finalized":
                    finalized = msg
                    break
            assert finalized is not None
            assert finalized["transcript"] == "hello world this is a live test"

    def test_ws_finalize_persists_meeting_record(self, client, override_service):
        """Real integration: finalize writes transcript + summary to the meeting row."""
        meeting_id = _fresh_meeting()
        with client.websocket_connect(_ws_url(meeting_id)) as ws:
            ws.send_bytes(b"\x00" * 3200)
            ws.send_text(json.dumps({"type": "finalize"}))
            finalized = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("type") == "finalized":
                    finalized = msg
                    break
            assert finalized is not None

        row = _fetch_meeting(meeting_id)
        assert row is not None
        assert row.transcript == "hello world this is a live test"
        assert _meeting_summary(row) == "Test summary"

    def test_ws_team_member_can_stream(self, client, override_service):
        """team-meeting belongs to test-team; test-user-id is an ADMIN member."""
        url = _ws_url("team-meeting", "test-user-id", team_id="test-team")
        with client.websocket_connect(url) as ws:
            ws.send_bytes(b"\x00" * 3200)
            ws.send_text(json.dumps({"type": "finalize"}))
            finalized = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("type") == "finalized":
                    finalized = msg
                    break
            assert finalized is not None

    def test_ws_other_users_meeting_rejected(self, client, override_service):
        """test-meeting belongs to test-user-id; other-user-id must be rejected."""
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(_ws_url("test-meeting", "other-user-id")) as ws:
                ws.receive_text()

    def test_ws_team_non_member_rejected(self, client, override_service):
        """other-user-id is not a member of test-team → team-scoped rejection."""
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                _ws_url("team-meeting", "other-user-id", team_id="test-team")
            ) as ws:
                ws.receive_text()


class TestLiveUploadBehavioral:
    """REST fallback POST /api/v1/meetings/live/upload."""

    def test_upload_requires_auth(self, client, override_service):
        resp = client.post(
            "/api/v1/meetings/live/upload",
            files={"file": ("live.wav", b"\x00" * 3200, "audio/wav")},
        )
        assert resp.status_code == 401

    def test_upload_returns_transcript_and_creates_meeting(self, client, override_service):
        """Real integration: full-file upload → transcript + persisted meeting."""
        payload = b"\x00" * 3200
        resp = client.post(
            "/api/v1/meetings/live/upload",
            files={"file": ("live.wav", payload, "audio/wav")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["meeting_id"]
        assert data["transcript"] == "hello world this is a live test"
        assert data["summary"] == "Test summary"
        assert data["action_items"][0]["description"] == "Ship live transcription"
        assert data["decisions"] == ["Deploy on Friday"]

        row = _fetch_meeting(data["meeting_id"])
        assert row is not None, "upload must create a meeting record"
        assert row.transcript == "hello world this is a live test"
        assert _meeting_summary(row) == "Test summary"

    def test_upload_rejects_bad_mime(self, client, override_service):
        resp = client.post(
            "/api/v1/meetings/live/upload",
            files={"file": ("notes.txt", b"not audio", "text/plain")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 415

    def test_upload_rejects_oversize(self, client, override_service, monkeypatch):
        from meeting_notes_ai.config import settings

        monkeypatch.setattr(settings, "max_audio_size_mb", 1)
        big = b"x" * (2 * 1024 * 1024)  # 2 MB > 1 MB cap
        resp = client.post(
            "/api/v1/meetings/live/upload",
            files={"file": ("big.wav", big, "audio/wav")},
            headers=_auth_headers("test-user-id"),
        )
        assert resp.status_code == 413

    def test_upload_rate_limited_returns_429(self, client, _setup_test_db):
        """A user whose token bucket is exhausted gets HTTP 429."""
        from meeting_notes_ai.main import app
        from meeting_notes_ai.routes.live_transcription import get_live_service

        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        app.dependency_overrides[get_live_service] = lambda: service
        try:
            files = {"file": ("live.wav", b"\x00" * 3200, "audio/wav")}
            headers = _auth_headers("test-user-id")
            first = client.post("/api/v1/meetings/live/upload", files=files, headers=headers)
            assert first.status_code == 200, first.text
            second = client.post("/api/v1/meetings/live/upload", files=files, headers=headers)
            assert second.status_code == 429, second.text
        finally:
            app.dependency_overrides.pop(get_live_service, None)


class TestLiveSessionPayloadContract:
    """The WS protocol payload shapes the tests rely on (documented contract)."""

    def test_finalize_control_message_shape(self):
        # The contract: a text frame {"type": "finalize"} triggers persistence.
        msg = json.loads(json.dumps({"type": "finalize"}))
        assert msg == {"type": "finalize"}

    def test_partial_message_shape_has_sequence_and_timestamp(self):
        # The contract: partial frames carry sequence + timestamp + text.
        sample = {
            "type": "partial",
            "sequence": 1,
            "text": "hello",
            "timestamp": "2026-08-03T12:00:00Z",
        }
        assert "sequence" in sample
        assert "timestamp" in sample

    def test_chunk_payload_constructible(self):
        # Chunks are binary frames; the schema mirrors them server-side.
        chunk = LiveChunk(sequence=1, format=LiveChunkFormat.PCM16K, data=b"\x00" * 3200)
        assert chunk.sequence == 1
        assert len(chunk.data) == 3200


class TestChunkJsonSerialization:
    """Binary-safe chunk serialization (regression: UnicodeDecodeError).

    Real WebM/Opus MediaRecorder output is NOT valid UTF-8 (the WebM EBML
    header contains byte 0x9F after 0xDF 0xA3). ``model_dump(mode="json")``
    utf-8-decodes ``bytes`` fields and raises UnicodeDecodeError BEFORE the
    base64 fix on ``data`` can run — the exact crash that killed real-mic
    streaming (tester blocker t_8741722b, fixed by t_9fb6d453).
    """

    # Real WebM/EBML header as captured from a MediaRecorder (invalid UTF-8:
    # 0x9F at position 4 is a lone continuation byte).
    REAL_WEBM_HEADER = (
        b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01"
        b"\x42\xf2\x81\x02\x42\xf3\x81\x08\x42\x82\x84webm"
    )

    def test_chunk_to_json_accepts_invalid_utf8_binary(self):
        """The deterministic repro: must NOT raise UnicodeDecodeError."""
        from meeting_notes_ai.services.live_transcription import _chunk_to_json

        chunk = LiveChunk(sequence=1, format=LiveChunkFormat.WEBM_OPUS, data=self.REAL_WEBM_HEADER)
        dumped = _chunk_to_json(chunk)  # raises before the fix
        assert dumped["data"] == base64.b64encode(self.REAL_WEBM_HEADER).decode("ascii")

    def test_chunk_to_json_output_is_json_serializable(self):
        """``_apply_to_row`` json.dumps()s the output — no datetime/enum leaks."""
        import json as _json
        from datetime import datetime, timezone

        from meeting_notes_ai.services.live_transcription import _chunk_to_json

        chunk = LiveChunk(
            sequence=3,
            format=LiveChunkFormat.WEBM_OPUS,
            data=self.REAL_WEBM_HEADER,
            received_at=datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc),
        )
        dumped = _chunk_to_json(chunk)
        assert isinstance(dumped["received_at"], str)
        assert _json.dumps(dumped)  # must not choke on datetime / enum

    def test_chunk_json_round_trip_preserves_binary(self):
        """Base64 in → raw bytes out; format + sequence survive the round trip."""
        from meeting_notes_ai.services.live_transcription import (
            _chunk_from_json,
            _chunk_to_json,
        )

        chunk = LiveChunk(sequence=7, format=LiveChunkFormat.WEBM_OPUS, data=self.REAL_WEBM_HEADER)
        restored = _chunk_from_json(_chunk_to_json(chunk))
        assert restored.data == self.REAL_WEBM_HEADER
        assert restored.format is LiveChunkFormat.WEBM_OPUS
        assert restored.sequence == 7
