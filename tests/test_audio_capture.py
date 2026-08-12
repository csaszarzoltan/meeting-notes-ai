"""Pre-development tests for the ambient audio capture module (P0-A).

Contract source: ``analysis/analysis-brief.md`` §4 P0-A (commit 55a2991) and
the re-promotion handoff on task t_bb3039fd. The decomposer's generic example
(``src/audio_capture.py`` / ``capture_audio(duration) -> bytes``) does **not**
exist in this repo — the ambient capture module is the *already implemented*
live-transcription path:

- ``POST /api/v1/meetings/live/upload`` (``routes/live_transcription.py:227``)
  — REST capture: multipart ``file`` → 200 ``LiveTranscriptResponse``; empty →
  400; unsupported content-type (not in ``settings.SUPPORTED_AUDIO_FORMATS``)
  → 415; > ``max_audio_size_mb`` (25) → 413; ``LiveRateLimitExceeded`` → 429.
- ``LiveTranscriptionService.transcribe_file``
  (``services/live_transcription.py:308``) — service seam; an empty buffer
  must return an *empty* ``LiveTranscriptResponse`` (never fabricate).
- Capture "stop on demand" = the WS ingestion contract: binary chunk ingestion
  (``ingest_chunk``) plus the ``finalize`` control frame producing the final
  ``LiveTranscriptResponse`` (``live_session.py`` wire contract).

Because the feature already ships at HEAD, this suite is a *contract pin*:

- **Interface tests** — import/signature/shape guards that must pass
  immediately against HEAD (route registered, handler signature, service
  signature, response model, format set, env gate).
- **Behavioral tests** — assert the spec's observable behavior through the
  real endpoint stack with the canonical AI-seam override
  (``app.dependency_overrides[get_live_service]``, per
  ``tests/test_live_ui.py:159``). These mirror the validation contract in
  ``tests/test_ambient_recording.py`` (400/415/413/429 + happy path) so the
  two files stay consistent; do not report test_ambient_recording.py's known
  defects as regressions.

No inverse stub-guards (``pytest.raises(NotImplementedError)`` on the
feature's own methods) — the feature's methods are real and must be asserted
for their actual behavior.

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_audio_capture.py -q``
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytestmark = pytest.mark.quick


# ── Shared duck-typed AI seams (mirror tests/test_live_ui.py:25-50) ───────────


class _FakeTranscription:
    """Deterministic transcript for ambient capture tests."""

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
    """Deterministic extraction for ambient capture tests."""

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


def _provision_meeting(meeting_id: str, user_id: str = "test-user-id") -> None:
    """Insert a Meeting row (the WS capture flow provisions one via
    POST /live/start before the session attaches; finalize persists onto an
    existing row — services/live_transcription.py:451-452)."""

    async def _insert() -> None:
        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        async for session in get_db_session():
            session.add(
                Meeting(
                    id=meeting_id,
                    user_id=user_id,
                    title="Live transcription session",
                    filename="live_session.webm",
                    mode="general",
                    transcript=None,
                )
            )
            await session.commit()

    asyncio.run(_insert())


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately against HEAD (the contract is implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmbientCaptureInterface:
    """Imports, route registration, and signatures for the ambient capture path."""

    def test_upload_route_registered(self):
        """POST /api/v1/meetings/live/upload must exist (full-audio capture)."""
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

    def test_transcribe_file_signature(self):
        """transcribe_file must expose the exact spec signature
        (services/live_transcription.py:308)."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        sig = inspect.signature(LiveTranscriptionService.transcribe_file)
        params = sig.parameters
        required_params = (
            "audio_bytes",
            "filename",
            "user_id",
            "team_id",
            "meeting_id",
            "mode",
            "language",
        )
        for required in required_params:
            assert required in params, f"transcribe_file missing '{required}' param"
        # `from __future__ import annotations` in the module makes annotations
        # strings at runtime — accept both the live type and its string form.
        assert params["audio_bytes"].annotation in (bytes, "bytes")
        assert params["team_id"].default is None
        assert params["meeting_id"].default is None
        assert params["mode"].default == "general"
        assert params["language"].default is None
        ret = sig.return_annotation
        from meeting_notes_ai.live_session import LiveTranscriptResponse

        assert ret is LiveTranscriptResponse or ret == "LiveTranscriptResponse", (
            f"transcribe_file must return LiveTranscriptResponse, got {ret}"
        )

    def test_create_session_signature(self):
        """create_session must expose meeting_id/user_id plus scoping kwargs
        (services/live_transcription.py:161)."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        params = inspect.signature(LiveTranscriptionService.create_session).parameters
        for required in ("meeting_id", "user_id", "team_id", "room_id", "retention_days", "hipaa"):
            assert required in params, f"create_session missing '{required}' param"
        assert params["hipaa"].default is False

    def test_live_transcript_response_shape(self):
        """LiveTranscriptResponse must carry the full capture result shape."""
        from meeting_notes_ai.live_session import LiveTranscriptResponse

        resp = LiveTranscriptResponse(meeting_id="m-1")
        assert resp.meeting_id == "m-1"
        assert resp.transcript == ""
        assert resp.summary == ""
        assert resp.duration_seconds == 0.0
        assert resp.action_items == []
        assert resp.decisions == []

    def test_supported_audio_formats(self):
        """The capture path must accept the MIME types MediaRecorder emits."""
        from meeting_notes_ai.config import settings

        assert "audio/wav" in settings.SUPPORTED_AUDIO_FORMATS
        assert "audio/mpeg" in settings.SUPPORTED_AUDIO_FORMATS
        assert "audio/mp4" in settings.SUPPORTED_AUDIO_FORMATS
        assert "audio/webm" in settings.SUPPORTED_AUDIO_FORMATS

    def test_max_audio_size_default(self):
        """max_audio_size_mb must default to 25 MB."""
        from meeting_notes_ai.config import settings

        assert settings.max_audio_size_mb == 25

    def test_transcription_backend_env_gate(self, monkeypatch):
        """TRANSCRIPTION_BACKEND must be honored by Settings at construction."""
        from meeting_notes_ai.config import Settings

        monkeypatch.setenv("TRANSCRIPTION_BACKEND", "local")
        assert Settings.load().transcription_backend == "local"

        monkeypatch.delenv("TRANSCRIPTION_BACKEND")
        assert Settings.load().transcription_backend == "openai"

    def test_live_rate_limit_exceeded_importable(self):
        """LiveRateLimitExceeded is the capture path's rate-limit signal."""
        from meeting_notes_ai.services.live_transcription import LiveRateLimitExceeded

        assert issubclass(LiveRateLimitExceeded, Exception)


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — spec behavior through the real endpoint stack
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


