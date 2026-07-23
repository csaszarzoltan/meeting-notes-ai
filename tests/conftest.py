"""Shared pytest fixtures for MeetingNotesAI tests."""

from __future__ import annotations

import pytest

# ── Sample Data ───────────────────────────────────────────────────────────────


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """Short valid WAV audio bytes (silence)."""
    return b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"  # noqa: E501


@pytest.fixture
def sample_transcript() -> str:
    """Sample meeting transcript."""
    return (
        "John: Let's discuss the Q3 roadmap.\n"
        "Sarah: I think we should focus on the API integration first.\n"
        "John: Agreed. Mike, can you handle that?\n"
        "Mike: Sure, I'll start next week.\n"
        "Sarah: Great. We also need to decide on the deployment timeline.\n"
        "John: Let's target October 1st for the initial release.\n"
        "Sarah: Works for me.\n"
        "John: OK, action items: Mike owns the API integration, "
        "Sarah owns documentation, I'll handle deployment.\n"
    )


@pytest.fixture
def sample_filename() -> str:
    """Sample audio filename."""
    return "meeting_recording.wav"


@pytest.fixture
def sample_language() -> str:
    """Sample language code."""
    return "en"


@pytest.fixture
def empty_transcript() -> str:
    """Empty transcript edge case."""
    return ""


@pytest.fixture
def sample_patient_id() -> str:
    """Sample patient ID for healthcare tests."""
    return "PAT-2026-0042"


@pytest.fixture
def sample_case_metadata_dict() -> dict:
    """Sample case metadata dict for legal tests."""
    return {
        "case_number": "2026-CV-0042",
        "parties": ["Plaintiff Corp.", "Defendant LLC"],
        "date": "2026-07-15",
        "jurisdiction": "Southern District of New York",
    }


# ── Async helpers ─────────────────────────────────────────────────────────────


@pytest.fixture
def event_loop():
    """Provide an event loop for async tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
