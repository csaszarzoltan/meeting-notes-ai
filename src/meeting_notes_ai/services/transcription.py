"""Transcription service — OpenAI Whisper API integration."""

from __future__ import annotations

from io import BytesIO

from openai import AsyncOpenAI

from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment


class TranscriptionService:
    """Transcribe audio to text via Whisper API."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.model = model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text using OpenAI Whisper API.

        Args:
            audio_bytes: Raw audio file bytes.
            filename: Original filename (used to infer format).
            language: Optional ISO language code (e.g. "en").

        Returns:
            TranscriptionResult with text, language, duration, and segments.
        """
        client = self._get_client()

        # Build transcription kwargs
        kwargs: dict = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if language is not None:
            kwargs["language"] = language

        # Upload file as BytesIO
        audio_file = BytesIO(audio_bytes)
        audio_file.name = filename

        transcript = await client.audio.transcriptions.create(
            file=audio_file,
            **kwargs,
        )

        # Parse response
        segments = [
            TranscriptSegment(
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
                text=seg.get("text", ""),
            )
            for seg in getattr(transcript, "segments", []) or []
        ]

        return TranscriptionResult(
            text=transcript.text or "",
            language=getattr(transcript, "language", language or ""),
            duration_seconds=getattr(transcript, "duration", 0.0) or 0.0,
            segments=segments,
        )