class TestAmbientCaptureUpload:
    """POST /api/v1/meetings/live/upload — validation contract
    (routes/live_transcription.py:227-257)."""

    URL = "/api/v1/meetings/live/upload"

    def test_upload_returns_audio_buffer_transcript(self, client, override_service):
        """A valid capture returns a non-empty transcript buffer (200)."""
        resp = client.post(
            self.URL,
            files={"file": ("inperson.wav", b"\x00" * 3200, "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["meeting_id"], "response must carry a meeting_id"
        assert data["transcript"], "captured audio must produce a non-empty transcript"
        assert data["transcript"] == "ambient in-person recording transcript"
        assert data["summary"] == "Ambient meeting summary"
        assert data["duration_seconds"] == 2.0

    def test_upload_requires_auth(self, client, override_service):
        resp = client.post(
            self.URL,
            files={"file": ("inperson.wav", b"\x00" * 3200, "audio/wav")},
        )
        assert resp.status_code == 401

    def test_empty_audio_rejected_400(self, client, override_service):
        """An empty capture must be rejected with 400 (route :236)."""
        resp = client.post(
            self.URL,
            files={"file": ("empty.wav", b"", "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400, (
            f"empty audio must be rejected with 400, got {resp.status_code}"
        )

    def test_missing_mic_permission_rejected_415(self, client, override_service):
        """A non-audio content-type (e.g. a permission-denied capture saved as
        text) must be rejected with 415 (route :238)."""
        resp = client.post(
            self.URL,
            files={"file": ("denied.txt", b"mic permission denied", "text/plain")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 415, (
            f"unsupported content-type must be rejected with 415, got {resp.status_code}"
        )

    def test_oversize_audio_rejected_413(self, client, override_service, monkeypatch):
        """Audio over max_audio_size_mb must be rejected with 413 (route :243)."""
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
        """Exhausted token bucket must map to HTTP 429 (route :255)."""
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


class TestAmbientCaptureService:
    """LiveTranscriptionService.transcribe_file — the capture service seam."""

    def test_empty_buffer_never_fabricates_transcript(self, ambient_service):
        """An empty buffer is not a valid ambient capture: the service must
        return an empty LiveTranscriptResponse, never invent content
        (services/live_transcription.py:327-337)."""
        result = asyncio.run(
            ambient_service.transcribe_file(b"", "empty.wav", user_id="test-user-id")
        )
        assert result.transcript == "", (
            f"empty audio must not produce a fabricated transcript, got {result.transcript!r}"
        )
        assert result.summary == ""
        assert result.duration_seconds == 0.0

    def test_transcribe_file_returns_live_transcript_response(self, ambient_service):
        """Non-empty capture returns the spec response type with content."""
        from meeting_notes_ai.live_session import LiveTranscriptResponse

        result = asyncio.run(
            ambient_service.transcribe_file(
                b"\x00" * 3200, "inperson.wav", user_id="test-user-id"
            )
        )
        assert isinstance(result, LiveTranscriptResponse)
        assert result.transcript == "ambient in-person recording transcript"
        assert result.summary == "Ambient meeting summary"
        assert result.duration_seconds == 2.0

    def test_transcribe_file_mode_and_language_threaded(self, ambient_service):
        """mode/language must flow from the call into the AI seams
        (mode → extraction, language → transcription)."""
        captured = {}

        class _ModeFakeTranscription(_FakeTranscription):
            async def transcribe(self, audio_bytes, filename, language=None):
                captured["language"] = language
                return await super().transcribe(audio_bytes, filename, language)

        class _ModeFakeExtraction(_FakeExtraction):
            async def extract(self, transcript, mode=None):
                captured["mode"] = mode
                return await super().extract(transcript, mode)

        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        svc = LiveTranscriptionService(
            transcription_service=_ModeFakeTranscription(),
            extraction_service=_ModeFakeExtraction(),
        )
        result = asyncio.run(
            svc.transcribe_file(
                b"\x00" * 3200,
                "inperson.wav",
                user_id="test-user-id",
                mode="legal",
                language="hu",
            )
        )
        assert captured.get("language") == "hu"
        assert captured.get("mode") is not None
        assert getattr(captured.get("mode"), "value", None) == "legal"
        assert result.transcript == "ambient in-person recording transcript"


class TestAmbientCaptureStopOnDemand:
    """Capture can be stopped on demand: WS ingestion + finalize control frame
    (live_session.py wire contract) — the same pipeline the REST upload uses."""

    def test_ingest_then_finalize_stops_capture(self, _setup_test_db, ambient_service):
        """Binary chunk ingestion followed by the finalize control frame must
        stop the capture and produce the final LiveTranscriptResponse."""
        from meeting_notes_ai.live_session import LiveSessionStatus, LiveTranscriptResponse

        _provision_meeting("m-stop-1")
        session = asyncio.run(
            ambient_service.create_session(
                meeting_id="m-stop-1",
                user_id="test-user-id",
            )
        )
        assert session.status == LiveSessionStatus.LIVE

        from meeting_notes_ai.live_session import LiveChunk

        chunk = LiveChunk(sequence=1, data=b"\x00" * 1600)
        partial = asyncio.run(ambient_service.ingest_chunk(session.id, chunk))
        assert partial is not None, "ingesting a chunk must produce a partial transcript"

        result = asyncio.run(ambient_service.finalize(session.id))
        assert isinstance(result, LiveTranscriptResponse)
        assert result.session_id == session.id
        assert result.transcript == "ambient in-person recording transcript"
        assert result.duration_seconds == 2.0

        stopped = asyncio.run(ambient_service.get_session(session.id))
        assert stopped is not None
        assert stopped.status == LiveSessionStatus.FINALIZED, (
            "finalize must stop the capture by marking the session finalized"
        )

    def test_finalize_unknown_session_raises_key_error(self, ambient_service):
        """Stopping a capture that never started must fail loudly."""
        with pytest.raises(KeyError):
            asyncio.run(ambient_service.finalize("no-such-session"))
