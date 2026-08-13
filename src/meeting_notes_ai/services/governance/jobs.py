"""Durable deletion worker orchestration."""

import json
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import Artifact, DeletionJob, DeletionResult, Meeting, SharedLink
from meeting_notes_ai.services.governance.receipts import sign_receipt


async def run_deletion_job(db: AsyncSession, job_id: str) -> DeletionJob:
    job = (await db.execute(select(DeletionJob).where(DeletionJob.id == job_id))).scalar_one()
    if job.status == "completed":
        return job
    job.status = "processing"
    job.attempts += 1
    meeting = (await db.execute(select(Meeting).where(Meeting.id == job.meeting_id))).scalar_one()
    artifacts = (
        (await db.execute(select(Artifact).where(Artifact.meeting_id == job.meeting_id)))
        .scalars()
        .all()
    )
    existing = {
        (r.artifact_id, r.outcome)
        for r in (await db.execute(select(DeletionResult).where(DeletionResult.job_id == job.id)))
        .scalars()
        .all()
    }
    results = []
    for a in reversed(artifacts):
        if any(
            x[0] == a.id and x[1] in {"deleted", "already_absent", "external_remediation_required"}
            for x in existing
        ):
            continue
        outcome = (
            "external_remediation_required"
            if a.location_class == "external"
            else ("already_absent" if a.deleted_at else "deleted")
        )
        if outcome == "deleted":
            a.deleted_at = datetime.now(timezone.utc)
            a.retention_state = "deleted"
        row = DeletionResult(job_id=job.id, artifact_id=a.id, outcome=outcome)
        db.add(row)
        results.append({"artifact_id": a.id, "kind": a.kind, "outcome": outcome})
    for share in (
        (await db.execute(select(SharedLink).where(SharedLink.meeting_id == meeting.id)))
        .scalars()
        .all()
    ):
        share.is_active = False
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    body = {
        "job_id": job.id,
        "meeting_id": meeting.id,
        "requested_by": job.requested_by,
        "generated_at": job.completed_at.isoformat(),
        "results": results,
    }
    key = os.getenv("AUDIT_EXPORT_SIGNING_KEY", "").encode()
    if len(key) >= 32:
        job.receipt_json = json.dumps(sign_receipt(body, key), sort_keys=True)
    return job
