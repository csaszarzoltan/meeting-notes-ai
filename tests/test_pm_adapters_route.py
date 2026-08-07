"""Route-level integration test for the PM adapter sync flow.

Exercises the full end-to-end path through the real FastAPI routes:
  1. POST /api/v1/workspace/integrations/Jira/connect  (with credentials)
  2. POST /api/v1/workspace/actions/{id}/queue           (sync the action)
  3. Verify external_id / external_url / sync_state=task-synced are persisted

Provider HTTP is mocked at the transport level with respx so the test is
fully deterministic and offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

import meeting_notes_ai.routes.workspace as workspace
from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.session import is_session_factory_configured
from meeting_notes_ai.main import app

pytestmark = pytest.mark.quick

USER = {"user_id": "route-user-a", "email": "route@example.com", "display_name": "Route User"}

JIRA_SITE = "https://acme.atlassian.net"


@pytest.fixture(autouse=True)
def _env_and_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _setup_test_db):
    """Provide a deterministic encryption key + isolated on-disk workspace.

    Depends on the shared in-memory test DB (_setup_test_db) so the
    PMIntegrationToken upsert has real tables to write to.
    """
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", "route-test-encryption-key-32b!!")
    monkeypatch.setenv("HIPAA_MASTER_KEY", "route-test-encryption-key-32b!!")
    workspace._STATE_PATH = tmp_path / "workspace.json"  # type: ignore[attr-defined]
    assert is_session_factory_configured()


@pytest.fixture
def client():
    """Authenticated TestClient with a mocked provider transport."""
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def _create_meeting_with_action(client: TestClient) -> dict[str, Any]:
    """Create a meeting carrying one actionable item, return the action."""
    resp = client.post(
        "/api/v1/workspace/meetings",
        json={
            "title": "Route level sync",
            "transcript": "Maya approved the privacy review. Route owns the follow-up.",
            "summary": "Privacy review approved.",
            "action_items": [{"description": "Sync this to Jira", "assignee": "Maya"}],
            "decisions": ["Approve privacy review"],
        },
    )
    assert resp.status_code == 201
    actions = client.get("/api/v1/workspace/actions").json()["items"]
    return next(a for a in actions if a["title"] == "Sync this to Jira")


def test_pm_connect_queue_flow_persists_synced_task(client: TestClient) -> None:
    """Full flow: connect Jira -> queue action -> external_id/url + task-synced."""
    action = _create_meeting_with_action(client)
    with respx.mock:
        # Connect: GET /rest/api/3/myself
        respx.get(f"{JIRA_SITE}/rest/api/3/myself").mock(
            return_value=httpx.Response(
                200,
                json={
                    "accountId": "route-123",
                    "emailAddress": "route@example.com",
                    "displayName": "Route User",
                    "active": True,
                },
            )
        )
        # Create task: POST /rest/api/3/issue
        respx.post(f"{JIRA_SITE}/rest/api/3/issue").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "10042",
                    "key": "ACME-7",
                    "self": f"{JIRA_SITE}/rest/api/3/issue/10042",
                },
            )
        )

        connected = client.post(
            "/api/v1/workspace/integrations/Jira/connect",
            json={
                "credentials": {
                    "token": "route-oauth-token",
                    "site_url": JIRA_SITE,
                    "email": "route@example.com",
                    "default_project": "ACME",
                }
            },
        )
        assert connected.status_code == 200, connected.text
        assert connected.json()["connected"] is True

        queued = client.post(
            f"/api/v1/workspace/actions/{action['id']}/queue",
            json={"destination": "Jira"},
        )
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert body["external_id"] == "ACME-7"
    assert body["external_url"] == f"{JIRA_SITE}/browse/ACME-7"
    assert body["sync_state"] == "task-synced"


def test_connect_persists_pm_integration_token_row() -> None:
    """A PMIntegrationToken row is upserted (source of truth) on connect."""
    from meeting_notes_ai.db.models import PMIntegrationToken
    from meeting_notes_ai.db.session import get_db_session

    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as client:
        with respx.mock:
            respx.get(f"{JIRA_SITE}/rest/api/3/myself").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "accountId": "route-123",
                        "emailAddress": "route@example.com",
                        "displayName": "Route User",
                        "active": True,
                    },
                )
            )
            connected = client.post(
                "/api/v1/workspace/integrations/Jira/connect",
                json={
                    "credentials": {
                        "token": "route-oauth-token",
                        "site_url": JIRA_SITE,
                        "email": "route@example.com",
                        "default_project": "ACME",
                    }
                },
            )
        assert connected.status_code == 200, connected.text

        async def _check() -> None:
            factory = get_db_session.__globals__["_session_factory"]
            async with factory() as session:
                stmt = select(PMIntegrationToken).where(
                    PMIntegrationToken.user_id == USER["user_id"],
                    PMIntegrationToken.provider == "jira",
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                assert row is not None
                assert row.is_active is True
                assert row.account_email == "route@example.com"
                assert row.account_url == JIRA_SITE
                assert row.encrypted_credentials

        import asyncio

        asyncio.run(_check())
    app.dependency_overrides.clear()


def test_connect_persists_token_then_queue_succeeds_without_409(client: TestClient) -> None:
    """Connecting first makes queueing succeed (no 409 from the 'connect first' guard)."""
    action = _create_meeting_with_action(client)
    with respx.mock:
        respx.get(f"{JIRA_SITE}/rest/api/3/myself").mock(
            return_value=httpx.Response(
                200,
                json={
                    "accountId": "route-123",
                    "emailAddress": "route@example.com",
                    "displayName": "Route User",
                    "active": True,
                },
            )
        )
        respx.post(f"{JIRA_SITE}/rest/api/3/issue").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "10043",
                    "key": "ACME-8",
                    "self": f"{JIRA_SITE}/rest/api/3/issue/10043",
                },
            )
        )
        connected = client.post(
            "/api/v1/workspace/integrations/Jira/connect",
            json={
                "credentials": {
                    "token": "route-oauth-token",
                    "site_url": JIRA_SITE,
                    "email": "route@example.com",
                    "default_project": "ACME",
                }
            },
        )
        assert connected.status_code == 200, connected.text

        queued = client.post(
            f"/api/v1/workspace/actions/{action['id']}/queue",
            json={"destination": "Jira"},
        )
    assert queued.status_code == 200, queued.text
    assert queued.json()["sync_state"] == "task-synced"
