#!/usr/bin/env python3
"""Dev-only demo server for the live transcription UI.

Runs the real FastAPI app but overrides the external AI seam
(``get_live_service``) with deterministic fakes, so the /app/live React view
can be exercised end-to-end **without** an OPENAI_API_KEY: login → start
session → mic chunks → partials → finalize → action items.

This is a DEVELOPMENT tool, not the production app — production uses the real
Whisper/LLM pipeline via the unmodified dependency.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python examples/live_demo_server.py

Then open http://127.0.0.1:8000/app/live and log in with:
    email:    demo@example.com
    password: demo1234
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from meeting_notes_ai.main import app as real_app
from meeting_notes_ai.models import (
    ActionItem,
    ExtractionResult,
    MeetingMode,
    TranscriptionResult,
    TranscriptSegment,
)
from meeting_notes_ai.routes.live_transcription import get_live_service
from meeting_notes_ai.services.live_transcription import LiveTranscriptionService


class _DemoTranscription:
    """Deterministic fake STT — echoes a fixed transcript per chunk count."""

    def __init__(self) -> None:
        self._count = 0

    async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None):
        self._count += 1
        words = ["hello", "this", "is", "a", "live", "demo", "meeting", "with", "action", "items"]
        text = " ".join(words[: min(len(words), self._count + 1)])
        return TranscriptionResult(
            text=text,
            language=language or "en",
            duration_seconds=1.0,
            segments=[TranscriptSegment(start=0.0, end=1.0, text=text)],
        )


class _DemoExtraction:
    """Deterministic fake LLM extraction."""

    async def extract(self, transcript: str, mode: MeetingMode = MeetingMode.GENERAL):
        return ExtractionResult(
            summary="Demo summary: the live transcription pipeline works end-to-end.",
            action_items=[
                ActionItem(assignee="Demo", description="Review the live transcript"),
                ActionItem(assignee="Demo", description="Approve the extracted action items"),
            ],
            decisions=["Ship the live view"],
            key_points=["Partials stream in sequence", "Finalize persists the meeting"],
        )


def build_demo_app() -> FastAPI:
    """Return the real app with the AI seam swapped for demo fakes."""
    service = LiveTranscriptionService(
        transcription_service=_DemoTranscription(),
        extraction_service=_DemoExtraction(),
    )
    real_app.dependency_overrides[get_live_service] = lambda: service
    return real_app


if __name__ == "__main__":
    app = build_demo_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
