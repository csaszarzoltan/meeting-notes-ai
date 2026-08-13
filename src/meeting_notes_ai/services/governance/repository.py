"""Persistent, tenant-safe artifact registry."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import Artifact, ArtifactEdge


class ArtifactRegistry:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        *,
        team_id: str,
        meeting_id: str,
        kind: str,
        source_key: str,
        location_class: str,
        location_ref_encrypted: str = "",
        content: bytes | None = None,
        policy_version_id: str | None = None,
        parent_id: str | None = None,
        relation_type: str = "derived_from",
        status: str = "active",
        error_code: str | None = None,
    ) -> Artifact:
        existing = (
            await self.db.execute(
                select(Artifact).where(
                    Artifact.team_id == team_id, Artifact.source_key == source_key
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        item = Artifact(
            team_id=team_id,
            meeting_id=meeting_id,
            kind=kind,
            source_key=source_key,
            location_class=location_class,
            location_ref_encrypted=location_ref_encrypted,
            content_sha256=hashlib.sha256(content).hexdigest() if content is not None else None,
            retention_state="active",
            policy_version_id=policy_version_id,
            status=status,
            error_code=error_code,
        )
        self.db.add(item)
        await self.db.flush()
        if parent_id:
            parent = (
                await self.db.execute(
                    select(Artifact).where(
                        Artifact.id == parent_id,
                        Artifact.team_id == team_id,
                        Artifact.meeting_id == meeting_id,
                    )
                )
            ).scalar_one_or_none()
            if not parent or parent.id == item.id:
                raise ValueError("Invalid artifact parent")
            self.db.add(
                ArtifactEdge(parent_id=parent.id, child_id=item.id, relation_type=relation_type)
            )
        return item

    async def mark_failed(self, artifact: Artifact, code: str) -> None:
        artifact.status = "failed"
        artifact.error_code = code[:100]
