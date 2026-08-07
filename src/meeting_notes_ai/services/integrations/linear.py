"""Linear adapter for PM tool integration."""

from __future__ import annotations

from typing import Any

from meeting_notes_ai.services.integrations.base import (
    Adapter,
    AdapterAuth,
    AdapterConnection,
    AdapterTaskResult,
)


class LinearAdapter(Adapter):
    provider = "linear"
    display_name = "Linear"
    auth_type = "api_key"

    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        raise NotImplementedError("LinearAdapter.connect not implemented")

    async def create_task(
        self, action: dict[str, Any], project: str | None = None, idempotency_key: str | None = None
    ) -> AdapterTaskResult:
        raise NotImplementedError("LinearAdapter.create_task not implemented")
