"""Linear adapter — API key (personal)."""

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

_CONNECT_QUERY = """
query ViewerInfo {
    viewer { id name email }
    organization { urlKey }
}
"""

_CREATE_ISSUE_MUTATION = """
mutation CreateIssue($input: IssueCreateInput!) {
    issueCreate(input: $input) {
        success
        issue { id identifier url }
    }
}
"""


def _map_linear_error(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    if status in (401, 403):
        raise AdapterAuthError(
            "Invalid or expired credentials for Linear. Reconnect your account."
        ) from exc
    if status >= 500:
        raise AdapterUnavailableError(
            "Linear is temporarily unavailable. Try again in a few minutes."
        ) from exc
    raise AdapterValidationError(
        "Check the team ID in your Linear settings."
    ) from exc


def _check_graphql_errors(body: dict[str, Any]) -> None:
    """Raise a friendly PMAdapterError for GraphQL-level failures.

    Linear returns HTTP 200 with an ``errors`` array for GraphQL errors
    (auth failures, validation failures, rate limits).  The HTTP status
    alone is not enough — we must inspect the body.
    """
    errors = body.get("errors") if isinstance(body, dict) else None
    if not errors:
        return
    first = errors[0] if isinstance(errors, list) else None
    message = ""
    if isinstance(first, dict):
        message = first.get("message", "")
    lowered = f"{message}".lower()
    if any(
        k in lowered for k in ("authentication", "unauthorized", "invalid api key", "forbidden")
    ):
        raise AdapterAuthError(
            "Invalid or expired credentials for Linear. Reconnect your account."
        )
    if any(k in lowered for k in ("rate limit", "rate_limit", "too many requests")):
        raise AdapterUnavailableError(
            "Linear rate limit reached. Try again in a few minutes."
        )
    if any(k in lowered for k in ("team", "teamid", "not found", "validation")):
        raise AdapterValidationError(
            "Check the team ID in your Linear settings."
        )
    # Fallback: any unexpected GraphQL error surfaces as an unavailable error
    # so the UI shows a friendly 502 instead of a 500 crash.
    raise AdapterUnavailableError(
        f"Linear returned an error: {message or 'unknown GraphQL error'}"
    )


class LinearAdapter(Adapter):
    """Real Linear integration via the GraphQL API."""

    provider = "linear"
    display_name = "Linear"
    auth_type = "api_key"

    _auth: AdapterAuth | None = None

    def _resolve_auth(self, action: dict[str, Any]) -> AdapterAuth:
        if self._auth is None:
            raise AdapterValidationError("Linear adapter not connected.")
        return self._auth

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate credentials by querying the viewer."""
        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.post(
                    "https://api.linear.app/graphql",
                    json={"query": _CONNECT_QUERY},
                    headers={"Authorization": auth.token},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_linear_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Linear is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        body = resp.json()
        # Linear returns HTTP 200 with an `errors` array on GraphQL failures.
        _check_graphql_errors(body)
        data = body.get("data") or {}
        viewer = data.get("viewer") or {}
        org = data.get("organization") or {}
        if not viewer:
            # e.g. `data: {"viewer": null}` — treat as unauthenticated
            raise AdapterAuthError(
                "Invalid or expired credentials for Linear. Reconnect your account."
            )
        url_key = org.get("urlKey", "")
        workspace_url = f"https://{url_key}.linear.app" if url_key else auth.workspace_url

        self._auth = auth
        return AdapterConnection(
            account_email=viewer.get("email", auth.email),
            account_url=workspace_url,
            token_expires_at=None,
        )

    async def create_task(
        self,
        action: dict[str, Any],
        project: str | None = None,
        idempotency_key: str | None = None,
    ) -> AdapterTaskResult:
        """Create a Linear issue via GraphQL mutation."""
        auth = self._resolve_auth(action)
        team_id = project or auth.default_project
        if not team_id:
            raise AdapterValidationError(
                "A team ID (project) is required for Linear task creation."
            )

        variables: dict[str, Any] = {
            "input": {
                "teamId": team_id,
                "title": action.get("title", "Untitled action"),
                "description": (
                    f"Meeting: {action.get('meeting', 'N/A')}\n"
                    f"Owner: {action.get('owner', 'Unassigned')}\n"
                    f"Due: {action.get('due', 'Unscheduled')}"
                ),
            }
        }
        due = action.get("due")
        if due and due != "Unscheduled":
            variables["input"]["dueDate"] = due

        headers: dict[str, str] = {"Authorization": auth.token}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp: httpx.Response | None = None
        async with get_http_client() as client:
            try:
                resp = await client.post(
                    "https://api.linear.app/graphql",
                    json={"query": _CREATE_ISSUE_MUTATION, "variables": variables},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _map_linear_error(exc)
            except httpx.TransportError as exc:
                raise AdapterUnavailableError(
                    "Linear is temporarily unavailable. Try again in a few minutes."
                ) from exc

        assert resp is not None
        body = resp.json()
        # Linear returns HTTP 200 with an `errors` array on GraphQL failures.
        _check_graphql_errors(body)
        issue_data = (body.get("data") or {}).get("issueCreate") or {}
        if not issue_data.get("success"):
            raise AdapterValidationError("Linear issue creation failed.")
        issue = issue_data.get("issue", {})
        return AdapterTaskResult(
            external_id=issue.get("id", ""),
            external_url=issue.get("url", ""),
            raw=body,
        )
