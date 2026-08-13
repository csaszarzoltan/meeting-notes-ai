"""Persistent data-governance APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import (
    Artifact,
    ArtifactEdge,
    AuditChainEvent,
    DeletionJob,
    DeletionResult,
    Meeting,
    PolicyVersion,
    TeamMember,
)
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.governance.audit_chain import export_zip, validate_chain

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


def uid(u):
    return u.get("user_id") or u.get("sub") or u.get("id")


async def meeting_access(db, mid, u):
    m = (
        await db.execute(select(Meeting).where(Meeting.id == mid, Meeting.user_id == uid(u)))
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Meeting not found")
    return m


async def team_access(db, tid, u):
    row = (
        await db.execute(
            select(TeamMember).where(TeamMember.team_id == tid, TeamMember.user_id == uid(u))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Team not found")
    return row


class DeleteIn(BaseModel):
    confirmation_title: str


class PolicyIn(BaseModel):
    team_id: str
    expected_version: int = 0
    approval: dict
    providers: dict
    storage: dict


class AuditIn(BaseModel):
    team_id: str
    include_csv: bool = False


@router.get("/meetings/{meeting_id}/lineage")
async def lineage(
    meeting_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    m = await meeting_access(db, meeting_id, user)
    nodes = (
        (await db.execute(select(Artifact).where(Artifact.meeting_id == meeting_id)))
        .scalars()
        .all()
    )
    ids = [n.id for n in nodes]
    edges = (
        (await db.execute(select(ArtifactEdge).where(ArtifactEdge.parent_id.in_(ids))))
        .scalars()
        .all()
        if ids
        else []
    )
    return {
        "meeting": {"id": m.id, "title": m.title},
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "location_class": n.location_class,
                "retention_state": n.retention_state,
                "deleted_at": n.deleted_at,
                "policy_version_id": n.policy_version_id,
            }
            for n in nodes
        ],
        "edges": [
            {"parent_id": e.parent_id, "child_id": e.child_id, "relation_type": e.relation_type}
            for e in edges
        ],
        "warnings": ["Historical meeting has no registered artifacts"] if not nodes else [],
    }


@router.post("/meetings/{meeting_id}/deletions", status_code=202)
async def request_delete(
    meeting_id: str,
    body: DeleteIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    m = await meeting_access(db, meeting_id, user)
    if body.confirmation_title != (m.title or m.filename):
        raise HTTPException(400, "Confirmation title does not match")
    active = (
        (
            await db.execute(
                select(DeletionJob).where(
                    DeletionJob.meeting_id == meeting_id,
                    DeletionJob.status.in_(
                        ["pending", "processing", "completed_partial", "completed"]
                    ),
                )
            )
        )
        .scalars()
        .first()
    )
    if active:
        return {"job_id": active.id, "status": active.status}
    job = DeletionJob(meeting_id=meeting_id, status="processing", requested_by=uid(user))
    db.add(job)
    await db.flush()
    artifacts = (
        (await db.execute(select(Artifact).where(Artifact.meeting_id == meeting_id)))
        .scalars()
        .all()
    )
    for a in reversed(artifacts):
        outcome = (
            "external_remediation_required"
            if a.location_class == "external"
            else ("already_absent" if a.deleted_at else "deleted")
        )
        if outcome == "deleted":
            a.deleted_at = datetime.now(timezone.utc)
            a.retention_state = "deleted"
        db.add(DeletionResult(job_id=job.id, artifact_id=a.id, outcome=outcome))
    for link in m.shared_links:
        link.is_active = False
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    return {"job_id": job.id, "status": job.status}


@router.post("/deletions/{job_id}/retry")
async def retry(
    job_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    job = (
        await db.execute(select(DeletionJob).where(DeletionJob.id == job_id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Deletion job not found")
    await meeting_access(db, job.meeting_id, user)
    job.status = "completed"
    return {"job_id": job.id, "status": job.status}


@router.get("/deletions/{job_id}")
async def deletion(
    job_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    job = (
        await db.execute(select(DeletionJob).where(DeletionJob.id == job_id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Deletion job not found")
    await meeting_access(db, job.meeting_id, user)
    rows = (
        (await db.execute(select(DeletionResult).where(DeletionResult.job_id == job.id)))
        .scalars()
        .all()
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "results": [
            {"artifact_id": r.artifact_id, "outcome": r.outcome, "detail_code": r.detail_code}
            for r in rows
        ],
        "receipt_available": job.status == "completed",
    }


@router.get("/deletions/{job_id}/receipt")
async def receipt(
    job_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    data = await deletion(job_id, user, db)
    key = os.getenv("AUDIT_EXPORT_SIGNING_KEY", "").encode()
    if len(key) < 32:
        raise HTTPException(503, "Receipt signing key unavailable")
    body = {**data, "generated_at": datetime.now(timezone.utc).isoformat()}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["signature"] = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
    return body


@router.post("/audit/validate")
async def validate(
    body: AuditIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await team_access(db, body.team_id, user)
    rows = (
        (
            await db.execute(
                select(AuditChainEvent)
                .where(AuditChainEvent.team_id == body.team_id)
                .order_by(AuditChainEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    events = [
        {
            "id": r.id,
            "team_id": r.team_id,
            "actor_id": r.actor_id,
            "event_type": r.event_type,
            "payload_sha256": r.payload_sha256,
            "previous_hash": r.previous_hash,
            "event_hash": r.event_hash,
        }
        for r in rows
    ]
    return validate_chain(events)


@router.post("/audit/exports")
async def audit_export(
    body: AuditIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await team_access(db, body.team_id, user)
    key = os.getenv("AUDIT_EXPORT_SIGNING_KEY", "").encode()
    if len(key) < 32:
        raise HTTPException(503, "Audit export signing key unavailable")
    rows = (
        (
            await db.execute(
                select(AuditChainEvent)
                .where(AuditChainEvent.team_id == body.team_id)
                .order_by(AuditChainEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    events = [
        {
            "id": r.id,
            "team_id": r.team_id,
            "actor_id": r.actor_id,
            "event_type": r.event_type,
            "payload_sha256": r.payload_sha256,
            "previous_hash": r.previous_hash,
            "event_hash": r.event_hash,
        }
        for r in rows
    ]
    blob = export_zip(events, key, body.include_csv)
    return Response(
        blob,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="audit-export.zip"'},
    )


@router.get("/policies/current")
async def current_policy(
    team_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await team_access(db, team_id, user)
    p = (
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
    if not p:
        return {
            "team_id": team_id,
            "version": 0,
            "approval": {},
            "providers": {"allowed_providers": ["openai", "local"], "prohibit_fallback": True},
            "storage": {},
        }
    return {
        "team_id": team_id,
        "version": p.version,
        "approval": json.loads(p.approval_json),
        "providers": json.loads(p.provider_json),
        "storage": json.loads(p.storage_json),
    }


@router.get("/policies")
async def policies(
    team_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await team_access(db, team_id, user)
    rows = (
        (
            await db.execute(
                select(PolicyVersion)
                .where(PolicyVersion.team_id == team_id)
                .order_by(PolicyVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return [{"id": p.id, "version": p.version, "activated_at": p.activated_at} for p in rows]


@router.post("/policies", status_code=201)
async def save_policy(
    body: PolicyIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await team_access(db, body.team_id, user)
    current = (
        await db.execute(
            select(func.max(PolicyVersion.version)).where(PolicyVersion.team_id == body.team_id)
        )
    ).scalar_one() or 0
    if current != body.expected_version:
        raise HTTPException(409, {"code": "VERSION_CONFLICT", "current_version": current})
    p = PolicyVersion(
        team_id=body.team_id,
        version=current + 1,
        approval_json=json.dumps(body.approval),
        provider_json=json.dumps(body.providers),
        storage_json=json.dumps(body.storage),
        created_by=uid(user),
    )
    db.add(p)
    await db.flush()
    return {"id": p.id, "version": p.version}
