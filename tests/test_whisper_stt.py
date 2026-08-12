"""Pre-development contract tests for the local Whisper STT tier (P0-B).

Spec source: ``analysis/analysis-brief.md`` §4 P0-B (commit 55a2991).

Feature target: with ``TRANSCRIPTION_BACKEND=local``, captured audio is
transcribed by a LOCAL faster-whisper model — no cloud/network calls, no
``openai`` package import. The local service mirrors the OpenAI tier's public
contract ``transcribe(audio_bytes, filename, language=None) -> TranscriptionResult``
so callers cannot tell which backend handled a request.

Module under test: ``src/meeting_notes_ai/services/local_transcription.py``
(``LocalWhisperTranscriptionService``). There is intentionally NO
``src/whisper_stt.py`` / bare ``transcribe(audio) -> str`` — the decomposer
example does not apply to this repo (brief §1.2, §4 P0-B).

Two categories:
- Interface tests — the class/signature/config surface; these must pass
  immediately against HEAD (the feature is already implemented).
- Behavioral tests — the spec behaviors: a real ``TranscriptionResult`` built
  from faster-whisper segments, env-gated local backend selection, empty/invalid
  audio handled without an exception, and the privacy guarantee (the local tier
  never imports or constructs the ``openai`` package).

No inverse stub-guards: the feature's own methods are never asserted to raise
``NotImplementedError``.

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_whisper_stt.py``
"""

from __future__ import annotations

import inspect
import os
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.quick

# ── Duck-typed faster-whisper seam ────────────────────────────────────────────


class _FakeLocalWhisper:
    """Duck-typed faster-whisper ``WhisperModel`` for the local tier.

    Mirrors the call surface the service depends on: ``transcribe(audio,
    language=None)`` returning ``(segments, info)`` where ``segments`` is an
    iterable of ``(start, end, text)`` tuples and ``info`` exposes
    ``.language`` / ``.duration``. The service must accept ANY object with this
    shape (interface parity with ``TranscriptionService.transcribe``) — it must
    never import the real faster-whisper package at test time.
    """

    def __init__(self, model: str = "small", compute_type: str = "int8") -> None:
        self.model = model
        self.compute_type = compute_type
        self.calls: list[tuple[bytes, str | None]] = []

    def transcribe(self, audio: bytes, language: str | None = None):
        self.calls.append((audio, language))
        segments = [(0.0, 3.0, "transcribed locally without cloud")]
        info = MagicMock()
        info.language = language or "en"
        info.duration = 3.0
        return segments, info


