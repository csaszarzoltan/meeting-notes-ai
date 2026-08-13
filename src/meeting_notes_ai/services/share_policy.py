"""Central snapshot gate for all persistent share creation paths."""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import Meeting, PolicyVersion, PublishedSnapshot


async def eligible_snapshot(db: AsyncSession, meeting: Meeting) -> PublishedSnapshot | None:
    policy = None
    strict = meeting.mode in {"healthcare", "legal"}
    if not strict:
        return None
    if meeting.team_id:
        policy = (
            (
                await db.execute(
                    select(PolicyVersion)
                    .where(PolicyVersion.team_id == meeting.team_id)
                    .order_by(PolicyVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
    if policy:
        try:
            approval = json.loads(policy.approval_json or "{}")
            strict = bool(
                approval.get(meeting.mode, {}).get(
                    "strict_grounding", approval.get("strict_grounding", strict)
                )
            )
        except json.JSONDecodeError as exc:
            if strict:
                raise HTTPException(
                    409, {"code": "POLICY_NOT_SATISFIED", "blockers": [{"code": "POLICY_INVALID"}]}
                ) from exc
    snapshot = (
        (
            await db.execute(
                select(PublishedSnapshot)
                .where(PublishedSnapshot.meeting_id == meeting.id)
                .order_by(PublishedSnapshot.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if strict and snapshot is None:
        raise HTTPException(
            409, {"code": "POLICY_NOT_SATISFIED", "blockers": [{"code": "SNAPSHOT_REQUIRED"}]}
        )
    return snapshot
