"""Pre-development TDD tests for the batch transcription path of the
In-Person Bot-Free Recording feature (analysis/analysis-brief.md).

Feature target: uploaded audio → transcription via the existing
``services/transcription.py`` Whisper integration (mocked API), plus the new
local faster-whisper tier (P0-3):

- ``transcribe_file`` (services/live_transcription.py:281-328) — the batch
  entry point: audio bytes → ``LiveTranscriptResponse`` with meeting_id,
  transcript, summary, action_items, duration_seconds; meeting row persisted.
- ``TranscriptionService.transcribe`` (services/transcription.py:26-76) — the
  OpenAI Whisper integration; unchanged by the feature. Tests mock the OpenAI
  client and assert the exact payload sent (model, response_format, language)
  and the resulting ``TranscriptionResult`` shape.
- P0-3: ``TRANSCRIPTION_BACKEND=local`` must route to a
  ``LocalWhisperTranscriptionService`` (new services/local_transcription.py)
  exposing the SAME ``transcribe(audio_bytes, filename, language=None)``
  signature and returning the same ``TranscriptionResult`` shape. A
  duck-typed ``_FakeLocalWhisper`` stands in for faster-whisper so the
  contract is testable without the heavy dependency.

Two categories:
- Interface tests — PASS immediately.
- Behavioral tests — FAIL cleanly while the local tier is missing (no inverse
  NotImplementedError stubs).

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_batch_transcription.py``.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.quick

# ── Duck-typed AI seams ────────────────────────────────────────────────────────


class _FakeTranscription:
    """Deterministic transcript for batch upload tests."""

    async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None):
        from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment

        return TranscriptionResult(
            text="batch transcription of uploaded audio",
            language=language or "en",
            duration_seconds=3.0,
            segments=[
                TranscriptSegment(start=0.0, end=3.0, text="batch transcription of uploaded audio")
            ],
        )


class _FakeExtraction:
    """Deterministic extraction for batch upload tests."""

    async def extract(self, transcript: str, mode=None):
        from meeting_notes_ai.models import ActionItem, ExtractionResult

        return ExtractionResult(
            summary="Batch summary",
            action_items=[ActionItem(assignee="Mike", description="Ship batch transcription")],
            decisions=["Batch path approved"],
            key_points=["Batch works"],
        )


class _FakeLocalWhisper:
    """Duck-typed faster-whisper seam for P0-3.

    Mirrors the ``WhisperModel.transcribe`` call surface (segments iterable of
    (start, end, text) tuples) so the local service can be exercised without
    importing the real faster-whisper package. The class itself lives in this
    test module — the developer must NOT import it; the point is that the
    service accepts any object with this shape (interface parity with
    ``TranscriptionService.transcribe``).
    """

    def __init__(self, model: str = "small", compute_type: str = "int8") -> None:
        self.model = model
        self.compute_type = compute_type
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, audio: bytes, language: str | None = None):
        self.calls.append((audio, language))
        segments = [
            (0.0, 3.0, "local whisper transcribed this locally"),
        ]
        info = MagicMock()
        info.language = language or "en"
        info.duration = 3.0
        return segments, info


def _token(user_id: str) -> str:
    from meeting_notes_ai.auth import create_access_token

    return asyncio.run(create_access_token(user_id))


def _auth_headers(user_id: str = "test-user-id") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


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


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately
# ═══════════════════════════════════════════════════════════════════════════════


class TestBatchTranscriptionInterface:
    """Public signatures the feature must keep stable."""

    def test_transcribe_file_signature(self):
        """transcribe_file must expose the documented keyword contract."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        sig = inspect.signature(LiveTranscriptionService.transcribe_file)
        params = sig.parameters
        assert "audio_bytes" in params
        assert "filename" in params
        assert params["user_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
            "user_id must be keyword-only (star in signature)"
        )
        for optional in ("team_id", "meeting_id", "mode", "language"):
            assert optional in params, f"transcribe_file missing '{optional}'"
        assert params["mode"].default == "general"
        assert params["language"].default is None

    def test_transcribe_file_is_async(self):
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        assert inspect.iscoroutinefunction(LiveTranscriptionService.transcribe_file)

    def test_live_transcript_response_shape(self):
        """The batch response must carry meeting_id/transcript/summary/action_items."""
        from meeting_notes_ai.live_session import LiveTranscriptResponse

        resp = LiveTranscriptResponse(
            meeting_id="m-1",
            transcript="t",
            summary="s",
            duration_seconds=3.0,
        )
        assert resp.meeting_id == "m-1"
        assert resp.transcript == "t"
        assert resp.summary == "s"
        assert resp.duration_seconds == 3.0
        assert resp.action_items == []

    def test_transcription_service_transcribe_signature(self):
        """The OpenAI transcription interface is unchanged by the feature."""
        from meeting_notes_ai.services.transcription import TranscriptionService

        sig = inspect.signature(TranscriptionService.transcribe)
        params = list(sig.parameters)
        assert params[:4] == ["self", "audio_bytes", "filename", "language"]
        assert sig.parameters["language"].default is None
        assert inspect.iscoroutinefunction(TranscriptionService.transcribe)

    def test_transcription_service_returns_transcription_result(self):
        """The OpenAI service must return TranscriptionResult (mocked API)."""
        from meeting_notes_ai.services.transcription import TranscriptionService

        assert TranscriptionService.transcribe.__annotations__.get("return") in (
            "TranscriptionResult",
            "meeting_notes_ai.models.TranscriptionResult",
        ) or "TranscriptionResult" in str(
            inspect.signature(TranscriptionService.transcribe).return_annotation
        ), "transcribe return annotation must be TranscriptionResult"

    def test_transcription_backend_config_field_exists(self):
        """P0-3: Settings must expose transcription_backend (env TRANSCRIPTION_BACKEND)."""
        from meeting_notes_ai.config import Settings

        assert hasattr(Settings, "transcription_backend") or "transcription_backend" in (
            Settings.__dataclass_fields__
        ), "Settings.transcription_backend missing — P0-3 must add it"

    def test_transcription_backend_default_openai(self):
        """P0-3: the default backend must be 'openai' (existing behavior)."""
        from meeting_notes_ai.config import Settings

        defaults = getattr(Settings, "__dataclass_fields__", {})
        if "transcription_backend" in defaults:
            assert "openai" in str(defaults["transcription_backend"].default), (
                "TRANSCRIPTION_BACKEND must default to 'openai'"
            )

    def test_local_whisper_service_module_importable(self):
        """P0-3: services/local_transcription.py must be importable."""
        import importlib

        module = importlib.import_module("meeting_notes_ai.services.local_transcription")
        assert module is not None

    def test_local_whisper_service_class_exists(self):
        """P0-3: LocalWhisperTranscriptionService class must exist."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        assert LocalWhisperTranscriptionService is not None

    def test_local_whisper_transcribe_signature_matches_openai(self):
        """P0-3: local transcribe must mirror TranscriptionService.transcribe."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        sig = inspect.signature(LocalWhisperTranscriptionService.transcribe)
        params = list(sig.parameters)
        assert params[:4] == ["self", "audio_bytes", "filename", "language"], (
            "local transcribe signature must be "
            f"(self, audio_bytes, filename, language=None), got {params}"
        )
        assert sig.parameters["language"].default is None
        assert inspect.iscoroutinefunction(LocalWhisperTranscriptionService.transcribe)

    def test_get_live_service_constructs_openai_backend_by_default(self):
        """Default wiring: get_live_service must construct TranscriptionService
        (openai backend) — the existing behavior stays untouched."""
        from meeting_notes_ai.routes.live_transcription import get_live_service

        service = get_live_service()
        from meeting_notes_ai.services.transcription import TranscriptionService

        assert isinstance(service.transcription_service, TranscriptionService)


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — FAIL cleanly while the feature is missing
# ═══════════════════════════════════════════════════════════════════════════════


