"""Asana adapter — Personal Access Token (PAT)."""

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

_ASANA_API = "https://app.asana.com/api/1.0"


def _map_asana_error(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    if status in (401, 403):
        raise AdapterAuthError(
            "Invalid or expired credentials for Asana. Reconnect your account."
        ) from exc
    if status >= 500:
        raise AdapterUnavailableError(
            "Asana is temporarily unavailable. Try again in a few minutes."
        ) from exc
    raise AdapterValidationError(
        "Check the workspace/project GID in your Asana settings."
    ) from exc


class AsanaAdapter(Adapter):
    """Real Asana integration via the REST API v1."""

    provider = "asana"
    display_name = "Asana"
    auth_type = "pat"
    _rate_limiter = TokenBucketRateLimiter(
        capacity=150, fill_rate=150 / 60  # 1500 calls/min
    )

    _auth: AdapterAuth | None = None

    def _resolve_auth(self, action: dict[str, Any]) -> AdapterAuth:
        if self._auth is None:
            raise AdapterValidationError("Asana adapter not connected.")
        return self._auth

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate PAT and fetch user profile + first workspace."""
        await self._throttle()
        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.get(
                    f"{_ASANA_API}/users/me",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_asana_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Asana is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        user_data = resp.json().get("data", {})
        account_email = user_data.get("email", auth.email)

        # Fetch workspaces to get the default workspace GID
        ws_resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                ws_resp = await client.get(
                    f"{_ASANA_API}/workspaces",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
            except (httpx.HTTPStatusError, httpx.TransportError):
                pass  # Best effort; workspace URL is optional

        account_url = "https://app.asana.com"
        if ws_resp and ws_resp.is_success:
            workspaces = ws_resp.json().get("data", [])
            if workspaces:
                account_url = workspaces[0].get("permalink_url", "https://app.asana.com")

        self._auth = auth
        return AdapterConnection(
            account_email=account_email,
            account_url=account_url,
            token_expires_at=None,
        )

    async def create_task(
        self,
        action: dict[str, Any],
        project: str | None = None,
        idempotency_key: str | None = None,
    ) -> AdapterTaskResult:
        """Create an Asana task."""
        await self._throttle()
        auth = self._resolve_auth(action)
        workspace_gid = auth.default_project
        if not workspace_gid:
            raise AdapterValidationError(
                "A workspace GID (project) is required for Asana task creation."
            )

        task_body: dict[str, Any] = {
            "workspace": workspace_gid,
            "name": action.get("title", "Untitled action"),
            "notes": (
                f"Meeting: {action.get('meeting', 'N/A')}\n"
                f"Owner: {action.get('owner', 'Unassigned')}\n"
                f"Due: {action.get('due', 'Unscheduled')}"
            ),
        }
        if project:
            task_body["projects"] = [project]
        due = action.get("due")
        if due and due != "Unscheduled":
            task_body["due_on"] = due

        headers: dict[str, str] = {
            "Authorization": f"Bearer {auth.token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.post(
                    f"{_ASANA_API}/tasks",
                    json={"data": task_body},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_asana_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Asana is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        data = resp.json().get("data", {})
        return AdapterTaskResult(
            external_id=data.get("gid", ""),
            external_url=data.get("permalink_url", ""),
            raw=data,
        )
