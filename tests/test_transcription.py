"""Interface and behavioral tests for TranscriptionService."""

from __future__ import annotations

from inspect import signature
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


from meeting_notes_ai.models import (
    TranscriptionResult,
    TranscriptSegment,
)
from meeting_notes_ai.services.transcription import TranscriptionService

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestTranscriptionServiceInterface:
    """Verify TranscriptionService class contract."""

    def test_transcription_service_can_be_imported(self):
        """TranscriptionService should be importable."""
        from meeting_notes_ai.services.transcription import (
            TranscriptionService,
        )

        assert TranscriptionService is not None

    def test_transcription_result_can_be_imported(self):
        """TranscriptionResult model should be importable."""
        from meeting_notes_ai.models import TranscriptionResult

        assert TranscriptionResult is not None

    def test_transcript_segment_can_be_imported(self):
        """TranscriptSegment model should be importable."""
        from meeting_notes_ai.models import TranscriptSegment

        assert TranscriptSegment is not None

    def test_transcription_service_init_signature(self):
        """__init__ should accept api_key and model params."""
        sig = signature(TranscriptionService.__init__)
        params = list(sig.parameters.keys())
        assert "api_key" in params
        assert "model" in params

    def test_transcription_service_transcribe_signature(self):
        """transcribe method should have expected signature."""
        assert hasattr(TranscriptionService, "transcribe")
        sig = signature(TranscriptionService.transcribe)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "audio_bytes" in params
        assert "filename" in params
        assert "language" in params

    def test_transcribe_has_default_language_none(self):
        """language param should default to None."""
        sig = signature(TranscriptionService.transcribe)
        param = sig.parameters.get("language")
        assert param is not None
        assert param.default is None

    def test_transcribe_is_async(self):
        """transcribe should be a coroutine (async)."""
        import inspect

        assert inspect.iscoroutinefunction(TranscriptionService.transcribe)

    def test_transcription_init_default_model(self):
        """model should default to 'whisper-1'."""
        sig = signature(TranscriptionService.__init__)
        param = sig.parameters.get("model")
        assert param is not None
        assert param.default == "whisper-1"

    def test_transcription_result_is_pydantic(self):
        """TranscriptionResult should be instantiable with fields."""
        result = TranscriptionResult(
            text="Hello world",
            language="en",
            duration_seconds=12.5,
            segments=[
                TranscriptSegment(start=0.0, end=5.0, text="Hello"),
                TranscriptSegment(start=5.0, end=12.5, text="world"),
            ],
        )
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration_seconds == 12.5
        assert len(result.segments) == 2

    def test_transcription_result_defaults(self):
        """TranscriptionResult should have sensible defaults."""
        result = TranscriptionResult()
        assert result.text == ""
        assert result.language == ""
        assert result.duration_seconds == 0.0
        assert result.segments == []

    def test_transcript_segment_is_pydantic(self):
        """TranscriptSegment should be instantiable with fields."""
        seg = TranscriptSegment(start=1.0, end=2.5, text="test")
        assert seg.start == 1.0
        assert seg.end == 2.5
        assert seg.text == "test"

    def test_transcript_segment_defaults(self):
        """TranscriptSegment should have sensible defaults."""
        seg = TranscriptSegment()
        assert seg.start == 0.0
        assert seg.end == 0.0
        assert seg.text == ""


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestTranscriptionServiceBehavioral:
    """Verify transcription behavior with real implementation."""

    def test_transcription_init_succeeds(self):
        """Instantiating TranscriptionService should not raise."""
        service = TranscriptionService(api_key="test-key")
        assert service.api_key == "test-key"
        assert service.model == "whisper-1"

    @pytest.mark.asyncio
    async def test_transcribe_calls_openai(
        self, sample_audio_bytes, sample_filename
    ):
        """Calling transcribe should use OpenAI client."""
        service = TranscriptionService(api_key="test-key")

        # Mock the OpenAI client
        mock_transcription = MagicMock()
        mock_transcription.text = "Hello world"
        mock_transcription.language = "en"
        mock_transcription.duration = 12.5
        mock_transcription.segments = [
            {"start": 0.0, "end": 5.0, "text": "Hello"},
            {"start": 5.0, "end": 12.5, "text": "world"},
        ]

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.transcribe(
                sample_audio_bytes, sample_filename
            )

        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration_seconds == 12.5
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.segments[1].text == "world"

    @pytest.mark.asyncio
    async def test_transcribe_with_language(
        self, sample_audio_bytes, sample_filename, sample_language
    ):
        """Calling transcribe with language should pass to API."""
        service = TranscriptionService(api_key="test-key")

        mock_transcription = MagicMock()
        mock_transcription.text = "Hello world"
        mock_transcription.language = "en"
        mock_transcription.duration = 0.0
        mock_transcription.segments = None

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.transcribe(
                sample_audio_bytes, sample_filename, language=sample_language
            )

        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_transcribe_with_empty_audio_returns_empty(
        self, sample_filename
    ):
        """Calling transcribe with empty bytes returns empty result."""
        service = TranscriptionService(api_key="test-key")

        mock_transcription = MagicMock()
        mock_transcription.text = ""
        mock_transcription.language = ""
        mock_transcription.duration = 0.0
        mock_transcription.segments = None

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.transcribe(b"", sample_filename)

        assert result.text == ""
        assert result.duration_seconds == 0.0
