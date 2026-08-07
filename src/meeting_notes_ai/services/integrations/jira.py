"""Jira adapter — OAuth2 (primary) + JWT-basic fallback for server/DC."""

from __future__ import annotations

from typing import Any

import httpx

from meeting_notes_ai.services.http_client import get_http_client
from meeting_notes_ai.services.integrations.base import (
    Adapter,
    AdapterAuth,
    AdapterAuthError,
    AdapterConnection,
    AdapterTaskResult,
    AdapterUnavailableError,
    AdapterValidationError,
)


def _map_jira_error(exc: httpx.HTTPStatusError) -> None:
    """Translate an httpx error into the adapter exception family."""
    status = exc.response.status_code
    if status in (401, 403):
        raise AdapterAuthError(
            "Invalid or expired credentials for Jira. Reconnect your account."
        ) from exc
    if status >= 500:
        raise AdapterUnavailableError(
            "Jira is temporarily unavailable. Try again in a few minutes."
        ) from exc
    raise AdapterValidationError(
        "Check the project key in your Jira settings."
    ) from exc


class JiraAdapter(Adapter):
    """Real Jira integration using the REST API v3."""

    provider = "jira"
    display_name = "Jira"
    auth_type = "oauth2"

    # Transient auth state set by the route layer between connect() and
    # create_task().  Adapters are effectively stateless — the route layer
    # owns decryption and lifecycle — but create_task() needs the site URL
    # and token that connect() validated, so we cache them here.
    _auth: AdapterAuth | None = None

    def _resolve_auth(self, action: dict[str, Any]) -> AdapterAuth:
        """Return cached auth or raise if connect() was never called."""
        if self._auth is None:
            raise AdapterValidationError(
                "Jira adapter not connected. Call connect() first."
            )
        return self._auth

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate credentials by calling /rest/api/3/myself."""
        site_url = auth.site_url.rstrip("/")
        if not site_url:
            raise AdapterValidationError("site_url is required for Jira connections.")

        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.get(
                    f"{site_url}/rest/api/3/myself",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_jira_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Jira is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        self._auth = auth
        data = resp.json()
        return AdapterConnection(
            account_email=data.get("emailAddress", auth.email),
            account_url=site_url,
            token_expires_at=None,
        )

    async def create_task(
        self,
        action: dict[str, Any],
        project: str | None = None,
        idempotency_key: str | None = None,
    ) -> AdapterTaskResult:
        """Create a Jira issue from a workspace action item."""
        auth = self._resolve_auth(action)
        site_url = auth.site_url.rstrip("/")
        proj_key = project or auth.default_project

        fields: dict[str, Any] = {
            "summary": action.get("title", "Untitled action"),
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Meeting: {action.get('meeting', 'N/A')}\n"
                                    f"Owner: {action.get('owner', 'Unassigned')}\n"
                                    f"Due: {action.get('due', 'Unscheduled')}"
                                ),
                            }
                        ],
                    }
                ],
            },
            "issuetype": {"name": "Task"},
        }
        if proj_key:
            fields["project"] = {"key": proj_key}
        due = action.get("due")
        if due and due != "Unscheduled":
            fields["duedate"] = due

        headers: dict[str, str] = {
            "Authorization": f"Bearer {auth.token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.post(
                    f"{site_url}/rest/api/3/issue",
                    json={"fields": fields},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_jira_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Jira is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        data = resp.json()
        key = data.get("key", "")
        return AdapterTaskResult(
            external_id=key,
            external_url=f"{site_url}/browse/{key}",
            raw=data,
        )
