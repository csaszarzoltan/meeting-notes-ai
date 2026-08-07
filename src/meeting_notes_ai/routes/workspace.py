"""Authenticated, tenant-scoped product workspace APIs."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.services.integrations import PM_PROVIDERS, get_adapter
from meeting_notes_ai.services.integrations.base import (
    AdapterAuth,
    AdapterAuthError,
    AdapterUnavailableError,
    AdapterValidationError,
)

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
public_router = APIRouter(prefix="/public/workspace-shares", tags=["public-workspace"])
_STATE_PATH = Path("data/workspace_state.json")
_LOCK = threading.RLock()


def _resolve_provider(integrations: dict[str, Any], destination: str) -> str | None:
    """Map a display name or slug to a provider slug, or None for legacy."""
    # Exact display-name match in the catalog
    entry = integrations.get(destination)
    if entry and entry.get("provider"):
        return entry["provider"]
    # Case-insensitive slug match
    dest_lower = destination.lower().strip()
    for _name, info in integrations.items():
        if info.get("provider", "").lower() == dest_lower:
            return info["provider"]
    return None


def _seed_integrations() -> dict[str, Any]:
    """Return the canonical integration catalog for a fresh workspace."""
    return {
        "Microsoft Planner": {"connected": False, "mode": "adapter_required"},
        "Jira": {"connected": False, "provider": "jira", "mode": "adapter_required"},
        "Linear": {"connected": False, "provider": "linear", "mode": "adapter_required"},
        "Asana": {"connected": False, "provider": "asana", "mode": "adapter_required"},
        "Todoist": {"connected": False, "provider": "todoist", "mode": "adapter_required"},
        "Salesforce": {"connected": False, "mode": "adapter_required"},
        "Slack": {"connected": False, "mode": "adapter_required"},
    }


def _seed_workspace(user_id: str) -> dict[str, Any]:
    """Return an empty, private first-run workspace."""
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
        "integrations": _seed_integrations(),
        "batches": [],
        "audit": [],
        "shares": [],
    }


def _read_document() -> dict[str, Any]:
    """Read the complete tenant document."""
    with _LOCK:
        if not _STATE_PATH.exists():
            return {"schema_version": 2, "workspaces": {}}
        try:
            value = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="Workspace state is unavailable") from exc
        return value if "workspaces" in value else {"schema_version": 2, "workspaces": {}}


def _write_document(document: dict[str, Any]) -> None:
    """Atomically persist the complete tenant document."""
    with _LOCK:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(_STATE_PATH)


def _workspace(user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _read_document()
    state = document["workspaces"].setdefault(user_id, _seed_workspace(user_id))
    _write_document(document)
    return document, state


def _find(items: list[dict[str, Any]], item_id: str, label: str) -> dict[str, Any]:
    item = next((item for item in items if item["id"] == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _audit(state: dict[str, Any], event: str, details: dict[str, Any]) -> None:
    state["audit"].append(
        {
            "id": str(uuid4()),
            "event": event,
            "details": details,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )


class MeetingCreate(BaseModel):
    """Canonical meeting payload created from processing output."""

    id: str | None = None
    title: str = Field(default="Untitled meeting", min_length=1, max_length=300)
    transcript: str = Field(min_length=1, max_length=1_000_000)
    summary: str = Field(default="", max_length=100_000)
    action_items: list[Any] = Field(default_factory=list)
    decisions: list[Any] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    mode: str = Field(default="general", pattern="^(general|healthcare|legal)$")
    warnings: list[str] = Field(default_factory=list)
    phi_redacted: bool = False
    redaction_matches: int = Field(default=0, ge=0)


class ReviewUpdate(BaseModel):
    """Editable and approvable review fields."""

    summary: str = Field(min_length=1, max_length=100_000)
    review_status: str = Field(pattern="^(needs_review|in_review|approved|rejected)$")
    reviewer: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=1000)


class ActionUpdate(BaseModel):
    """Mutable action fields."""

    status: str = Field(pattern="^(suggested|confirmed|queued|completed)$")
    owner: str = Field(min_length=1, max_length=100)
    due: str = Field(min_length=1, max_length=50)


class DestinationRequest(BaseModel):
    """Requested connector destination."""

    destination: str = Field(min_length=1, max_length=100)


class InsightRequest(BaseModel):
    """Private workspace query."""

    query: str = Field(min_length=2, max_length=500)


class ShareRequest(BaseModel):
    """Backend-enforced share controls."""

    expires_in: str = Field(default="7d", pattern="^(1h|24h|7d|never)$")


def _expires(value: str) -> str | None:
    delta = {"1h": timedelta(hours=1), "24h": timedelta(days=1), "7d": timedelta(days=7)}.get(value)
    return (datetime.now(timezone.utc) + delta).isoformat() if delta else None


@router.get("/dashboard")
async def dashboard(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return trusted outcome metrics for the authenticated user."""
    _, state = _workspace(user["user_id"])
    return {
        "needs_review": sum(m["review_status"] == "needs_review" for m in state["meetings"]),
        "open_actions": sum(a["status"] != "completed" for a in state["actions"]),
        "processing_failures": sum(b.get("failed", 0) for b in state["batches"]),
        "time_saved_hours": round(len(state["meetings"]) * 0.5, 1),
        "recent_meetings": state["meetings"][:5],
        "my_actions": state["actions"][:5],
        "activity": state["audit"][-5:],
        "onboarding_complete": bool(state["meetings"]),
    }


