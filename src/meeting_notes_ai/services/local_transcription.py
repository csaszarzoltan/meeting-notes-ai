"""Local transcription service — faster-whisper backend (P0-3).

When ``TRANSCRIPTION_BACKEND=local`` the live/ambient pipeline routes audio to
``LocalWhisperTranscriptionService`` instead of the OpenAI Whisper API. The
service mirrors ``TranscriptionService.transcribe``'s public contract
``(self, audio_bytes, filename, language=None)`` and returns the same
``TranscriptionResult`` shape, so callers cannot tell which backend handled a
request.

The faster-whisper ``WhisperModel`` is a heavy native dependency, so it is
imported lazily inside :meth:`_build_model` and is entirely injectable
(``whisper=`` constructor kwarg) — tests stand in with a duck-typed object that
mirrors the ``WhisperModel.transcribe`` call surface (segments iterable of
``(start, end, text)`` tuples plus an info object with ``language``/``duration``).

Privacy guarantee (P0-4): this class never constructs an OpenAI client and
never imports the ``openai`` package, so Healthcare/Legal meetings processed
with ``TRANSCRIPTION_BACKEND=local`` never leave the machine.
"""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment


class LocalWhisperTranscriptionService:
    """Transcribe audio to text via a local faster-whisper model.

    Args:
        whisper: Optional pre-built faster-whisper ``WhisperModel`` (or any
            object with a matching ``transcribe(audio, language=None)`` method
            returning ``(segments, info)``). When omitted, the model is built
            lazily from ``WHISPER_MODEL`` / ``WHISPER_COMPUTE_TYPE`` env vars.
        model: faster-whisper model size to load (defaults to ``WHISPER_MODEL``).
        compute_type: faster-whisper compute type (defaults to ``int8``).
    """

    def __init__(
        self,
        whisper: Any | None = None,
        model: str | None = None,
        compute_type: str = "int8",
    ) -> None:
        import os

        self.model = model or os.getenv("WHISPER_MODEL", "small")
        self.compute_type = compute_type or os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        self._whisper = whisper
        self._client: Any | None = None  # local backend never holds an OpenAI client

    def _build_model(self) -> Any:
        """Lazily import and build the faster-whisper model."""
        if self._whisper is None:
            from faster_whisper import WhisperModel

            self._whisper = WhisperModel(self.model, compute_type=self.compute_type)
        return self._whisper

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe raw audio bytes with the local faster-whisper model.

        Args:
            audio_bytes: Raw audio file bytes (WAV/WebM/MP3 …).
            filename: Original filename (unused by the local backend, kept for
                interface parity with ``TranscriptionService.transcribe``).
            language: Optional ISO language code (e.g. "en") forwarded to the
                model; ``None`` lets faster-whisper auto-detect.

        Returns:
            TranscriptionResult with text, language, duration, and segments.
        """
        model = self._build_model()
        segments, info = model.transcribe(audio_bytes, language=language)

        text_parts: list[str] = []
        parsed: list[TranscriptSegment] = []
        for start, end, text in segments:
            text_parts.append(text)
            parsed.append(
                TranscriptSegment(start=float(start), end=float(end), text=str(text))
            )

        return TranscriptionResult(
            text=" ".join(text_parts).strip(),
            language=getattr(info, "language", language or ""),
            duration_seconds=float(getattr(info, "duration", 0.0) or 0.0),
            segments=parsed,
        )
