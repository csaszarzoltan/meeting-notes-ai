"""Persisted fail-closed provider preflight."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import PolicyDecision, PolicyVersion
from meeting_notes_ai.services.governance.policies import evaluate_provider


async def enforce_provider(
    db: AsyncSession,
    *,
    meeting_id: str,
    team_id: str | None,
    provider: str,
    operation: str,
    available: bool = True,
) -> dict:
    if not team_id:
        return {"outcome": "allowed", "code": "COMPATIBILITY_MODE", "policy_version_id": None}
    policy = (
        (
            await db.execute(
                select(PolicyVersion)
                .where(PolicyVersion.team_id == team_id)
                .order_by(PolicyVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if not policy:
        return {"outcome": "allowed", "code": "COMPATIBILITY_MODE", "policy_version_id": None}
    result = evaluate_provider(json.loads(policy.provider_json or "{}"), provider, available)
    db.add(
        PolicyDecision(
            meeting_id=meeting_id,
            policy_version_id=policy.id,
            operation=operation,
            outcome=result["outcome"],
            reasons_json=json.dumps([result["code"]]),
        )
    )
    await db.flush()
    return {**result, "policy_version_id": policy.id}