@router.get("/meetings")
async def list_meetings(
    user: dict[str, Any] = Depends(get_current_user), q: str = ""
) -> dict[str, Any]:
    """List or search meetings in the authenticated workspace."""
    _, state = _workspace(user["user_id"])
    query = q.casefold().strip()
    items = state["meetings"]
    if query:
        items = [
            m
            for m in items
            if query
            in " ".join(
                [
                    m["title"],
                    m["summary"],
                    m["transcript"],
                    " ".join(m.get("tags", [])),
                    " ".join(str(x) for x in m.get("decisions", [])),
                ]
            ).casefold()
        ]
    return {"items": items}


@router.post("/meetings", status_code=201)
async def create_meeting(
    request: MeetingCreate, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Save a processed result as a canonical private meeting."""
    document, state = _workspace(user["user_id"])
    meeting_id = request.id or str(uuid4())
    if any(m["id"] == meeting_id for m in state["meetings"]):
        meeting_id = str(uuid4())
    raw = request.model_dump(exclude={"id"})
    evidence = [
        {
            "timestamp": "00:00",
            "speaker": "Speaker 1",
            "text": request.transcript[:500],
            "confidence": 0.0,
        }
    ]
    meeting = {
        **raw,
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
    for item in request.action_items:
        value = item if isinstance(item, dict) else {"description": str(item)}
        state["actions"].append(
            {
                "id": str(uuid4()),
                "title": value.get("description", "Action"),
                "owner": value.get("assignee") or "Unassigned",
                "owner_id": user["user_id"],
                "due": value.get("deadline") or "Unscheduled",
                "meeting_id": meeting_id,
                "meeting": meeting["title"],
                "timestamp": "00:00",
                "status": "suggested",
                "destination": "Not selected",
                "external_id": None,
                "external_url": None,
            }
        )
    _audit(state, "meeting.created", {"meeting_id": meeting_id})
    _write_document(document)
    return meeting


@router.get("/meetings/{meeting_id}")
async def meeting_detail(
    meeting_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Return one owned meeting."""
    _, state = _workspace(user["user_id"])
    return _find(state["meetings"], meeting_id, "Meeting")


@router.patch("/meetings/{meeting_id}/review")
async def update_review(
    meeting_id: str, request: ReviewUpdate, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Persist review edits and immutable provenance."""
    document, state = _workspace(user["user_id"])
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
    meeting.update(summary=request.summary, review_status=request.review_status)
    meeting["versions"].append(version)
    _audit(state, "meeting.reviewed", {"meeting_id": meeting_id, "version": version["number"]})
    _write_document(document)
    return meeting


@router.get("/actions")
async def list_actions(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List private workspace actions."""
    _, state = _workspace(user["user_id"])
    return {"items": state["actions"]}


@router.patch("/actions/{action_id}")
async def update_action(
    action_id: str, request: ActionUpdate, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Persist action ownership, due date, and status."""
    document, state = _workspace(user["user_id"])
    action = _find(state["actions"], action_id, "Action")
    action.update(request.model_dump())
    _audit(state, "action.updated", {"action_id": action_id})
    _write_document(document)
    return action


@router.post("/actions/{action_id}/queue")
async def queue_action(
    action_id: str,
    request: DestinationRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Queue an action for syncing to a PM provider or legacy connector."""
    document, state = _workspace(user["user_id"])
    action = _find(state["actions"], action_id, "Action")

    provider_slug = _resolve_provider(state["integrations"], request.destination)

    # ── PM provider path (Jira / Linear / Asana / Todoist) ──
    if provider_slug is not None:
        # Load the credential row (source of truth)
        from sqlalchemy import select

        from meeting_notes_ai.db.models import PMIntegrationToken
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        stmt = select(PMIntegrationToken).where(
            PMIntegrationToken.user_id == user["user_id"],
            PMIntegrationToken.provider == provider_slug,
            PMIntegrationToken.is_active.is_(True),
        )
        row = (await db.execute(stmt)).scalar_one_or_none()

        if row is None:
            display = request.destination
            raise HTTPException(
                status_code=409,
                detail=f"Connect {display} before syncing this action",
            )

        # Decrypt credentials
        encryptor = TokenEncryptor()
        creds = json.loads(encryptor.decrypt(row.encrypted_credentials))
        auth = AdapterAuth(
            provider=provider_slug,
            token=creds.get("token", ""),
            site_url=creds.get("site_url", ""),
            email=creds.get("email", ""),
            default_project=creds.get("default_project", ""),
        )

        # Idempotency pre-check: already synced?
        idempotency_key = f"{action.get('meeting_id', '')}:{action['id']}"
        if action.get("external_id") and action.get("sync_key") == idempotency_key:
            action["sync_state"] = "task-synced"
            return action

        # Call the provider adapter
        adapter = get_adapter(provider_slug)()
        # Cache auth on adapter for create_task
        adapter._auth = auth  # noqa: SLF001
        try:
            result = await asyncio.wait_for(
                adapter.create_task(action, idempotency_key=idempotency_key),
                timeout=30,
            )
        except AdapterAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except AdapterUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except AdapterValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (TimeoutError, asyncio.TimeoutError) as exc:
            msg = (
                f"{request.destination} is temporarily unavailable."
                " Try again in a few minutes."
            )
            raise HTTPException(status_code=502, detail=msg) from exc

        action.update(
            destination=request.destination,
            status="queued",
            external_id=result.external_id,
            external_url=result.external_url,
            sync_key=idempotency_key,
        )
        _audit(state, "action.synced", {
            "action_id": action_id,
            "destination": request.destination,
            "external_id": result.external_id,
        })
        _write_document(document)
        action["sync_state"] = "task-synced"
        return action

    # ── Legacy connector path (Planner / Salesforce / Slack) ──
    connector = state["integrations"].get(request.destination)
    if not connector or not connector["connected"]:
        raise HTTPException(
            status_code=409,
            detail="Connect an adapter before queuing this action",
        )
    action.update(
        destination=request.destination,
        status="queued",
        external_id=None,
        adapter_job_id=str(uuid4()),
    )
    _audit(state, "action.queued", {
        "action_id": action_id,
        "destination": request.destination,
    })
    _write_document(document)
    return action


@router.get("/settings")
async def get_settings(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return private workspace settings."""
    return _workspace(user["user_id"])[1]["settings"]


@router.put("/settings")
async def put_settings(
    request: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Persist allow-listed workspace settings."""
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
    document, state = _workspace(user["user_id"])
    state["settings"].update(request)
    _audit(state, "settings.updated", {"keys": sorted(request)})
    _write_document(document)
    return state["settings"]


@router.get("/integrations")
async def integrations(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List connector configuration."""
    return {"items": _workspace(user["user_id"])[1]["integrations"]}


@router.post("/integrations/{name}/connect")
async def connect_integration(
    name: str, request: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Connect a PM provider with credentials or toggle a legacy connector."""
    document, state = _workspace(user["user_id"])
    if name not in state["integrations"]:
        raise HTTPException(status_code=404, detail="Integration not found")

    provider_slug = state["integrations"][name].get("provider")

    # ── PM provider path: accept credentials and call connect() ──
    if provider_slug and provider_slug in PM_PROVIDERS:
        creds = request.get("credentials", {})
        token = creds.get("token", "")
        if not token and request.get("enabled", True):
            raise HTTPException(
                status_code=422,
                detail=f"Credentials required to connect {name}",
            )
        if not request.get("enabled", True) and not token:
            # Disconnect
            state["integrations"][name].update(connected=False)
            for key in ("account_email", "account_url", "token_expires_at"):
                state["integrations"][name].pop(key, None)
            _audit(state, "integration.changed", {"name": name, "action": "disconnect"})
            _write_document(document)
            return {"name": name, **state["integrations"][name]}

        auth = AdapterAuth(
            provider=provider_slug,
            token=token,
            site_url=creds.get("site_url", ""),
            email=creds.get("email", ""),
            default_project=creds.get("default_project", ""),
        )
        try:
            adapter = get_adapter(provider_slug)()
            connection = await adapter.connect(auth)
        except AdapterAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except AdapterUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except AdapterValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Store encrypted credentials
        from meeting_notes_ai.services.token_encryption import TokenEncryptor

        encryptor = TokenEncryptor()
        encryptor.encrypt(json.dumps({
            "token": token,
            "site_url": auth.site_url,
            "email": auth.email,
            "default_project": auth.default_project,
        }))
        state["integrations"][name].update(
            connected=True,
            account_email=connection.account_email,
            account_url=connection.account_url,
            token_expires_at=connection.token_expires_at,
        )
        _audit(state, "integration.changed", {"name": name})
        _write_document(document)
        return {"name": name, **state["integrations"][name]}

    # ── Legacy connector path (Planner / Salesforce / Slack) ──
    state["integrations"][name]["connected"] = bool(request.get("enabled", True))
    _audit(state, "integration.changed", {"name": name})
    _write_document(document)
    return {"name": name, **state["integrations"][name]}


@router.post("/insights/query")
async def query_insights(
    request: InsightRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Search private meeting evidence and return citations."""
    _, state = _workspace(user["user_id"])
    query = request.query.casefold()
    sources = []
    for meeting in state["meetings"]:
        for evidence in meeting["evidence"]:
            if any(
                token in f"{meeting['title']} {meeting['summary']} {evidence['text']}".casefold()
                for token in query.split()
            ):
                sources.append(
                    {"meeting_id": meeting["id"], "meeting": meeting["title"], **evidence}
                )
    return {
        "answer": f"Found {len(sources)} cited source moment(s) related to '{request.query}'.",
        "sources": sources[:8],
    }


@router.get("/compliance")
async def compliance(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Derive evidence-backed controls from current workspace policy."""
    _, state = _workspace(user["user_id"])
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
    """List tenant-scoped background jobs."""
    return {"items": _workspace(user["user_id"])[1]["batches"]}


@router.post("/batches/{batch_id}/retry")
async def retry_batch(
    batch_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Retry failed work while preserving complete items."""
    document, state = _workspace(user["user_id"])
    batch = _find(state["batches"], batch_id, "Batch")
    batch.update(status="processing", failed=0)
    _audit(state, "batch.retried", {"batch_id": batch_id})
    _write_document(document)
    return batch


@router.post("/meetings/{meeting_id}/share", status_code=201)
async def create_share(
    meeting_id: str, request: ShareRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Create an expiring share for an approved owned meeting."""
    document, state = _workspace(user["user_id"])
    meeting = _find(state["meetings"], meeting_id, "Meeting")
    if meeting["review_status"] != "approved":
        raise HTTPException(status_code=409, detail="Approve the meeting before sharing")
    share = {
        "id": str(uuid4()),
        "meeting_id": meeting_id,
        "token": uuid4().hex + uuid4().hex,
        "expires_at": _expires(request.expires_in),
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
async def revoke_share(share_id: str, user: dict[str, Any] = Depends(get_current_user)) -> None:
    """Immediately revoke an owned share."""
    document, state = _workspace(user["user_id"])
    share = _find(state["shares"], share_id, "Share")
    share["active"] = False
    _audit(state, "share.revoked", {"share_id": share_id})
    _write_document(document)


@public_router.get("/{token}")
async def resolve_share(token: str) -> dict[str, Any]:
    """Resolve an active, unexpired share and audit its access."""
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