class TestOpenAIWhisperPayload:
    """The OpenAI Whisper integration (services/transcription.py) with a mocked
    API client: exact payload + result shape."""

    @pytest.mark.asyncio
    async def test_transcribe_sends_expected_payload(self, sample_audio_bytes):
        """The API call must use the configured model + verbose_json; the
        language hint must be forwarded when given."""
        from meeting_notes_ai.services.transcription import TranscriptionService

        service = TranscriptionService(api_key="test-key", model="whisper-1")

        mock_transcription = MagicMock()
        mock_transcription.text = "Hello world"
        mock_transcription.language = "en"
        mock_transcription.duration = 12.5
        mock_transcription.segments = [{"start": 0.0, "end": 5.0, "text": "Hello"}]

        mock_client = AsyncMock()
        create = AsyncMock(return_value=mock_transcription)
        mock_client.audio.transcriptions.create = create

        with patch.object(service, "_get_client", return_value=mock_client):
            await service.transcribe(sample_audio_bytes, "meeting.wav", language="en")

        create.assert_awaited_once()
        kwargs = create.await_args.kwargs
        assert kwargs["model"] == "whisper-1"
        assert kwargs["response_format"] == "verbose_json"
        assert kwargs["language"] == "en"
        assert kwargs["file"].name == "meeting.wav"

    @pytest.mark.asyncio
    async def test_transcribe_result_shape(self, sample_audio_bytes, sample_filename):
        """Whisper verbose_json maps to TranscriptionResult with segments."""
        from meeting_notes_ai.services.transcription import TranscriptionService

        service = TranscriptionService(api_key="test-key")

        mock_transcription = MagicMock()
        mock_transcription.text = "Hello world"
        mock_transcription.language = "en"
        mock_transcription.duration = 12.5
        mock_transcription.segments = [
            {"start": 0.0, "end": 5.0, "text": "Hello"},
            {"start": 5.0, "end": 12.5, "text": "world"},
        ]

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.transcribe(sample_audio_bytes, sample_filename)

        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration_seconds == 12.5
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.segments[0].start == 0.0

    @pytest.mark.asyncio
    async def test_transcribe_no_language_omits_hint(self, sample_audio_bytes):
        """Without a language hint the request must not carry a language kwarg."""
        from meeting_notes_ai.services.transcription import TranscriptionService

        service = TranscriptionService(api_key="test-key")

        mock_transcription = MagicMock()
        mock_transcription.text = "Hello"
        mock_transcription.language = "en"
        mock_transcription.duration = 1.0
        mock_transcription.segments = None

        mock_client = AsyncMock()
        create = AsyncMock(return_value=mock_transcription)
        mock_client.audio.transcriptions.create = create

        with patch.object(service, "_get_client", return_value=mock_client):
            await service.transcribe(sample_audio_bytes, "meeting.wav")

        assert "language" not in create.await_args.kwargs


