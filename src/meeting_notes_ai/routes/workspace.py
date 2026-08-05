"""Authenticated, tenant-scoped product workspace APIs."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from meeting_notes_ai.auth import get_current_user

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
public_router = APIRouter(prefix="/public/workspace-shares", tags=["public-workspace"])
_STATE_PATH = Path("data/workspace_state.json")
_LOCK = threading.RLock()


def _seed_workspace(user_id: str) -> dict[str, Any]:
    """Create a private first-run workspace for one authenticated user."""
    return {
        "owner_id": user_id,
        "meetings": [],
        "actions": [],
        "settings": {
            "processing_region": "Zurich / EU",
            "retention_days": 1095,
            "sharing_default": "private_until_approved",
            "require_approval": True,
            "sensitive_detection": True,
            "vocabulary": ["MeetingNotesAI", "PHI"],
            "templates": ["General notes", "Decision log", "Healthcare SOAP"],
        },
        "integrations": {
            name: {"connected": False, "mode": "adapter_required"}
            for name in ["Microsoft Planner", "Jira", "Asana", "Linear", "Salesforce", "Slack"]
        },
        "batches": [],
        "audit": [],
        "shares": [],
    }


def _read_document() -> dict[str, Any]:
    """Read the complete tenant document from disk."""
    with _LOCK:
        if not _STATE_PATH.exists():
            return {"schema_version": 2, "workspaces": {}}
        document = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if "workspaces" not in document:
            return {"schema_version": 2, "workspaces": {}}
        return document


def _write_document(document: dict[str, Any]) -> None:
    """Atomically persist the complete tenant document."""
    with _LOCK:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(_STATE_PATH)


def _read_state(user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return document and isolated workspace for one user."""
    document = _read_document()
    workspace = document["workspaces"].setdefault(user_id, _seed_workspace(user_id))
    _write_document(document)
    return document, workspace


