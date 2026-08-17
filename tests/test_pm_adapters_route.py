"""Route-level integration test for the PM adapter sync flow.

Exercises the full end-to-end path through the real FastAPI routes:
  1. POST /api/v1/workspace/integrations/Jira/connect  (with credentials)
  2. POST /api/v1/workspace/actions/{id}/queue           (sync the action)
  3. Verify external_id / external_url / sync_state=task-synced are persisted

Provider HTTP is mocked at the transport level with respx so the test is
fully deterministic and offline.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

import meeting_notes_ai.routes.workspace as workspace
from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import PMIntegrationToken
from meeting_notes_ai.db.session import get_db_session, is_session_factory_configured
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
            json={"destination": "Jira", "confirmed": True},
        )
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert body["external_id"] == "ACME-7"
    assert body["external_url"] == f"{JIRA_SITE}/browse/ACME-7"
    assert body["sync_state"] == "task-synced"


def test_connect_persists_pm_integration_token_row() -> None:
    """A PMIntegrationToken row is upserted (source of truth) on connect."""
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
            json={"destination": "Jira", "confirmed": True},
        )
    assert queued.status_code == 200, queued.text
    assert queued.json()["sync_state"] == "task-synced"


# ── Health endpoint tests ─────────────────────────────────────────────────────


async def _insert_token(
    *,
    user_id: str = USER["user_id"],
    provider: str = "jira",
    is_active: bool = True,
    token_expires_at: datetime | None = None,
    disconnected_at: datetime | None = None,
    account_email: str = "route@example.com",
) -> None:
    """Insert a PMIntegrationToken row directly into the test DB.

    Deletes any existing row for (user_id, provider) first to avoid
    UNIQUE constraint conflicts from prior tests.
    """
    factory = get_db_session.__globals__["_session_factory"]
    async with factory() as session:
        await session.execute(
            sql_delete(PMIntegrationToken).where(
                PMIntegrationToken.user_id == user_id,
                PMIntegrationToken.provider == provider,
            )
        )
        await session.flush()
        token = PMIntegrationToken(
            user_id=user_id,
            provider=provider,
            encrypted_credentials="dGVzdA==",
            account_email=account_email,
            account_url=JIRA_SITE,
            token_expires_at=token_expires_at,
            is_active=is_active,
            disconnected_at=disconnected_at,
        )
        session.add(token)
        await session.commit()


async def _delete_tokens(user_id: str = USER["user_id"], provider: str = "jira") -> None:
    """Remove all PMIntegrationToken rows for the given user/provider."""
    factory = get_db_session.__globals__["_session_factory"]
    async with factory() as session:
        await session.execute(
            sql_delete(PMIntegrationToken).where(
                PMIntegrationToken.user_id == user_id,
                PMIntegrationToken.provider == provider,
            )
        )
        await session.commit()


def test_integration_health_connected_returns_green(client: TestClient) -> None:
    """Mock valid token expiring far in the future -> status 'healthy'."""
    future = datetime.now(timezone.utc) + timedelta(hours=48)
    asyncio.run(_insert_token(token_expires_at=future, is_active=True))

    resp = client.get("/api/v1/workspace/integrations/Jira/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["provider"] == "jira"
    assert body["token_expires_at"] is not None

    asyncio.run(_delete_tokens())


def test_integration_health_expiring_returns_yellow(client: TestClient) -> None:
    """Mock token expiring in 12h -> status 'expiring_soon'."""
    soon = datetime.now(timezone.utc) + timedelta(hours=12)
    asyncio.run(_insert_token(token_expires_at=soon, is_active=True))

    resp = client.get("/api/v1/workspace/integrations/Jira/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "expiring_soon"
    assert body["provider"] == "jira"

    asyncio.run(_delete_tokens())


def test_integration_health_expired_returns_red(client: TestClient) -> None:
    """Mock expired token -> status 'needs_reauth'."""
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    asyncio.run(_insert_token(token_expires_at=past, is_active=True))

    resp = client.get("/api/v1/workspace/integrations/Jira/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_reauth"
    assert body["provider"] == "jira"

    asyncio.run(_delete_tokens())


def test_integration_health_not_found_returns_404(client: TestClient) -> None:
    """Unknown provider name -> 404."""
    resp = client.get("/api/v1/workspace/integrations/UnknownTool/health")
    assert resp.status_code == 404


# ── Review-before-push preview / confirmation tests ───────────────────────────


def test_queue_action_rejects_unconfirmed_returns_preview(client: TestClient) -> None:
    """POST queue without confirmed=true -> 409 with preview data."""
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

        # Queue WITHOUT confirmed=true
        queued = client.post(
            f"/api/v1/workspace/actions/{action['id']}/queue",
            json={"destination": "Jira"},
        )
    assert queued.status_code == 409
    body = queued.json()["detail"]
    assert body["message"] == "Confirm action to proceed"
    preview = body["preview"]
    assert "title" in preview
    assert "description" in preview
    assert "assignee" in preview
    assert "priority" in preview
    assert preview["destination"] == "jira"


def test_queue_action_confirmed_succeeds(client: TestClient) -> None:
    """POST queue with confirmed=true -> 200 with sync result."""
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
                    "id": "10099",
                    "key": "ACME-99",
                    "self": f"{JIRA_SITE}/rest/api/3/issue/10099",
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
            json={"destination": "Jira", "confirmed": True},
        )
    assert queued.status_code == 200, queued.text
    assert queued.json()["sync_state"] == "task-synced"
    assert queued.json()["external_id"] == "ACME-99"


def test_preview_action_returns_mapped_fields(client: TestClient) -> None:
    """POST preview -> 200 with correct field mapping for Jira."""
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

        resp = client.post(
            f"/api/v1/workspace/actions/{action['id']}/preview",
            json={"destination": "Jira"},
        )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["destination"] == "jira"
    assert preview["title"] == action["title"]
    assert "description" in preview
    assert preview["priority"] in ("High", "Medium", "Low")
    assert preview["project"] == "ACME"
