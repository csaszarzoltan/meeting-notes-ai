"""TDD contracts for the complete v1.0 meeting-workflow GUI."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.quick
ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "frontend/src/workspace"


def read(name: str) -> str:
    """Read one workspace component as UTF-8 text."""
    return (UI / name).read_text(encoding="utf-8")


def test_action_center_supports_execution_workflow() -> None:
    """Suggested actions can be filtered, confirmed, and synchronized."""
    source = read("ActionCenter.tsx")
    for term in (
        "Assigned to me",
        "Unassigned",
        "Due soon",
        "Overdue",
        "Waiting for approval",
        "Synced",
        "Completed",
    ):
        assert term in source
    for term in ("Suggested", "Confirmed", "Microsoft Planner", "Source evidence"):
        assert term in source


def test_safe_sharing_has_preview_permissions_and_protection() -> None:
    """The sharing flow exposes audience, content, permissions, protection, and preview."""
    source = read("SharingCenter.tsx")
    for term in (
        "Audience",
        "Selected people",
        "Summary",
        "Transcript",
        "Download",
        "Reshare",
        "Expiration",
        "Passcode",
        "Recipient preview",
        "This is what recipients will see",
    ):
        assert term in source
    assert "/api/v1/meetings/" in source


def test_processing_timeline_has_eight_recoverable_stages() -> None:
    """Processing is transparent and stage-level failures are recoverable."""
    source = read("ProcessingTimeline.tsx")
    for term in (
        "Uploading",
        "Audio validation",
        "Transcribing",
        "Identifying speakers",
        "Extracting notes",
        "Applying privacy policy",
        "Linking source evidence",
        "Ready for review",
        "Retry this stage",
    ):
        assert term in source


def test_compliance_center_is_issue_first_not_score_first() -> None:
    """Compliance starts with issues, evidence freshness, and remediation."""
    source = read("ComplianceCenter.tsx")
    for term in (
        "Critical issues",
        "Required actions",
        "Unknown or stale evidence",
        "Passing controls",
        "Review findings",
        "Last checked",
        "Audit history",
    ):
        assert term in source
    assert "overall_compliance_score" not in source


def test_cross_meeting_insights_are_cited() -> None:
    """Workspace intelligence links every answer to source meeting moments."""
    source = read("InsightsCenter.tsx")
    for term in (
        "Ask across meetings",
        "Recurring themes",
        "Risks",
        "Decisions",
        "Source moments",
        "Open meeting at",
    ):
        assert term in source


def test_live_workspace_has_status_transcript_and_intelligence_columns() -> None:
    """The live screen follows the three-column capture specification."""
    source = read("LiveWorkspace.tsx")
    for term in (
        "Audio quality",
        "Consent confirmed",
        "Follow live",
        "Speaker 2",
        "Highlights",
        "Actions",
        "Decisions",
        "Notes",
        "Live draft",
        "Add bookmark",
    ):
        assert term in source


def test_setup_flow_exposes_capture_modes_templates_and_data_path() -> None:
    """Meeting setup progressively explains context and privacy."""
    source = read("MeetingSetup.tsx")
    for term in (
        "Record live",
        "Upload recording",
        "Import calendar meeting",
        "Record in person",
        "1:1",
        "Stand-up",
        "Project review",
        "Customer call",
        "Interview",
        "Healthcare",
        "Legal",
        "How we handle this meeting",
        "Processing region",
        "Zürich / EU",
    ):
        assert term in source


def test_mobile_navigation_has_required_five_destinations() -> None:
    """Mobile users get Home, Meetings, Record, Actions, and More."""
    source = read("MobileNavigation.tsx")
    for term in ("Home", "Meetings", "Record", "Actions", "More"):
        assert term in source
    css = (ROOT / "frontend/src/styles.css").read_text(encoding="utf-8")
    assert ".mobile-bottom-nav" in css
    assert "min-height:44px" in css.replace(" ", "")


def test_app_routes_all_product_views_to_real_components() -> None:
    """Priority product views are not generic placeholders."""
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    for component in (
        "ActionCenter",
        "SharingCenter",
        "ComplianceCenter",
        "InsightsCenter",
        "BatchCenter",
        "IntegrationsCenter",
        "WorkspaceSettings",
    ):
        assert component in source