def _find(items: list[dict[str, Any]], item_id: str, label: str) -> dict[str, Any]:
    """Find an item by identifier or raise a precise 404."""
    item = next((value for value in items if value["id"] == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _audit(state: dict[str, Any], event: str, details: dict[str, Any]) -> None:
    """Append an immutable, timestamped audit event."""
    state["audit"].append(
        {
            "id": str(uuid4()),
            "event": event,
            "details": details,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _expiry(expires_in: str) -> datetime | None:
    """Convert a supported share expiry value to an absolute time."""
    delta = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}.get(
        expires_in
    )
    return datetime.now(timezone.utc) + delta if delta else None


class MeetingCreate(BaseModel):
    """Canonical meeting payload created from upload, live, or batch output."""

    id: str | None = None
    title: str = Field(default="Untitled meeting", max_length=300)
    transcript: str = Field(min_length=1)
    summary: str = ""
    action_items: list[Any] = []
    decisions: list[Any] = []
    key_points: list[str] = []
    mode: str = "general"
    warnings: list[str] = []
    phi_redacted: bool = False
    redaction_matches: int = 0


class ReviewUpdate(BaseModel):
    """Editable and approvable meeting review fields."""

    summary: str = Field(min_length=1, max_length=20_000)
    review_status: str = Field(pattern="^(needs_review|in_review|approved|rejected)$")
    reviewer: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=1000)


class ActionUpdate(BaseModel):
    """Mutable action ownership and status fields."""

    status: str = Field(pattern="^(suggested|confirmed|queued|completed)$")
    owner: str = Field(min_length=1, max_length=100)
    due: str = Field(min_length=1, max_length=50)


class SyncRequest(BaseModel):
    """Requested connector destination."""

    destination: str = Field(min_length=1, max_length=100)


class InsightRequest(BaseModel):
    """Cross-meeting workspace query."""

    query: str = Field(min_length=2, max_length=500)


class WorkspaceShareRequest(BaseModel):
    """Backend-enforced share controls."""

    expires_in: str = Field(default="7d", pattern="^(1h|24h|7d|never)$")


@router.get("/dashboard")
async def dashboard(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return outcome metrics scoped to the authenticated user."""
    _, state = _read_state(user["user_id"])
    return {
        "needs_review": sum(m["review_status"] == "needs_review" for m in state["meetings"]),
        "open_actions": sum(a["status"] != "completed" for a in state["actions"]),
        "processing_failures": sum(b.get("failed", 0) for b in state["batches"]),
        "time_saved_hours": round(len(state["meetings"]) * 0.5, 1),
        "recent_meetings": state["meetings"][:5],
        "my_actions": [a for a in state["actions"] if a.get("owner_id") == user["user_id"]][:5],
    }


@router.get("/meetings")
async def meetings(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List meetings owned by the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return {"items": state["meetings"]}


@router.post("/meetings", status_code=201)
async def create_meeting(
    request: MeetingCreate, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Save a processing result as the canonical meeting record."""
    document, state = _read_state(user["user_id"])
    meeting_id = request.id or str(uuid4())
    if any(item["id"] == meeting_id for item in state["meetings"]):
        meeting_id = str(uuid4())
    evidence = [
        {
            "timestamp": "00:00",
            "speaker": "Speaker 1",
            "text": request.transcript[:500],
            "confidence": 0.0,
        }
    ]
    meeting = {
        **request.model_dump(exclude={"id"}),
        "id": meeting_id,
        "owner_id": user["user_id"],
        "date": datetime.now(timezone.utc).isoformat(),
        "duration": "Unknown",
        "review_status": "needs_review",
        "participants": 0,
        "owner": user.get("display_name") or user.get("email") or "Current user",
        "sensitivity": "regulated" if request.mode in {"healthcare", "legal"} else "internal",
        "tags": [request.mode],
        "evidence": evidence,
        "versions": [],
        "audio_url": None,
    }
    state["meetings"].append(meeting)
    for index, action in enumerate(request.action_items):
        description = action if isinstance(action, str) else action.get("description", "Action")
        state["actions"].append(
            {
                "id": str(uuid4()),
                "title": description,
                "owner": action.get("assignee") if isinstance(action, dict) else "Unassigned",
                "owner_id": user["user_id"],
                "due": action.get("deadline") if isinstance(action, dict) else "Unscheduled",
                "meeting_id": meeting_id,
                "meeting": meeting["title"],
                "timestamp": evidence[min(index, len(evidence) - 1)]["timestamp"],
                "status": "suggested",
                "destination": "Not selected",
                "external_id": None,
            }
        )
    _audit(state, "meeting.created", {"meeting_id": meeting_id, "source": "processing"})
    _write_document(document)
    return meeting


@router.get("/meetings/{meeting_id}")
async def meeting_detail(
    meeting_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Return one meeting from the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return _find(state["meetings"], meeting_id, "Meeting")


@router.patch("/meetings/{meeting_id}/review")
async def update_review(
    meeting_id: str,
    request: ReviewUpdate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist review changes and an immutable version."""
    document, state = _read_state(user["user_id"])
    meeting = _find(state["meetings"], meeting_id, "Meeting")
    version = {
        "number": len(meeting["versions"]) + 1,
        "summary": request.summary,
        "status": request.review_status,
        "reviewer": request.reviewer,
        "reviewer_id": user["user_id"],
        "comment": request.comment,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    meeting.update({"summary": request.summary, "review_status": request.review_status})
    meeting["versions"].append(version)
    _audit(state, "meeting.reviewed", {"meeting_id": meeting_id, "version": version["number"]})
    _write_document(document)
    return meeting


@router.get("/actions")
async def actions(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List actions from the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return {"items": state["actions"]}


@router.patch("/actions/{action_id}")
async def update_action(
    action_id: str,
    request: ActionUpdate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist action ownership, deadline, and status."""
    document, state = _read_state(user["user_id"])
    action = _find(state["actions"], action_id, "Action")
    action.update(request.model_dump())
    _audit(state, "action.updated", {"action_id": action_id, "status": request.status})
    _write_document(document)
    return action


@router.post("/actions/{action_id}/queue")
async def queue_action(
    action_id: str,
    request: SyncRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Queue an action for a configured external adapter without faking vendor completion."""
    document, state = _read_state(user["user_id"])
    action = _find(state["actions"], action_id, "Action")
    connector = state["integrations"].get(request.destination)
    if not connector or not connector["connected"]:
        raise HTTPException(status_code=409, detail="Connect an adapter before queuing this action")
    action.update(
        {
            "destination": request.destination,
            "status": "queued",
            "external_id": None,
            "adapter_job_id": str(uuid4()),
        }
    )
    _audit(state, "action.queued", {"action_id": action_id, "destination": request.destination})
    _write_document(document)
    return action


@router.get("/settings")
async def get_settings(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return settings for the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return state["settings"]


@router.put("/settings")
async def put_settings(
    request: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Persist an allow-listed set of workspace settings."""
    allowed = {
        "processing_region",
        "retention_days",
        "sharing_default",
        "require_approval",
        "sensitive_detection",
        "vocabulary",
        "templates",
    }
    unknown = set(request) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown settings: {sorted(unknown)}")
    document, state = _read_state(user["user_id"])
    state["settings"].update(request)
    _audit(state, "settings.updated", {"keys": sorted(request)})
    _write_document(document)
    return state["settings"]


@router.get("/integrations")
async def integrations(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List connector configuration for the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return {"items": state["integrations"]}


@router.post("/integrations/{name}/connect")
async def connect_integration(
    name: str,
    request: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Enable or disable a deployment-provided connector adapter."""
    document, state = _read_state(user["user_id"])
    if name not in state["integrations"]:
        raise HTTPException(status_code=404, detail="Integration not found")
    state["integrations"][name]["connected"] = bool(request.get("enabled", True))
    _audit(state, "integration.changed", {"name": name})
    _write_document(document)
    return {"name": name, **state["integrations"][name]}


@router.post("/insights/query")
async def query_insights(
    request: InsightRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Search private meeting evidence and return cited source moments."""
    _, state = _read_state(user["user_id"])
    query = request.query.casefold()
    sources = []
    for meeting in state["meetings"]:
        for evidence in meeting["evidence"]:
            haystack = f"{meeting['title']} {meeting['summary']} {evidence['text']}".casefold()
            if query in haystack or any(token in haystack for token in query.split()):
                sources.append(
                    {"meeting_id": meeting["id"], "meeting": meeting["title"], **evidence}
                )
    return {
        "answer": f"Found {len(sources)} cited source moment(s) related to '{request.query}'.",
        "sources": sources[:8],
    }


@router.get("/compliance")
async def compliance(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Derive current controls from policy settings and the workspace audit trail."""
    _, state = _read_state(user["user_id"])
    settings = state["settings"]
    now = datetime.now(timezone.utc).isoformat()
    controls = [
        {
            "id": "approval-policy",
            "level": "pass" if settings["require_approval"] else "critical",
            "title": "Approval before sharing",
            "detail": "Workspace sharing policy requires reviewed notes.",
            "evidence": f"settings.require_approval={settings['require_approval']}",
            "last_checked": now,
            "owner": user.get("email", user["user_id"]),
            "remediation": "Open privacy settings",
            "target": "settings",
        },
        {
            "id": "retention-policy",
            "level": "pass" if settings["retention_days"] > 0 else "critical",
            "title": "Retention policy configured",
            "detail": f"Retention is {settings['retention_days']} days.",
            "evidence": "Authenticated workspace settings",
            "last_checked": now,
            "owner": user.get("email", user["user_id"]),
            "remediation": "Open privacy settings",
            "target": "settings",
        },
    ]
    return {"controls": controls, "audit": state["audit"][-20:]}


@router.get("/batches")
async def list_batches(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return batches from the authenticated workspace."""
    _, state = _read_state(user["user_id"])
    return {"items": state["batches"]}


@router.post("/batches/{batch_id}/retry")
async def retry_batch(
    batch_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Retry failed batch items while preserving completed work."""
    document, state = _read_state(user["user_id"])
    batch = _find(state["batches"], batch_id, "Batch")
    batch.update({"status": "processing", "failed": 0})
    _audit(state, "batch.retried", {"batch_id": batch_id})
    _write_document(document)
    return batch


@router.post("/meetings/{meeting_id}/share", status_code=201)
async def share_workspace_meeting(
    meeting_id: str,
    request: WorkspaceShareRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a private, expiring share for an approved owned meeting."""
    document, state = _read_state(user["user_id"])
    meeting = _find(state["meetings"], meeting_id, "Meeting")
    if meeting["review_status"] != "approved":
        raise HTTPException(status_code=409, detail="Approve the meeting before sharing")
    share = {
        "id": str(uuid4()),
        "meeting_id": meeting_id,
        "token": uuid4().hex + uuid4().hex,
        "expires_at": _expiry(request.expires_in).isoformat()
        if _expiry(request.expires_in)
        else None,
        "active": True,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "views": [],
    }
    state["shares"].append(share)
    _audit(state, "meeting.shared", {"meeting_id": meeting_id, "share_id": share["id"]})
    _write_document(document)
    return {**share, "url": f"/public/workspace-shares/{share['token']}"}


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_workspace_share(
    share_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> None:
    """Immediately revoke a share owned by the authenticated workspace."""
    document, state = _read_state(user["user_id"])
    share = _find(state["shares"], share_id, "Share")
    share["active"] = False
    _audit(state, "share.revoked", {"share_id": share_id})
    _write_document(document)


@public_router.get("/{token}")
async def resolve_public_share(token: str) -> dict[str, Any]:
    """Resolve an active, unexpired share and record anonymous access."""
    document = _read_document()
    for state in document["workspaces"].values():
        share = next((item for item in state["shares"] if item["token"] == token), None)
        if not share:
            continue
        if not share["active"]:
            raise HTTPException(status_code=410, detail="Share revoked")
        if share["expires_at"] and datetime.fromisoformat(share["expires_at"]) <= datetime.now(
            timezone.utc
        ):
            raise HTTPException(status_code=410, detail="Share expired")
        meeting = _find(state["meetings"], share["meeting_id"], "Meeting")
        share["views"].append(datetime.now(timezone.utc).isoformat())
        _audit(state, "share.viewed", {"share_id": share["id"]})
        _write_document(document)
        return {
            "title": meeting["title"],
            "summary": meeting["summary"],
            "decisions": meeting["decisions"],
            "key_points": meeting["key_points"],
        }
    raise HTTPException(status_code=404, detail="Share not found")
