"""Todoist adapter — REST token."""

from __future__ import annotations

from typing import Any

import httpx

from meeting_notes_ai.ratelimit import TokenBucketRateLimiter
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

_TODOIST_API = "https://api.todoist.com/rest/v2"


def _map_todoist_error(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    if status in (401, 403):
        raise AdapterAuthError(
            "Invalid or expired credentials for Todoist. Reconnect your account."
        ) from exc
    if status >= 500:
        raise AdapterUnavailableError(
            "Todoist is temporarily unavailable. Try again in a few minutes."
        ) from exc
    raise AdapterValidationError(
        "Check the project ID in your Todoist settings."
    ) from exc


class TodoistAdapter(Adapter):
    """Real Todoist integration via the REST API v2."""

    provider = "todoist"
    display_name = "Todoist"
    auth_type = "rest_token"
    _rate_limiter = TokenBucketRateLimiter(
        capacity=100, fill_rate=100 / 900  # 1000 req/15min
    )

    _auth: AdapterAuth | None = None

    def _resolve_auth(self, action: dict[str, Any]) -> AdapterAuth:
        if self._auth is None:
            raise AdapterValidationError("Todoist adapter not connected.")
        return self._auth

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate token by fetching projects."""
        await self._throttle()
        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.get(
                    f"{_TODOIST_API}/projects",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_todoist_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Todoist is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        self._auth = auth
        return AdapterConnection(
            account_email=auth.email or "todoist-user",
            account_url="https://todoist.com",
            token_expires_at=None,
        )

    async def create_task(
        self,
        action: dict[str, Any],
        project: str | None = None,
        idempotency_key: str | None = None,
    ) -> AdapterTaskResult:
        """Create a Todoist task."""
        await self._throttle()
        auth = self._resolve_auth(action)

        task_body: dict[str, Any] = {
            "content": action.get("title", "Untitled action"),
            "description": (
                f"Meeting: {action.get('meeting', 'N/A')}\n"
                f"Owner: {action.get('owner', 'Unassigned')}\n"
                f"Due: {action.get('due', 'Unscheduled')}"
            ),
        }
        if project:
            task_body["project_id"] = project
        due = action.get("due")
        if due and due != "Unscheduled":
            task_body["due_string"] = due
            task_body["due_lang"] = "en"

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
                    f"{_TODOIST_API}/tasks",
                    json=task_body,
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_todoist_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Todoist is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        data = resp.json()
        return AdapterTaskResult(
            external_id=str(data.get("id", "")),
            external_url=data.get("url", ""),
            raw=data,
        )
