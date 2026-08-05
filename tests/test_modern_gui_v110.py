"""TDD contracts for the modern outcome-first product experience."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.quick
ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "frontend/src"


def source(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_command_palette_has_search_and_quick_actions() -> None:
    text = source("workspace/CommandPalette.tsx")
    for term in (
        "Search meetings",
        "Start recording",
        "Upload recording",
        "Open review queue",
        "Overdue actions",
    ):
        assert term in text
    assert 'role="dialog"' in text


def test_review_contains_lifecycle_autosave_mobile_tabs_and_evidence_navigation() -> None:
    text = source("workspace/ReviewWorkspace.tsx") + source("workspace/LifecycleStepper.tsx")
    for term in (
        "Captured",
        "Processing",
        "Needs review",
        "Approved",
        "Shared",
        "Actions in progress",
        "Saved",
        "Previous source",
        "Next source",
        "Notes",
        "Transcript",
        "Evidence",
        "Actions",
    ):
        assert term in text
    assert 'aria-live="polite"' in text


def test_dashboard_has_onboarding_and_next_best_action() -> None:
    text = source("workspace/Dashboard.tsx")
    for term in (
        "Get productive in three steps",
        "Connect your calendar",
        "Review your first meeting",
        "Next best action",
    ):
        assert term in text


def test_global_feedback_components_cover_async_states() -> None:
    text = source("workspace/AsyncState.tsx")
    for term in ("Loading", "Partial success", "Offline", "Permission denied", "Retry"):
        assert term in text


def test_modern_design_supports_compact_dark_and_mobile_player() -> None:
    css = source("styles.css")
    for term in (
        ".command-palette",
        ".lifecycle-stepper",
        ".mobile-review-tabs",
        ".mobile-player",
        '[data-density="compact"]',
        '[data-theme="dark"]',
    ):
        assert term in css
