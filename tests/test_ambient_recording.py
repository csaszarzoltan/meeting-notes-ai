"""Pre-development TDD tests for ambient in-person recording (P0/P1 of the
In-Person Bot-Free Recording feature — analysis/analysis-brief.md).

Feature target: the browser-mic → WebSocket → Whisper → extraction → review
pipeline already exists and is tested (tests/test_live_ui.py,
tests/test_live_transcription.py). This file locks in the *ambient recording*
contract the feature adds:

- ``POST /api/v1/meetings/live/start`` — provision a draft meeting for an
  in-person session (interface tests; behavior already covered in
  test_live_ui.py).
- ``POST /api/v1/meetings/live/upload`` — full-audio REST fallback for the
  in-person batch path. Validation contract (routes/live_transcription.py:215-244):
  empty → 400, unsupported content-type → 415, > max_audio_size_mb → 413,
  exhausted token bucket → 429. Happy path persists a meeting row with
  transcript + summary (``_persist_meeting``).
- ``TranscriptSegment.speaker`` (P0-2) — the diarization primitive every
  downstream consumer (evidence, assignee seeding) depends on. RED until the
  model gains the field; the default must stay ``None`` for untouched callers.
- The MeetingSetup 'Record in person' card (P0-1) — there is NO JS test
  framework in frontend/package.json, so the card is validated here via the
  backend UI-glue it depends on: ``GET /app/live`` must keep serving with a
  mic-permitting Permissions-Policy (the card routes into the same live
  workspace), plus a negative source assertion that the card is still gated
  (``isAvailable`` omits 'Record in person' / disabled label present) — that
  assertion flips from RED to GREEN when the frontend card is unblocked.

Two categories:
- Interface tests — import/signature/shape checks that PASS immediately.
- Behavioral tests — assert the spec's target behavior with real return
  values; they FAIL cleanly while the feature is missing (no inverse
  NotImplementedError stubs on feature methods).

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_ambient_recording.py``.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytestmark = pytest.mark.quick

# ── Shared duck-typed AI seams (mirror tests/test_live_ui.py:25-50) ───────────


class _FakeTranscription:
    """Deterministic transcript for ambient upload tests."""

    async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None):
        from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment

        return TranscriptionResult(
            text="ambient in-person recording transcript",
            language=language or "en",
            duration_seconds=2.0,
            segments=[
                TranscriptSegment(start=0.0, end=2.0, text="ambient in-person recording transcript")
            ],
        )


class _FakeExtraction:
    """Deterministic extraction for ambient upload tests."""

    async def extract(self, transcript: str, mode=None):
        from meeting_notes_ai.models import ActionItem, ExtractionResult

        return ExtractionResult(
            summary="Ambient meeting summary",
            action_items=[ActionItem(assignee="QA", description="Review ambient capture")],
            decisions=["Approve the in-person pilot"],
            key_points=["Ambient capture works"],
        )


def _token(user_id: str) -> str:
    from meeting_notes_ai.auth import create_access_token

    return asyncio.run(create_access_token(user_id))


def _auth_headers(user_id: str = "test-user-id") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _fetch_meeting(meeting_id: str):
    """Fetch a meeting row by id (real DB round-trip)."""

    async def _fetch():
        from sqlalchemy import select

        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        async for session in get_db_session():
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            return result.scalar_one_or_none()
        return None

    return asyncio.run(_fetch())


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmbientRecordingInterface:
    """Routes, handler signatures, and response shapes for ambient capture."""

    def test_start_route_registered(self):
        """POST /api/v1/meetings/live/start must exist (draft meeting for in-person)."""
        from meeting_notes_ai.routes.live_transcription import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/start") and "POST" in methods:
                return
        pytest.fail("POST /api/v1/meetings/live/start route not found")

    def test_upload_route_registered(self):
        """POST /api/v1/meetings/live/upload must exist (batch in-person audio)."""
        from meeting_notes_ai.routes.live_transcription import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/upload") and "POST" in methods:
                return
        pytest.fail("POST /api/v1/meetings/live/upload route not found")

    def test_upload_handler_signature(self):
        """Handler must take file/user/db/service dependencies."""
        from meeting_notes_ai.routes.live_transcription import upload_live_audio

        params = inspect.signature(upload_live_audio).parameters
        for required in ("file", "user", "db", "service"):
            assert required in params, f"upload_live_audio missing '{required}' param"

    def test_upload_handler_is_async(self):
        from meeting_notes_ai.routes.live_transcription import upload_live_audio

        assert inspect.iscoroutinefunction(upload_live_audio)

    def test_live_router_wired_into_app(self):
        """The live router must be included in the app (ambient uses /live/*)."""
        from meeting_notes_ai.main import app
        from meeting_notes_ai.routes.live_transcription import router as live_router

        included = [r for r in app.routes if getattr(r, "original_router", None) is live_router]
        assert included, "live_transcription router is not wired into the app"

    def test_transcript_segment_speaker_field_exists(self):
        """P0-2: TranscriptSegment must gain a 'speaker' field."""
        from meeting_notes_ai.models import TranscriptSegment

        assert "speaker" in TranscriptSegment.model_fields, (
            "TranscriptSegment.speaker missing — P0-2 must add speaker: str | None = None"
        )

    def test_transcript_segment_speaker_defaults_none(self):
        """P0-2: the speaker default must be None (backwards compatible)."""
        from meeting_notes_ai.models import TranscriptSegment

        seg = TranscriptSegment(start=0.0, end=1.0, text="hello")
        assert seg.speaker is None, "speaker must default to None for untouched callers"

    def test_supported_audio_formats_include_webm_wav(self):
        """The in-person upload path must accept the formats MediaRecorder emits."""
        from meeting_notes_ai.config import settings

        assert "audio/webm" in settings.SUPPORTED_AUDIO_FORMATS
        assert "audio/wav" in settings.SUPPORTED_AUDIO_FORMATS


class TestMeetingSetupCardGlue:
    """The 'Record in person' card has no JS test framework (frontend/package.json
    has no vitest/jest), so its backend glue is validated here: the /app/live
    route it routes into must keep serving with a mic-permitting policy, and the
    card's availability gate must admit 'Record in person' after P0-1."""

    @pytest.fixture
    def client(self, _setup_test_db):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.main import app

        return TestClient(app)

    def test_live_app_route_returns_200(self, client):
        """The in-person card routes into the same live workspace."""
        resp = client.get("/app/live")
        assert resp.status_code == 200

    def test_live_app_permissions_policy_allows_microphone(self, client):
        """Ambient capture needs the mic; the live page must keep allowing it."""
        resp = client.get("/app/live")
        policy = resp.headers["Permissions-Policy"]
        assert "microphone" in policy, "Permissions-Policy must permit the microphone"

    def test_live_app_csp_allows_websocket(self, client):
        """In-person audio streams over the same WS; CSP must keep ws:."""
        resp = client.get("/app/live")
        csp = resp.headers["Content-Security-Policy"]
        assert "ws:" in csp

    def test_meeting_setup_gate_admits_record_in_person(self):
        """P0-1: 'Record in person' must be in the card's isAvailable gate.

        Reads the source file (frontend/src/workspace/MeetingSetup.tsx) — the
        only observable surface of the pure-frontend gate until a JS test
        framework exists. RED while ``isAvailable`` only admits
        'Record live' / 'Upload recording'; flips GREEN when P0-1 lands.
        """
        source = _read_meeting_setup_source()
        assert "Record in person" in source, "card entry missing from MeetingSetup"
        # The gate is currently `capture === 'Record live' || capture === 'Upload recording'`
        # (MeetingSetup.tsx:8). P0-1 must include 'Record in person'.
        gate_line = next(
            (line for line in source.splitlines() if "isAvailable" in line and "capture" in line),
            "",
        )
        assert gate_line, "could not locate the isAvailable gate expression"
        assert "Record in person" in gate_line, (
            "'Record in person' not admitted by isAvailable gate — P0-1 must add it "
            f"(gate: {gate_line.strip()})"
        )

    def test_meeting_setup_disabled_label_removed(self):
        """P0-1: the '…is not available yet' disabled label must be gone.

        RED while MeetingSetup.tsx:10 renders
        ``{capture} is not available yet`` for the in-person card.
        """
        source = _read_meeting_setup_source()
        assert "is not available yet" not in source, (
            "'Record in person is not available yet' label still present — P0-1 must remove it"
        )


def _read_meeting_setup_source() -> str:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "frontend" / "src" / "workspace" / "MeetingSetup.tsx"
    return path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — FAIL cleanly while the feature is missing
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client(_setup_test_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from meeting_notes_ai.config import settings
    from meeting_notes_ai.main import app

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
    return TestClient(app)


@pytest.fixture
def ambient_service(_setup_test_db):
    from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

    return LiveTranscriptionService(
        transcription_service=_FakeTranscription(),
        extraction_service=_FakeExtraction(),
    )


@pytest.fixture
def override_service(client, ambient_service):
    """Swap get_live_service for the fake-backed service (test_live_ui.py:159)."""
    from meeting_notes_ai.main import app
    from meeting_notes_ai.routes.live_transcription import get_live_service

    app.dependency_overrides[get_live_service] = lambda: ambient_service
    yield ambient_service
    app.dependency_overrides.pop(get_live_service, None)


class TestAmbientUploadValidation:
    """POST /api/v1/meetings/live/upload — validation contract
    (routes/live_transcription.py:215-244)."""

    URL = "/api/v1/meetings/live/upload"

    def test_upload_requires_auth(self, client, override_service):
        resp = client.post(
            self.URL,
            files={"file": ("inperson.wav", b"\x00" * 3200, "audio/wav")},
        )
        assert resp.status_code == 401

    def test_empty_audio_rejected_400(self, client, override_service):
        """Empty upload must be rejected with 400 (route :225)."""
        resp = client.post(
            self.URL,
            files={"file": ("empty.wav", b"", "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400, (
            f"empty audio must be rejected with 400, got {resp.status_code}"
        )

    def test_wrong_content_type_rejected_415(self, client, override_service):
        """Non-audio content-type must be rejected with 415 (route :229)."""
        resp = client.post(
            self.URL,
            files={"file": ("notes.txt", b"not audio", "text/plain")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 415, (
            f"wrong content-type must be rejected with 415, got {resp.status_code}"
        )

    def test_oversize_audio_rejected_413(self, client, override_service, monkeypatch):
        """Audio over max_audio_size_mb must be rejected with 413 (route :234)."""
        from meeting_notes_ai.config import settings

        monkeypatch.setattr(settings, "max_audio_size_mb", 1)
        big = b"x" * (2 * 1024 * 1024)  # 2 MB > 1 MB cap
        resp = client.post(
            self.URL,
            files={"file": ("big.wav", big, "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 413, (
            f"oversize audio must be rejected with 413, got {resp.status_code}"
        )

    def test_rate_limited_upload_rejected_429(self, client, _setup_test_db):
        """Exhausted token bucket must map to HTTP 429 (route :243)."""
        from meeting_notes_ai.main import app
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
        from meeting_notes_ai.routes.live_transcription import get_live_service
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
            rate_limiter=TokenBucketRateLimiter(capacity=1, fill_rate=0.001),
        )
        app.dependency_overrides[get_live_service] = lambda: service
        try:
            files = {"file": ("live.wav", b"\x00" * 3200, "audio/wav")}
            headers = _auth_headers()
            first = client.post(self.URL, files=files, headers=headers)
            assert first.status_code == 200, first.text
            second = client.post(self.URL, files=files, headers=headers)
            assert second.status_code == 429, (
                f"rate-limited upload must be rejected with 429, got {second.status_code}"
            )
        finally:
            app.dependency_overrides.pop(get_live_service, None)


class TestAmbientUploadHappyPath:
    """Uploading a valid in-person recording persists a meeting with transcript
    + summary (via transcribe_file → _persist_meeting)."""

    URL = "/api/v1/meetings/live/upload"

    def test_upload_persists_meeting_with_transcript_and_summary(
        self, client, override_service
    ):
        """Happy path: 200 + LiveTranscriptResponse + persisted meeting row."""
        payload = b"\x00" * 3200
        resp = client.post(
            self.URL,
            files={"file": ("inperson.wav", payload, "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["meeting_id"], "response must carry a meeting_id"
        assert data["transcript"] == "ambient in-person recording transcript"
        assert data["summary"] == "Ambient meeting summary"
        assert data["action_items"][0]["description"] == "Review ambient capture"
        assert data["decisions"] == ["Approve the in-person pilot"]
        assert data["duration_seconds"] == 2.0

        row = _fetch_meeting(data["meeting_id"])
        assert row is not None, "upload must persist a meeting row"
        assert row.transcript == "ambient in-person recording transcript"
        meta = {}
        if row.metadata_json:
            import json

            meta = json.loads(row.metadata_json)
        assert meta.get("summary") == "Ambient meeting summary"

    def test_upload_rejects_empty_via_duck_typed_service(self, client, ambient_service):
        """Service-level guard: transcribe_file of empty bytes is not a valid
        ambient capture (the route already rejects empties; the service must
        not invent content either)."""
        result = asyncio.run(
            ambient_service.transcribe_file(b"", "empty.wav", user_id="test-user-id")
        )
        # A real implementation may transcribe silence; but it must NOT fabricate
        # the fake's canned transcript for an empty buffer.
        assert result.transcript == "", (
            f"empty audio must not produce a fabricated transcript, got {result.transcript!r}"
        )


class TestAmbientStartEndpoint:
    """POST /api/v1/meetings/live/start — provision a draft meeting for the
    in-person session before the mic/WS flow (acceptance #1)."""

    URL = "/api/v1/meetings/live/start"

    def test_start_requires_auth(self, client):
        resp = client.post(self.URL)
        assert resp.status_code == 401

    def test_start_creates_draft_meeting(self, client):
        """Authenticated start provisions a meeting row and returns its id."""
        resp = client.post(self.URL, headers=_auth_headers())
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["meeting_id"]
        assert data["status"] == "live_ready"

        row = _fetch_meeting(data["meeting_id"])
        assert row is not None, "start must persist a draft meeting row"
        assert row.user_id == "test-user-id"
