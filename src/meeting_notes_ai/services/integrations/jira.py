"""Jira adapter for PM tool integration."""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.services.integrations.base import (
    Adapter,
    AdapterAuth,
    AdapterConnection,
    AdapterTaskResult,
)


class JiraAdapter(Adapter):
    provider = "jira"
    display_name = "Jira"
    auth_type = "oauth2"

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        raise NotImplementedError("JiraAdapter.connect not implemented")

    async def create_task(
        self, action: dict[str, Any], project: str | None = None, idempotency_key: str | None = None
    ) -> AdapterTaskResult:
        raise NotImplementedError("JiraAdapter.create_task not implemented")
