"""Security and end-to-end tests for the tenant-scoped workspace."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.main import app
from meeting_notes_ai.routes import workspace

pytestmark = pytest.mark.quick
USER = {"user_id": "user-a", "email": "a@example.com", "display_name": "User A"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Authenticate a real client and isolate its on-disk tenant state."""
    monkeypatch.setattr(workspace, "_STATE_PATH", tmp_path / "workspace.json")
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def create_meeting(client: TestClient) -> dict:
    """Create a canonical meeting through real file I/O."""
    response = client.post(
        "/api/v1/workspace/meetings",
        json={
            "title": "Uploaded review",
            "transcript": "Maya approved the privacy review. Zoltan owns the follow-up.",
            "summary": "Privacy review approved.",
            "action_items": [{"description": "Follow up", "assignee": "Zoltan"}],
            "decisions": ["Approve privacy review"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_workspace_requires_authentication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Anonymous callers cannot read or mutate the private workspace."""
    monkeypatch.setattr(workspace, "_STATE_PATH", tmp_path / "workspace.json")
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/workspace/dashboard").status_code == 401
        assert anonymous.put("/api/v1/workspace/settings", json={}).status_code == 401


def test_tenants_are_isolated(client: TestClient):
    """A second user cannot see the first user's canonical meeting."""
    meeting = create_meeting(client)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-b",
        "email": "b@example.com",
    }
    assert client.get(f"/api/v1/workspace/meetings/{meeting['id']}").status_code == 404
    assert client.get("/api/v1/workspace/meetings").json()["items"] == []


def test_upload_review_share_and_public_access_flow(client: TestClient):
    """Canonical create, approval, sharing, public resolve, and revocation work end to end."""
    meeting = create_meeting(client)
    approved = client.patch(
        f"/api/v1/workspace/meetings/{meeting['id']}/review",
        json={"summary": "Verified", "review_status": "approved", "reviewer": "User A"},
    )
    assert approved.status_code == 200
    shared = client.post(
        f"/api/v1/workspace/meetings/{meeting['id']}/share", json={"expires_in": "7d"}
    )
    assert shared.status_code == 201
    public = client.get(shared.json()["url"])
    assert public.status_code == 200
    assert public.json()["summary"] == "Verified"
    assert client.delete(f"/api/v1/workspace/shares/{shared.json()['id']}").status_code == 204
    assert client.get(shared.json()["url"]).status_code == 410


def test_actions_require_connected_adapter_and_are_not_fake_synced(client: TestClient):
    """External work is queued only after connector configuration."""
    create_meeting(client)
    action = client.get("/api/v1/workspace/actions").json()["items"][0]
    blocked = client.post(
        f"/api/v1/workspace/actions/{action['id']}/queue",
        json={"destination": "Microsoft Planner"},
    )
    assert blocked.status_code == 409
    client.post(
        "/api/v1/workspace/integrations/Microsoft%20Planner/connect", json={"enabled": True}
    )
    queued = client.post(
        f"/api/v1/workspace/actions/{action['id']}/queue",
        json={"destination": "Microsoft Planner"},
    )
    assert queued.json()["status"] == "queued"
    assert queued.json()["external_id"] is None
    assert queued.json()["adapter_job_id"]


def test_compliance_is_derived_from_authenticated_settings(client: TestClient):
    """Compliance reflects current policy state rather than seeded claims."""
    initial = client.get("/api/v1/workspace/compliance").json()["controls"]
    assert all(item["level"] == "pass" for item in initial)
    client.put("/api/v1/workspace/settings", json={"require_approval": False})
    changed = client.get("/api/v1/workspace/compliance").json()["controls"]
    assert changed[0]["level"] == "critical"


def test_complete_private_workspace_surface(client: TestClient):
    """Exercise settings, integrations, actions, insights, compliance, and batch errors."""
    meeting = create_meeting(client)
    assert client.get("/api/v1/workspace/dashboard").status_code == 200
    assert client.get("/api/v1/workspace/meetings").json()["items"][0]["id"] == meeting["id"]
    assert client.get(f"/api/v1/workspace/meetings/{meeting['id']}").status_code == 200
    action = client.get("/api/v1/workspace/actions").json()["items"][0]
    changed = client.patch(
        f"/api/v1/workspace/actions/{action['id']}",
        json={"status": "confirmed", "owner": "Maya", "due": "2026-08-09"},
    )
    assert changed.json()["owner"] == "Maya"
    assert client.get("/api/v1/workspace/settings").status_code == 200
    assert client.put("/api/v1/workspace/settings", json={"unknown": True}).status_code == 422
    assert client.get("/api/v1/workspace/integrations").status_code == 200
    assert client.post("/api/v1/workspace/integrations/Unknown/connect", json={}).status_code == 404
    insight = client.post("/api/v1/workspace/insights/query", json={"query": "privacy"})
    assert insight.status_code == 200
    assert client.get("/api/v1/workspace/compliance").status_code == 200
    assert client.get("/api/v1/workspace/batches").status_code == 200
    assert client.post("/api/v1/workspace/batches/nope/retry").status_code == 404


def test_share_policy_errors_and_missing_public_token(client: TestClient):
    """Unapproved, missing, expired, and unknown shares fail closed."""
    meeting = create_meeting(client)
    assert (
        client.post(
            f"/api/v1/workspace/meetings/{meeting['id']}/share", json={"expires_in": "1h"}
        ).status_code
        == 409
    )
    assert client.get("/public/workspace-shares/not-found").status_code == 404
    assert client.delete("/api/v1/workspace/shares/not-found").status_code == 404
