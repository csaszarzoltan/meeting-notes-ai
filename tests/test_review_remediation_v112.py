"""Regression contracts for the independent v1.1.0 review findings."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.quick
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"


def read(path: str) -> str:
    """Read a frontend source file."""
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_auth_gate_is_mounted_and_workspace_client_sends_bearer() -> None:
    """The private application must mount auth and attach its session JWT."""
    assert "<AuthGate><App /></AuthGate>" in read("main.tsx")
    api = read("api/workspace.ts")
    assert "sessionStorage.getItem('workspace_token')" in api
    assert "Authorization" in api and "Bearer" in api


def test_upload_saves_canonical_meeting_before_review() -> None:
    """Processed upload output must be saved before opening review."""
    source = read("workspace/UploadFlow.tsx")
    assert "workspaceRequest<MeetingResult>('/meetings'" in source
    assert "onComplete(saved)" in source


def test_action_center_queues_without_fake_sync() -> None:
    """Task execution must not claim remote provider completion."""
    source = read("workspace/ActionCenter.tsx")
    assert "/queue" in source
    assert "/sync" not in source
    assert "Queue for adapter" in source


def test_review_player_uses_real_audio_ref() -> None:
    """Review playback and evidence jumps must control the audio element."""
    source = read("workspace/ReviewWorkspace.tsx")
    assert "audioRef" in source
    assert ".play()" in source
    assert "currentTime" in source


def test_command_palette_queries_workspace_and_handles_keyboard() -> None:
    """Global search must query workspace data and support keyboard selection."""
    source = read("workspace/CommandPalette.tsx")
    assert "workspaceRequest" in source
    assert "ArrowDown" in source and "ArrowUp" in source and "Enter" in source


def test_unavailable_capture_modes_are_disabled() -> None:
    """Preview-only capture modes must not present a working Continue button."""
    source = read("workspace/MeetingSetup.tsx")
    assert "isAvailable" in source
    assert "disabled={!isAvailable}" in source