class TestBatchTranscribeFile:
    """transcribe_file — uploaded audio → LiveTranscriptResponse + persisted row."""

    @pytest.fixture
    def client(self, _setup_test_db, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.config import settings
        from meeting_notes_ai.main import app

        monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
        return TestClient(app)

    @pytest.fixture
    def batch_service(self, _setup_test_db):
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        return LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
        )

    @pytest.fixture
    def override_service(self, client, batch_service):
        from meeting_notes_ai.main import app
        from meeting_notes_ai.routes.live_transcription import get_live_service

        app.dependency_overrides[get_live_service] = lambda: batch_service
        yield batch_service
        app.dependency_overrides.pop(get_live_service, None)

    def test_upload_returns_batch_result_and_persists(self, client, override_service):
        """Full-file upload → LiveTranscriptResponse + meeting row."""
        resp = client.post(
            "/api/v1/meetings/live/upload",
            files={"file": ("batch.wav", b"\x00" * 3200, "audio/wav")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["meeting_id"]
        assert data["transcript"] == "batch transcription of uploaded audio"
        assert data["summary"] == "Batch summary"
        assert data["action_items"][0]["description"] == "Ship batch transcription"
        assert data["duration_seconds"] == 3.0

        row = _fetch_meeting(data["meeting_id"])
        assert row is not None, "transcribe_file must persist the meeting"
        assert row.transcript == "batch transcription of uploaded audio"

    @pytest.mark.asyncio
    async def test_transcribe_file_mode_threaded(self, batch_service):
        """P0-4: the meeting mode must reach the persisted row (currently
        transcribe_file passes mode through; finalize hard-codes 'general')."""
        result = await batch_service.transcribe_file(
            b"\x00" * 3200,
            "healthcare.wav",
            user_id="test-user-id",
            mode="healthcare",
        )
        row = await asyncio.to_thread(_fetch_meeting, result.meeting_id)
        assert row is not None
        assert row.mode == "healthcare", (
            f"meeting mode must be persisted (healthcare), got {row.mode!r}"
        )


class TestLocalWhisperBackendBehavioral:
    """P0-3 RED contract: TRANSCRIPTION_BACKEND=local routes to a local
    faster-whisper-backed service with the same transcribe signature and a
    real TranscriptionResult return value."""

    @pytest.mark.asyncio
    async def test_local_whisper_service_returns_transcription_result(self):
        """The local service must return a real TranscriptionResult built from
        faster-whisper segments — NOT raise, NOT return None."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        service = LocalWhisperTranscriptionService(whisper=_FakeLocalWhisper())
        result = await service.transcribe(b"\x00" * 3200, "inperson.wav", language="en")

        from meeting_notes_ai.models import TranscriptionResult

        assert isinstance(result, TranscriptionResult), (
            f"local transcribe must return TranscriptionResult, got {type(result).__name__}"
        )
        assert result.text == "local whisper transcribed this locally"
        assert result.language == "en"
        assert result.duration_seconds == 3.0
        assert len(result.segments) == 1
        assert result.segments[0].text == "local whisper transcribed this locally"

    @pytest.mark.asyncio
    async def test_local_whisper_service_feeds_raw_audio_to_backend(self):
        """The local service must hand the raw audio bytes to faster-whisper."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        fake = _FakeLocalWhisper()
        service = LocalWhisperTranscriptionService(whisper=fake)
        audio = b"\x00" * 16000
        await service.transcribe(audio, "inperson.wav")

        assert fake.calls, "local service must call the faster-whisper backend"
        sent_audio, _ = fake.calls[-1]
        assert sent_audio == audio, "raw audio bytes must reach the local backend"

    def test_settings_env_gate_local_backend(self, monkeypatch):
        """P0-3: TRANSCRIPTION_BACKEND=local must be honored by Settings."""
        monkeypatch.setenv("TRANSCRIPTION_BACKEND", "local")
        from meeting_notes_ai.config import Settings

        s = Settings()
        assert getattr(s, "transcription_backend", None) == "local", (
            "Settings must read TRANSCRIPTION_BACKEND=local from the environment"
        )