class _EmptyLocalWhisper:
    """Faster-whisper seam that transcribes to zero segments (silence)."""

    def transcribe(self, audio: bytes, language: str | None = None):
        info = MagicMock()
        info.language = language or "en"
        info.duration = 0.0
        return [], info


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately against HEAD
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalWhisperInterface:
    """Public surface of the local Whisper tier (brief §4 P0-B)."""

    def test_module_importable(self):
        """services/local_transcription.py must exist and be importable."""
        import importlib

        module = importlib.import_module("meeting_notes_ai.services.local_transcription")
        assert module is not None

    def test_service_class_exists(self):
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        assert LocalWhisperTranscriptionService is not None

    def test_init_signature_exact(self):
        """__init__ must accept the documented injectable params with defaults."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        sig = inspect.signature(LocalWhisperTranscriptionService.__init__)
        params = sig.parameters
        assert list(params) == ["self", "whisper", "model", "compute_type"], (
            f"__init__ params must be (self, whisper, model, compute_type), got {list(params)}"
        )
        assert params["whisper"].default is None
        assert params["model"].default is None
        assert params["compute_type"].default == "int8"

    def test_transcribe_signature_matches_openai_tier(self):
        """transcribe must mirror TranscriptionService.transcribe's contract."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        sig = inspect.signature(LocalWhisperTranscriptionService.transcribe)
        params = list(sig.parameters)
        assert params == ["self", "audio_bytes", "filename", "language"], (
            "transcribe signature must be "
            f"(self, audio_bytes, filename, language=None), got {params}"
        )
        assert sig.parameters["language"].default is None
        assert inspect.iscoroutinefunction(LocalWhisperTranscriptionService.transcribe), (
            "transcribe must be async (interface parity with the OpenAI tier)"
        )

    def test_transcribe_return_annotation_is_transcription_result(self):
        """The return type must be TranscriptionResult — not str."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        ret = inspect.signature(LocalWhisperTranscriptionService.transcribe).return_annotation
        assert ret is not inspect.Signature.empty
        assert "TranscriptionResult" in str(ret), (
            f"transcribe must be annotated -> TranscriptionResult, got {ret!r}"
        )

    def test_transcription_backend_config_field_exists(self):
        """Settings must expose transcription_backend (env TRANSCRIPTION_BACKEND)."""
        from meeting_notes_ai.config import Settings

        assert "transcription_backend" in Settings.__dataclass_fields__, (
            "Settings.transcription_backend missing — P0-3 must add it"
        )

    def test_transcription_backend_defaults_to_openai(self):
        """Default backend stays 'openai'; 'local' is opt-in via env."""
        from meeting_notes_ai.config import Settings

        default = Settings.__dataclass_fields__["transcription_backend"].default
        assert "openai" in str(default), (
            f"TRANSCRIPTION_BACKEND must default to 'openai', got {default!r}"
        )

    def test_transcribe_file_has_keyword_only_contract(self):
        """The batch entry point used by the ambient pipeline keeps its shape."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        sig = inspect.signature(LiveTranscriptionService.transcribe_file)
        params = sig.parameters
        assert "audio_bytes" in params and "filename" in params
        assert params["user_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
            "user_id must be keyword-only (star in signature)"
        )
        assert params["language"].default is None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — the local tier's spec behavior (green against HEAD)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalWhisperTranscribeBehavior:
    """Local transcription must produce a real result from local segments."""

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcription_result(self):
        """transcribe must return a TranscriptionResult built from the local
        model's segments — not str, not None, not a raise."""
        from meeting_notes_ai.models import TranscriptionResult
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        service = LocalWhisperTranscriptionService(whisper=_FakeLocalWhisper())
        result = await service.transcribe(b"\x00" * 3200, "inperson.wav", language="en")

        assert isinstance(result, TranscriptionResult), (
            f"local transcribe must return TranscriptionResult, got {type(result).__name__}"
        )
        assert result.text == "transcribed locally without cloud"
        assert result.language == "en"
        assert result.duration_seconds == 3.0
        assert len(result.segments) == 1
        assert result.segments[0].start == 0.0
        assert result.segments[0].end == 3.0
        assert result.segments[0].text == "transcribed locally without cloud"

    @pytest.mark.asyncio
    async def test_transcribe_feeds_raw_audio_and_language_to_backend(self):
        """The raw audio bytes must reach the local model unchanged, and the
        language hint must be forwarded when provided."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        fake = _FakeLocalWhisper()
        service = LocalWhisperTranscriptionService(whisper=fake)
        audio = b"\x00" * 16000
        await service.transcribe(audio, "inperson.wav", language="hu")

        assert fake.calls, "local service must call the faster-whisper backend"
        sent_audio, sent_lang = fake.calls[-1]
        assert sent_audio == audio, "raw audio bytes must reach the local backend"
        assert sent_lang == "hu", "language hint must be forwarded to the backend"

    @pytest.mark.asyncio
    async def test_transcribe_without_language_passes_none(self):
        """No language hint → the backend is called with language=None."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        fake = _FakeLocalWhisper()
        service = LocalWhisperTranscriptionService(whisper=fake)
        await service.transcribe(b"\x00" * 3200, "inperson.wav")

        assert fake.calls
        assert fake.calls[-1][1] is None

    @pytest.mark.asyncio
    async def test_transcribe_joins_multiple_segments(self):
        """Multiple (start, end, text) tuples join into the transcript text."""
        from meeting_notes_ai.models import TranscriptSegment
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        class _MultiSegWhisper:
            def transcribe(self, audio: bytes, language: str | None = None):
                info = MagicMock()
                info.language = language or "en"
                info.duration = 5.0
                return [(0.0, 2.5, "first part"), (2.5, 5.0, "second part")], info

        service = LocalWhisperTranscriptionService(whisper=_MultiSegWhisper())
        result = await service.transcribe(b"\x00" * 3200, "inperson.wav")

        assert result.text == "first part second part"
        assert result.duration_seconds == 5.0
        assert len(result.segments) == 2
        assert all(isinstance(seg, TranscriptSegment) for seg in result.segments)

    @pytest.mark.asyncio
    async def test_empty_segments_yield_empty_text_no_error(self):
        """Silence (zero segments) must not raise; text stays empty."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        service = LocalWhisperTranscriptionService(whisper=_EmptyLocalWhisper())
        result = await service.transcribe(b"\x00" * 3200, "silence.wav")

        assert result.text == ""
        assert result.segments == []


class TestLocalWhisperPrivacy:
    """P0-4 privacy guarantee: the local tier never touches the openai package."""

    def test_module_source_never_imports_openai(self):
        """The local service source must not import or construct openai."""
        import inspect as _inspect

        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        source = _inspect.getsource(LocalWhisperTranscriptionService)
        assert "import openai" not in source
        assert "from openai" not in source
        assert "OpenAI(" not in source, (
            "local backend must never construct an OpenAI client (privacy guarantee)"
        )

    def test_service_never_holds_openai_client_after_transcribe(self):
        """After a local transcription, the service must not hold any OpenAI
        client — the only client attribute stays None."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        service = LocalWhisperTranscriptionService(whisper=_FakeLocalWhisper())
        assert getattr(service, "_client", "missing") is None, (
            "local backend must never hold an OpenAI client"
        )


