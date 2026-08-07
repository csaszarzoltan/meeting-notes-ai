"""Todoist adapter for PM tool integration."""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.services.integrations.base import (
    Adapter,
    AdapterAuth,
    AdapterConnection,
    AdapterTaskResult,
)


class TodoistAdapter(Adapter):
    provider = "todoist"
    display_name = "Todoist"
    auth_type = "rest_token"

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        raise NotImplementedError("TodoistAdapter.connect not implemented")

    async def create_task(
        self, action: dict[str, Any], project: str | None = None, idempotency_key: str | None = None
    ) -> AdapterTaskResult:
        raise NotImplementedError("TodoistAdapter.create_task not implemented")
