"""Compatibility checks retained for the historical v1.0.1 workspace contract.

The old anonymous and fake-sync expectations were intentionally retired by
v1.1.2. This module now verifies that the read paths remain shape-compatible
when used through the authenticated tenant boundary.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.main import app
from meeting_notes_ai.routes import workspace

pytestmark = pytest.mark.quick
USER = {"user_id": "legacy-user", "email": "legacy@example.com", "display_name": "Legacy"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return an authenticated client using real temporary JSON I/O."""
    monkeypatch.setattr(workspace, "_STATE_PATH", tmp_path / "workspace.json")
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def test_workspace_list_shapes_remain_compatible(client: TestClient) -> None:
    """Historical dashboard, meeting, and action list response keys remain stable."""
    assert set(client.get("/api/v1/workspace/dashboard").json()) >= {
        "needs_review",
        "open_actions",
        "processing_failures",
        "time_saved_hours",
    }
    assert client.get("/api/v1/workspace/meetings").json() == {"items": []}
    assert client.get("/api/v1/workspace/actions").json() == {"items": []}


def test_workspace_review_persists_after_canonical_create(client: TestClient) -> None:
    """Canonical create and review preserve the original detail contract."""
    meeting = client.post(
        "/api/v1/workspace/meetings",
        json={"title": "Compatibility meeting", "transcript": "Evidence", "summary": "Draft"},
    ).json()
    reviewed = client.patch(
        f"/api/v1/workspace/meetings/{meeting['id']}/review",
        json={"summary": "Verified", "review_status": "approved", "reviewer": "Legacy"},
    )
    assert reviewed.status_code == 200
    detail = client.get(f"/api/v1/workspace/meetings/{meeting['id']}").json()
    assert detail["summary"] == "Verified"
    assert detail["versions"][-1]["reviewer"] == "Legacy"
