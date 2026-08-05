"""TDD coverage for persisted product-workspace behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_notes_ai.main import app
from meeting_notes_ai.routes import workspace

pytestmark = pytest.mark.quick


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return an app client backed by a real temporary JSON store."""
    monkeypatch.setattr(workspace, "_STATE_PATH", tmp_path / "workspace.json")
    return TestClient(app)


def test_workspace_dashboard_and_meetings_are_persisted(client: TestClient) -> None:
    """Dashboard and meeting library come from the persistent workspace API."""
    dashboard = client.get("/api/v1/workspace/dashboard")
    meetings = client.get("/api/v1/workspace/meetings")
    assert dashboard.status_code == 200
    assert meetings.status_code == 200
    assert dashboard.json()["needs_review"] >= 1
    assert meetings.json()["items"][0]["id"]


def test_review_update_persists_version_and_approval(client: TestClient) -> None:
    """Editing and approval create durable versions and audit history."""
    meeting_id = client.get("/api/v1/workspace/meetings").json()["items"][0]["id"]
    response = client.patch(
        f"/api/v1/workspace/meetings/{meeting_id}/review",
        json={"summary": "Verified summary", "review_status": "approved", "reviewer": "QA"},
    )
    assert response.status_code == 200
    detail = client.get(f"/api/v1/workspace/meetings/{meeting_id}").json()
    assert detail["summary"] == "Verified summary"
    assert detail["review_status"] == "approved"
    assert detail["versions"][-1]["reviewer"] == "QA"


def test_action_confirmation_and_sync_are_durable(client: TestClient) -> None:
    """Actions move through confirmation and synchronization via real I/O."""
    action = client.get("/api/v1/workspace/actions").json()["items"][0]
    confirmed = client.patch(
        f"/api/v1/workspace/actions/{action['id']}",
        json={"status": "confirmed", "owner": "Zoltan", "due": "2026-08-07"},
    )
    synced = client.post(
        f"/api/v1/workspace/actions/{action['id']}/sync",
        json={"destination": "Microsoft Planner"},
    )
    assert confirmed.json()["status"] == "confirmed"
    assert synced.json()["status"] == "synced"
    assert synced.json()["external_id"].startswith("planner-")


def test_settings_and_integrations_persist(client: TestClient) -> None:
    """Governed settings and connector state survive subsequent reads."""
    settings = client.put(
        "/api/v1/workspace/settings",
        json={"processing_region": "Zurich / EU", "retention_days": 2190},
    )
    connector = client.post(
        "/api/v1/workspace/integrations/Microsoft%20Planner/connect",
        json={"enabled": True},
    )
    assert settings.status_code == 200
    assert client.get("/api/v1/workspace/settings").json()["retention_days"] == 2190
    assert connector.json()["connected"] is True


def test_insights_query_returns_cited_source_moments(client: TestClient) -> None:
    """Workspace answers are generated from persisted meetings with citations."""
    response = client.post("/api/v1/workspace/insights/query", json={"query": "privacy"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["sources"]
    assert body["sources"][0]["meeting_id"]
    assert body["sources"][0]["timestamp"]


def test_compliance_and_batches_are_real_api_surfaces(client: TestClient) -> None:
    """Compliance findings and batch retry are backed by persisted state."""
    controls = client.get("/api/v1/workspace/compliance").json()["controls"]
    assert controls[0]["evidence"]
    batches = client.get("/api/v1/workspace/batches").json()["items"]
    retried = client.post(f"/api/v1/workspace/batches/{batches[-1]['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "processing"


def test_share_requires_approval_and_can_be_revoked(client: TestClient) -> None:
    """Workspace shares are policy-gated, persisted, and immediately revocable."""
    meeting_id = client.get("/api/v1/workspace/meetings").json()["items"][0]["id"]
    blocked = client.post(
        f"/api/v1/workspace/meetings/{meeting_id}/share", json={"expires_in": "7d"}
    )
    assert blocked.status_code == 409
    client.patch(
        f"/api/v1/workspace/meetings/{meeting_id}/review",
        json={"summary": "Approved", "review_status": "approved", "reviewer": "QA"},
    )
    shared = client.post(
        f"/api/v1/workspace/meetings/{meeting_id}/share", json={"expires_in": "7d"}
    )
    assert shared.status_code == 201
    assert client.delete(f"/api/v1/workspace/shares/{shared.json()['id']}").status_code == 204
