"""TDD contract for the unified v0.9 product workspace."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_notes_ai.main import app

pytestmark = pytest.mark.quick
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def test_root_product_route_serves_unified_react_shell() -> None:
    """The main product route must serve the built SPA, not inline legacy markup."""
    response = TestClient(app).get("/app")
    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert "New meeting" not in response.text
    assert response.headers["content-security-policy"].startswith("default-src 'self'")


def test_spa_assets_are_available_from_unified_app_base() -> None:
    """The generated asset route supports the unified /app asset base."""
    product_source = (ROOT / "src/meeting_notes_ai/routes/product_app.py").read_text()
    assert '@router.get("/app/assets/{path:path}"' in product_source


def test_product_shell_exposes_research_priority_navigation() -> None:
    """The GUI covers the research-prioritized product areas."""
    source = (FRONTEND / "App.tsx").read_text()
    for label in (
        "Home",
        "Meetings",
        "Record",
        "Batches",
        "Actions",
        "Team",
        "Sharing",
        "Compliance",
        "Integrations",
        "Settings",
    ):
        assert label in source


def test_meeting_library_has_search_filters_and_empty_state() -> None:
    """Meeting history must be discoverable and friendly when empty."""
    source = (FRONTEND / "workspace/MeetingLibrary.tsx").read_text()
    assert "Search meetings" in source
    assert "All statuses" in source
    assert "No meetings match" in source
    assert "aria-label" in source


def test_review_workspace_links_evidence_and_requires_approval() -> None:
    """Review UX exposes transcript evidence and explicit approval."""
    source = (FRONTEND / "workspace/ReviewWorkspace.tsx").read_text()
    assert "Source evidence" in source
    assert "Approve notes" in source
    assert "Needs review" in source
    assert "audio" in source
    assert "timestamp" in source.lower()


def test_upload_flow_has_privacy_defaults_and_friendly_errors() -> None:
    """The real upload flow must guide privacy and show recoverable errors."""
    source = (FRONTEND / "workspace/UploadFlow.tsx").read_text()
    assert "/api/v1/meetings" in source
    assert "Healthcare" in source
    assert "Consent" in source
    assert "25 MB" in source
    assert 'role="alert"' in source


def test_design_system_is_responsive_and_accessible() -> None:
    """The sellable UI ships focus, motion, mobile, and token rules."""
    css = (FRONTEND / "styles.css").read_text()
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@media (max-width:" in css
    assert "--accent:" in css
    assert ".app-shell" in css


def test_frontend_dependencies_are_exactly_pinned() -> None:
    """GitHub-ready builds must not float direct dependency versions."""
    import json

    package = json.loads((ROOT / "frontend/package.json").read_text())
    for group in ("dependencies", "devDependencies"):
        assert all(not value.startswith(("^", "~")) for value in package[group].values())


def test_app_asset_route_serves_real_built_file() -> None:
    """Integration: the FastAPI route performs real file I/O for a Vite asset."""
    assets = ROOT / "frontend/dist/assets"
    asset = next(item for item in assets.iterdir() if item.is_file())
    response = TestClient(app).get(f"/app/assets/{asset.name}")
    assert response.status_code == 200
    assert response.content == asset.read_bytes()


def test_app_asset_route_rejects_missing_and_traversal_paths() -> None:
    """Asset delivery must fail closed for missing and traversal inputs."""
    client = TestClient(app)
    assert client.get("/app/assets/not-found.js").status_code == 404
    assert client.get("/app/assets/%2E%2E/README.md").status_code in {404, 422}


def test_legacy_live_route_redirects_to_canonical_workspace() -> None:
    """Old live bookmarks remain compatible without maintaining two UIs."""
    response = TestClient(app).get("/app/live", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app"
