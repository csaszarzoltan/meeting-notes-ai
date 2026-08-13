"""Persistent trusted-record review APIs."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.models import (
    Claim,
    ClaimEvidence,
    Meeting,
    PublishedSnapshot,
    ReviewDecision,
    SpeakerMapping,
    TranscriptSegment,
)
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.evidence import SegmentSpan, validate_spans
from meeting_notes_ai.services.review import evaluate_policy

router = APIRouter(prefix="/api/v1/trusted", tags=["trusted-records"])


def uid(user: dict) -> str:
    return user.get("user_id") or user.get("sub") or user.get("id")


async def owned(db: AsyncSession, meeting_id: str, user: dict) -> Meeting:
    meeting = (
        await db.execute(
            select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == uid(user))
        )
    ).scalar_one_or_none()
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    return meeting


async def ensure_projection(db: AsyncSession, m: Meeting) -> None:
    existing = (
        await db.execute(select(func.count()).select_from(Claim).where(Claim.meeting_id == m.id))
    ).scalar_one()
    if existing:
        return
    segment = TranscriptSegment(
        meeting_id=m.id,
        ordinal=0,
        start_ms=0,
        end_ms=max(1, len(m.transcript or "") * 40),
        raw_speaker_label="Unknown",
        text=m.transcript or "",
        revision=1,
    )
    db.add(segment)
    await db.flush()
    values = [("summary", json.loads(m.metadata_json or "{}").get("summary", ""))]
    for kind, raw in (
        ("decision", m.decisions),
        ("key_point", m.key_points),
        ("action", m.action_items),
    ):
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError:
            data = []
        for item in data:
            values.append(
                (kind, item if isinstance(item, str) else item.get("description", json.dumps(item)))
            )
    for kind, text in values:
        if text:
            db.add(Claim(meeting_id=m.id, claim_type=kind, text=text, status="draft", version=1))


class EvidenceIn(BaseModel):
    segment_id: str
    start_ms: int
    end_ms: int


class ClaimUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    evidence: list[EvidenceIn] = Field(max_length=100)


class MappingIn(BaseModel):
    raw_label: str
    canonical_name: str = Field(min_length=1, max_length=200)
    user_id: str | None = None
    segment_ids: list[str] = Field(min_length=1, max_length=500)
    expected_transcript_version: int


class DecisionIn(BaseModel):
    decision: str
    reason: str | None = None


def claim_dict(c: Claim, evidence: list[ClaimEvidence]) -> dict:
    return {
        "id": c.id,
        "type": c.claim_type,
        "text": c.text,
        "status": c.status,
        "version": c.version,
        "evidence": [
            {"segment_id": e.segment_id, "start_ms": e.start_ms, "end_ms": e.end_ms}
            for e in evidence
        ],
    }


@router.get("/meetings/{meeting_id}/record")
async def record(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    m = await owned(db, meeting_id, user)
    await ensure_projection(db, m)
    await db.flush()
    segments = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.meeting_id == m.id)
                .order_by(TranscriptSegment.ordinal)
            )
        )
        .scalars()
        .all()
    )
    claims = (await db.execute(select(Claim).where(Claim.meeting_id == m.id))).scalars().all()
    evidence = (
        (await db.execute(select(ClaimEvidence).join(Claim).where(Claim.meeting_id == m.id)))
        .scalars()
        .all()
    )
    by = {c.id: [] for c in claims}
    for e in evidence:
        by[e.claim_id].append(e)
    latest = (
        (
            await db.execute(
                select(PublishedSnapshot)
                .where(PublishedSnapshot.meeting_id == m.id)
                .order_by(PublishedSnapshot.version.desc())
            )
        )
        .scalars()
        .first()
    )
    return {
        "meeting": {"id": m.id, "title": m.title, "mode": m.mode},
        "transcript_version": max([s.revision for s in segments], default=1),
        "segments": [
            {
                "id": s.id,
                "ordinal": s.ordinal,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "raw_speaker_label": s.raw_speaker_label,
                "speaker_id": s.speaker_id,
                "text": s.text,
                "confidence": s.confidence,
                "revision": s.revision,
            }
            for s in segments
        ],
        "claims": [claim_dict(c, by[c.id]) for c in claims],
        "snapshot": None
        if not latest
        else {"id": latest.id, "version": latest.version, "sha256": latest.payload_sha256},
    }


@router.put("/meetings/{meeting_id}/claims/{claim_id}")
async def update_claim(
    meeting_id: str,
    claim_id: str,
    body: ClaimUpdate,
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await owned(db, meeting_id, user)
    if if_match is None:
        raise HTTPException(428, "If-Match is required")
    claim = (
        await db.execute(select(Claim).where(Claim.id == claim_id, Claim.meeting_id == meeting_id))
    ).scalar_one_or_none()
    if not claim:
        raise HTTPException(404, "Claim not found")
    if str(claim.version) != if_match.strip('"'):
        raise HTTPException(409, {"code": "VERSION_CONFLICT", "current_version": claim.version})
    ids = [e.segment_id for e in body.evidence]
    segs = (
        (
            await db.execute(
                select(TranscriptSegment).where(
                    TranscriptSegment.id.in_(ids), TranscriptSegment.meeting_id == meeting_id
                )
            )
        )
        .scalars()
        .all()
    )
    sm = {s.id: s for s in segs}
    try:
        validate_spans(
            meeting_id,
            [
                SegmentSpan(
                    e.segment_id,
                    meeting_id,
                    sm[e.segment_id].start_ms,
                    sm[e.segment_id].end_ms,
                    e.start_ms,
                    e.end_ms,
                )
                for e in body.evidence
                if e.segment_id in sm
            ],
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, {"code": "INVALID_EVIDENCE", "message": str(exc)}) from exc
    if len(sm) != len(set(ids)):
        raise HTTPException(422, {"code": "INVALID_EVIDENCE", "message": "Unknown segment"})
    claim.text = body.text
    claim.version += 1
    claim.status = "draft"
    await db.execute(delete(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id))
    for i, e in enumerate(body.evidence):
        db.add(
            ClaimEvidence(
                claim_id=claim.id,
                segment_id=e.segment_id,
                start_ms=e.start_ms,
                end_ms=e.end_ms,
                ordinal=i,
            )
        )
    response.headers["ETag"] = f'"{claim.version}"'
    return {"id": claim.id, "version": claim.version, "status": claim.status}


@router.post("/meetings/{meeting_id}/speaker-mappings")
async def map_speaker(
    meeting_id: str,
    body: MappingIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await owned(db, meeting_id, user)
    segs = (
        (
            await db.execute(
                select(TranscriptSegment).where(
                    TranscriptSegment.id.in_(body.segment_ids),
                    TranscriptSegment.meeting_id == meeting_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if len(segs) != len(set(body.segment_ids)):
        raise HTTPException(422, "Unknown segment")
    if any(s.revision != body.expected_transcript_version for s in segs):
        raise HTTPException(409, "Stale transcript version")
    mapping = SpeakerMapping(
        meeting_id=meeting_id,
        raw_label=body.raw_label,
        canonical_name=body.canonical_name.strip(),
        user_id=body.user_id,
        version=body.expected_transcript_version + 1,
        created_by=uid(user),
    )
    db.add(mapping)
    for s in segs:
        s.speaker_id = body.user_id or mapping.id
        s.revision += 1
    claims = (
        (
            await db.execute(
                select(Claim).where(Claim.meeting_id == meeting_id, Claim.status == "approved")
            )
        )
        .scalars()
        .all()
    )
    for c in claims:
        c.status = "needs_reapproval"
    return {
        "mapping_id": mapping.id,
        "transcript_version": body.expected_transcript_version + 1,
        "impacted_claim_ids": [c.id for c in claims],
    }


@router.post("/meetings/{meeting_id}/claims/{claim_id}/decisions")
async def decide(
    meeting_id: str,
    claim_id: str,
    body: DecisionIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await owned(db, meeting_id, user)
    claim = (
        await db.execute(select(Claim).where(Claim.id == claim_id, Claim.meeting_id == meeting_id))
    ).scalar_one_or_none()
    if not claim:
        raise HTTPException(404, "Claim not found")
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(422, "Invalid decision")
    claim.status = "approved" if body.decision == "approve" else "rejected"
    db.add(
        ReviewDecision(
            claim_id=claim.id,
            claim_version=claim.version,
            decision=body.decision,
            reason=body.reason,
            actor_id=uid(user),
        )
    )
    return {"claim_id": claim.id, "status": claim.status}


@router.post("/meetings/{meeting_id}/publish", status_code=201)
async def publish(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    m = await owned(db, meeting_id, user)
    claims = (await db.execute(select(Claim).where(Claim.meeting_id == meeting_id))).scalars().all()
    evidence = (await db.execute(select(ClaimEvidence))).scalars().all()
    ev = {e.claim_id for e in evidence}
    approvals = (
        (
            await db.execute(
                select(ReviewDecision).where(
                    ReviewDecision.claim_id.in_([c.id for c in claims]),
                    ReviewDecision.decision == "approve",
                )
            )
        )
        .scalars()
        .all()
    )
    ap = {a.claim_id for a in approvals}
    payload_claims = [
        {
            "id": c.id,
            "text": c.text,
            "status": c.status,
            "evidence": [1] if c.id in ev else [],
            "approver_ids": [1] if c.id in ap else [],
        }
        for c in claims
    ]
    blockers = evaluate_policy(
        payload_claims,
        m.mode in {"healthcare", "legal"},
        1 if m.mode in {"healthcare", "legal"} else 0,
    )
    if blockers:
        raise HTTPException(409, {"code": "POLICY_NOT_SATISFIED", "blockers": blockers})
    version = (
        await db.execute(
            select(func.count())
            .select_from(PublishedSnapshot)
            .where(PublishedSnapshot.meeting_id == meeting_id)
        )
    ).scalar_one() + 1
    payload = json.dumps(
        {"meeting_id": meeting_id, "version": version, "claims": payload_claims},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    snap = PublishedSnapshot(
        meeting_id=meeting_id,
        version=version,
        payload_json=payload,
        payload_sha256=digest,
        created_by=uid(user),
    )
    db.add(snap)
    await db.flush()
    if m.team_id:
        from meeting_notes_ai.services.governance.repository import ArtifactRegistry

        await ArtifactRegistry(db).register(
            team_id=m.team_id,
            meeting_id=m.id,
            kind="published_snapshot",
            source_key=f"snapshot:{m.id}:{version}",
            location_class="database",
            content=payload.encode(),
            policy_version_id=snap.policy_version_id,
        )
    return {"snapshot_id": snap.id, "version": version, "sha256": digest}


@router.get("/meetings/{meeting_id}/activity")
async def activity(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await owned(db, meeting_id, user)
    claims = (
        (await db.execute(select(Claim.id).where(Claim.meeting_id == meeting_id))).scalars().all()
    )
    rows = (
        (
            await db.execute(
                select(ReviewDecision)
                .where(ReviewDecision.claim_id.in_(claims))
                .order_by(ReviewDecision.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "event": r.decision,
            "actor_id": r.actor_id,
            "claim_version": r.claim_version,
            "at": r.created_at,
        }
        for r in rows
    ]
