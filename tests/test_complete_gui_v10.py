"""Source-contract checks that ensure priority GUI screens use real APIs."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.quick
ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "frontend/src/workspace"


def read(name: str) -> str:
    """Read a workspace component."""
    return (UI / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("component", "endpoint"),
    [
        ("Dashboard.tsx", "/dashboard"),
        ("MeetingLibrary.tsx", "/meetings"),
        ("ActionCenter.tsx", "/actions"),
        ("BatchCenter.tsx", "/batches"),
        ("ComplianceCenter.tsx", "/compliance"),
        ("IntegrationsCenter.tsx", "/integrations"),
        ("WorkspaceSettings.tsx", "/settings"),
        ("InsightsCenter.tsx", "/insights/query"),
    ],
)
def test_priority_screen_uses_workspace_api(component: str, endpoint: str) -> None:
    """Priority screens must not be static facades."""
    source = read(component)
    assert "workspaceRequest" in source
    assert endpoint in source


def test_review_persists_versions_and_uses_real_evidence() -> None:
    """Review submits status changes and renders evidence from its API model."""
    source = read("ReviewWorkspace.tsx")
    assert "/review" in source
    assert "detail.evidence" in source
    assert "detail.versions" in source
    assert "setApproved(true)" not in source
    assert "const SAMPLE" not in source


def test_live_workspace_delegates_to_real_websocket_view() -> None:
    """Live page uses the real microphone/WebSocket implementation without fake utterances."""
    source = read("LiveWorkspace.tsx")
    assert "LiveTranscriptionView" in source
    assert "Speaker 2" not in source
    assert "Audio quality" not in source


def test_sharing_only_claims_backend_enforced_controls() -> None:
    """Sharing UI must not advertise unsupported passcode or permission controls."""
    source = read("SharingCenter.tsx")
    assert "/share" in source
    assert "expires_in" in source
    assert "Passcode" not in source
    assert "Domain restriction" not in source
    assert "Maximum views" not in source


def test_mobile_navigation_has_five_destinations_and_touch_targets() -> None:
    """Mobile navigation implements the required destinations and touch size."""
    source = read("MobileNavigation.tsx")
    for term in ("Home", "Meetings", "Record", "Actions", "More"):
        assert term in source
    css = (ROOT / "frontend/src/styles.css").read_text(encoding="utf-8")
    assert ".mobile-bottom-nav" in css
    assert "min-height:44px" in css.replace(" ", "")
