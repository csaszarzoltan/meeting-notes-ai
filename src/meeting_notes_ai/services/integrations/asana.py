"""Asana adapter for PM tool integration."""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.services.integrations.base import (
    Adapter,
    AdapterAuth,
    AdapterConnection,
    AdapterTaskResult,
)


class AsanaAdapter(Adapter):
    provider = "asana"
    display_name = "Asana"
    auth_type = "pat"

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        raise NotImplementedError("AsanaAdapter.connect not implemented")

    async def create_task(
        self, action: dict[str, Any], project: str | None = None, idempotency_key: str | None = None
    ) -> AdapterTaskResult:
        raise NotImplementedError("AsanaAdapter.create_task not implemented")