class TestLocalWhisperEmptyInput:
    """Empty/invalid audio must be handled without an exception."""

    @pytest.mark.asyncio
    async def test_transcribe_file_empty_buffer_returns_empty_result(self):
        """An empty buffer must return an empty LiveTranscriptResponse — never
        fabricate a transcript, never raise."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        service = LiveTranscriptionService(
            transcription_service=MagicMock(),
            extraction_service=MagicMock(),
            rate_limiter=MagicMock(),
        )
        result = await service.transcribe_file(
            b"", "empty.wav", user_id="test-user-id"
        )

        assert result.transcript == ""
        assert result.summary == ""
        assert result.duration_seconds == 0.0
        assert result.action_items == []
        # The transcription/extraction backends must not be touched for empty input.
        service.transcription_service.transcribe.assert_not_called()
        service.extraction_service.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcribe_file_zero_segments_no_fabrication(self, _setup_test_db):
        """Audio that transcribes to zero segments must not fabricate content."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        class _EmptyExtraction:
            async def extract(self, transcript: str, mode=None):
                from meeting_notes_ai.models import ExtractionResult

                return ExtractionResult()

        service = LiveTranscriptionService(
            transcription_service=LocalWhisperTranscriptionService(
                whisper=_EmptyLocalWhisper()
            ),
            extraction_service=_EmptyExtraction(),
            rate_limiter=MagicMock(),
        )
        result = await service.transcribe_file(
            b"\x00" * 3200, "silence.wav", user_id="test-user-id"
        )

        assert isinstance(result.transcript, str)
        assert result.transcript == ""
        assert result.duration_seconds == 0.0


class TestLocalWhisperBackendSelection:
    """TRANSCRIPTION_BACKEND env must select the local tier."""

    def test_settings_env_gate_local_backend(self, monkeypatch):
        """TRANSCRIPTION_BACKEND=local must be honored by Settings."""
        monkeypatch.setenv("TRANSCRIPTION_BACKEND", "local")
        from meeting_notes_ai.config import Settings

        s = Settings()
        assert getattr(s, "transcription_backend", None) == "local", (
            "Settings must read TRANSCRIPTION_BACKEND=local from the environment"
        )

    def test_get_live_service_builds_local_whisper_service(self, monkeypatch):
        """With TRANSCRIPTION_BACKEND=local, get_live_service must wire the
        LocalWhisperTranscriptionService as the transcription backend."""
        monkeypatch.setenv("TRANSCRIPTION_BACKEND", "local")
        from meeting_notes_ai.config import settings
        from meeting_notes_ai.routes.live_transcription import get_live_service
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        original = settings.transcription_backend
        try:
            settings.transcription_backend = "local"
            service = get_live_service()
        finally:
            settings.transcription_backend = original

        assert isinstance(
            service.transcription_service, LocalWhisperTranscriptionService
        ), (
            "TRANSCRIPTION_BACKEND=local must route to the local whisper service, "
            f"got {type(service.transcription_service).__name__}"
        )


class TestLocalWhisperNoOpenaiImport:
    """Hermetic check: importing the local tier must not pull in the openai
    package. Subprocess-based so it works regardless of collection order."""

    def test_importing_local_service_does_not_import_openai(self):
        import subprocess
        import sys as _sys

        code = (
            "import sys;"
            "import meeting_notes_ai.services.local_transcription;"
            "print('openai' in sys.modules)"
        )
        proc = subprocess.run(
            [_sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd="/home/zoltan/meeting-notes-ai",
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "False", (
            f"importing local_transcription must NOT import openai, got {proc.stdout.strip()}"
        )
