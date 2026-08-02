"""Secure file storage REST endpoints — MeetingNotesAI v0.7.0.

Endpoints (analysis brief §7):
    POST   /api/v1/meetings/{meeting_id}/audio       — upload audio (201)
    GET    /api/v1/meetings/{meeting_id}/audio       — download audio
    DELETE /api/v1/meetings/{meeting_id}/audio       — delete audio (204)
    GET    /api/v1/meetings/{meeting_id}/transcript  — transcript as .txt
    PUT    /api/v1/teams/{team_id}/retention         — set retention policy
    GET    /api/v1/teams/{team_id}/retention         — read retention policy
    POST   /api/v1/admin/retention/sweep             — manual sweep (admin token)

Every data endpoint requires ``get_current_user``; meeting access uses the
``_verify_meeting_access`` RBAC pattern from routes/sharing.py (owner or
team member; viewers are read-only). All operations write HIPAA audit
entries (``storage.upload`` / ``storage.download`` / ``storage.delete`` /
``storage.decrypt_failed`` / ``retention.policy.update``).

Note: the legacy unauthenticated ``POST /api/v1/meetings`` and
``POST /api/v1/transcribe`` flows are deliberately untouched — this router
is fully auth'd and does not inherit their auth gap (brief §15).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.auth import get_current_user, require_team_role
from meeting_notes_ai.config import settings
from meeting_notes_ai.db.models import (
    Meeting,
    StorageEncryption,
    StorageFileKind,
    StoredFile,
)
from meeting_notes_ai.db.session import get_db_session
from meeting_notes_ai.hipaa.audit_logger import AuditEntry
from meeting_notes_ai.hipaa.middleware import get_audit_logger
from meeting_notes_ai.routes.admin import require_admin
from meeting_notes_ai.routes.sharing import _verify_meeting_access
from meeting_notes_ai.storage.encryption import FileEncryptor
from meeting_notes_ai.storage.factory import get_storage_backend
from meeting_notes_ai.storage.retention import (
    DEFAULT_RETENTION_DAYS,
    ALLOWED_RETENTION_DAYS,
    RetentionPolicy,
    sweep_expired,
)

router = APIRouter(tags=["storage"])

_CHUNK_SIZE = 1024 * 1024  # 1 MiB streaming chunks


# ── Request/Response Schemas ───────────────────────────────────────────────────


class StoredFileResponse(BaseModel):
    """Metadata for a stored object (brief §7)."""

    id: str
    meeting_id: str
    kind: str
    object_key: str | None = None
    size_bytes: int
    sha256: str
    content_type: str
    encryption: str
    expires_at: datetime | None = None
    created_at: datetime | None = None


class RetentionUpdateRequest(BaseModel):
    """Body for PUT /api/v1/teams/{team_id}/retention.

    ``retention_days`` must be one of 365 (1y), 1095 (3y), 2555 (7y) or
    None (inherit the 6-year default).
    """

    retention_days: int | None = None

    @field_validator("retention_days")
    @classmethod
    def _validate_retention_days(cls, v: int | None) -> int | None:
        if v is not None and v not in ALLOWED_RETENTION_DAYS:
            raise ValueError(
                "retention_days must be one of "
                f"{sorted(ALLOWED_RETENTION_DAYS)} (1y/3y/7y) or null to inherit"
            )
        return v


class RetentionResponse(BaseModel):
    """Current retention policy for a team."""

    retention_days: int | None
    effective_days: int
    expires_at_example: str


# ── Dependencies ───────────────────────────────────────────────────────────────


async def get_storage_backend_dep() -> Any:
    """FastAPI dependency returning the configured storage backend.

    Resolved per request so tests can swap ``settings.storage_local_dir``
    without restarting the app; backend construction is cheap for local
    and lazy (no network) for S3.
    """
    return get_storage_backend()


def _client_ip(request: Request) -> str:
    """Best-effort client IP for HIPAA audit trails."""
    if request.client is not None and request.client.host:
        return request.client.host
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else ""


def _client_user_agent(request: Request) -> str:
    """Best-effort client User-Agent for HIPAA audit trails (truncated)."""
    return (request.headers.get("user-agent") or "")[:512]


def _phi_classification(meeting: Meeting) -> str:
    """Classify stored payloads from healthcare meetings as PHI."""
    return "phi" if meeting.mode == "healthcare" else "none"


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _find_latest_file(
    db: AsyncSession,
    meeting_id: str,
    kind: StorageFileKind,
) -> StoredFile | None:
    """Return the newest non-soft-deleted stored file of *kind* for a meeting."""
    result = await db.execute(
        select(StoredFile)
        .where(
            StoredFile.meeting_id == meeting_id,
            StoredFile.kind == kind,
            StoredFile.deleted_at.is_(None),
        )
        .order_by(StoredFile.created_at.desc())
    )
    return result.scalars().first()


async def _stream_upload(file: UploadFile) -> bytes:
    """Read the upload in chunks, enforcing the size cap while hashing.

    Streams per file (never whole batch in memory) and raises
    :class:`HTTPException` 413 as soon as the cap is exceeded.
    """
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    chunks = bytearray()
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "file_too_large",
                    "message": f"The file exceeds the {settings.max_audio_size_mb} MB limit.",
                    "max_size_mb": settings.max_audio_size_mb,
                },
            )
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_file", "message": "The uploaded file is empty."},
        )
    return bytes(chunks)


def _audit_actor(user: dict[str, Any]) -> str:
    return str(user["user_id"])


def _stored_to_response(row: StoredFile) -> StoredFileResponse:
    return StoredFileResponse(
        id=row.id,
        meeting_id=row.meeting_id,
        kind=row.kind.value if hasattr(row.kind, "value") else str(row.kind),
        object_key=row.object_key,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        content_type=row.content_type,
        encryption=row.encryption.value if hasattr(row.encryption, "value") else str(row.encryption),
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


# ── Upload / Download / Delete ─────────────────────────────────────────────────


@router.post(
    "/api/v1/meetings/{meeting_id}/audio",
    response_model=StoredFileResponse,
    status_code=201,
)
async def upload_audio(
    meeting_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
    storage: Any = Depends(get_storage_backend_dep),
) -> StoredFileResponse:
    """Store an audio file for a meeting (owner or team member; viewers blocked)."""
    meeting = await _verify_meeting_access(meeting_id, user, db, require_write=True)

    existing = await _find_latest_file(db, meeting_id, StorageFileKind.AUDIO)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "file_already_stored",
                "message": "Audio is already stored for this meeting.",
            },
        )

    if file.content_type not in settings.SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "unsupported_audio_format",
                "message": "Use WAV, MP3, MP4, or WebM audio.",
                "received": file.content_type,
                "supported": sorted(settings.SUPPORTED_AUDIO_FORMATS),
            },
        )

    payload = await _stream_upload(file)
    sha256 = hashlib.sha256(payload).hexdigest()

    encryptor = FileEncryptor()
    if encryptor.enabled:
        blob = encryptor.encrypt(payload)
        encryption = StorageEncryption.AES256GCM
    else:
        blob = payload
        encryption = StorageEncryption.NONE

    file_id = str(uuid4())
    object_key = f"audio/{meeting_id}/{file_id}"
    bucket = settings.storage_backend or "local"

    retention_days = await _load_team_retention(db, meeting)
    expires_at = RetentionPolicy(retention_days=retention_days).compute_expires_at(
        datetime.now(timezone.utc)
    )

    try:
        await storage.put(object_key, blob, file.content_type)
    except Exception as exc:  # storage backend failure → 502
        raise HTTPException(
            status_code=502,
            detail={
                "code": "storage_backend_error",
                "message": "The file could not be stored. Try again later.",
            },
        ) from exc

    row = StoredFile(
        id=file_id,
        meeting_id=meeting_id,
        team_id=meeting.team_id,
        uploaded_by=_audit_actor(user),
        kind=StorageFileKind.AUDIO,
        object_key=object_key,
        bucket=bucket,
        size_bytes=len(blob),
        sha256=sha256,
        content_type=file.content_type,
        encryption=encryption,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()

    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=_audit_actor(user),
            action="storage.upload",
            resource=object_key,
            phi_classification=_phi_classification(meeting),
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={
                "meeting_id": meeting_id,
                "kind": "audio",
                "size_bytes": len(payload),
                "sha256": sha256,
                "encryption": encryption.value,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
    )
    return _stored_to_response(row)


@router.get("/api/v1/meetings/{meeting_id}/audio")
async def download_audio(
    meeting_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
    storage: Any = Depends(get_storage_backend_dep),
) -> Response:
    """Download the stored audio for a meeting (owner or any team member)."""
    meeting = await _verify_meeting_access(meeting_id, user, db)
    row = await _find_latest_file(db, meeting_id, StorageFileKind.AUDIO)
    if row is None:
        raise HTTPException(status_code=404, detail="No stored audio for this meeting")

    data = await _fetch_and_decrypt(row, meeting, storage, audit, request)
    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=_audit_actor(user),
            action="storage.download",
            resource=row.object_key,
            phi_classification=_phi_classification(meeting),
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={"meeting_id": meeting_id, "kind": "audio"},
        )
    )
    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="audio-{meeting_id}.wav"'
        },
    )


@router.delete("/api/v1/meetings/{meeting_id}/audio", status_code=204)
async def delete_audio(
    meeting_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
    storage: Any = Depends(get_storage_backend_dep),
) -> None:
    """Soft-delete the stored audio (owner or team member with write access)."""
    meeting = await _verify_meeting_access(meeting_id, user, db, require_write=True)
    row = await _find_latest_file(db, meeting_id, StorageFileKind.AUDIO)
    if row is None:
        raise HTTPException(status_code=404, detail="No stored audio for this meeting")

    try:
        await storage.delete(row.object_key)
    except Exception as exc:  # storage backend failure → 502
        raise HTTPException(
            status_code=502,
            detail={
                "code": "storage_backend_error",
                "message": "The file could not be deleted. Try again later.",
            },
        ) from exc

    row.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=_audit_actor(user),
            action="storage.delete",
            resource=row.object_key,
            phi_classification=_phi_classification(meeting),
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={"meeting_id": meeting_id, "kind": "audio"},
        )
    )
    return None


@router.get("/api/v1/meetings/{meeting_id}/transcript")
async def download_transcript(
    meeting_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
    storage: Any = Depends(get_storage_backend_dep),
) -> Response:
    """Download a meeting's transcript as a .txt attachment.

    Serves the stored transcript object when one exists (kind=transcript),
    otherwise falls back to ``Meeting.transcript`` (brief §7).
    """
    meeting = await _verify_meeting_access(meeting_id, user, db)

    row = await _find_latest_file(db, meeting_id, StorageFileKind.TRANSCRIPT)
    if row is not None:
        data = await _fetch_and_decrypt(row, meeting, storage, audit, request)
        media_type = "text/plain; charset=utf-8"
    else:
        data = (meeting.transcript or "").encode("utf-8")
        media_type = "text/plain; charset=utf-8"

    await audit.log(
        AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=_audit_actor(user),
            action="storage.download",
            resource=row.object_key if row is not None else f"meeting/{meeting_id}/transcript",
            phi_classification=_phi_classification(meeting),
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={"meeting_id": meeting_id, "kind": "transcript"},
        )
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="transcript-{meeting_id}.txt"'
        },
    )


async def _fetch_and_decrypt(
    row: StoredFile,
    meeting: Meeting,
    storage: Any,
    audit: Any,
    request: Request,
) -> bytes:
    """Fetch *row*'s object and decrypt it, verifying the plaintext hash.

    Raises:
        HTTPException 502 with ``code: storage_decrypt_failed`` on any
        decrypt failure (tamper / wrong key) — raw ciphertext is never
        returned (brief §8).
    """
    try:
        blob = await storage.get(row.object_key)
    except Exception as exc:  # missing object or backend failure
        raise HTTPException(
            status_code=502,
            detail={
                "code": "storage_backend_error",
                "message": "The stored file could not be retrieved.",
            },
        ) from exc

    if row.encryption == StorageEncryption.AES256GCM:
        try:
            plaintext = FileEncryptor(mode="aes256gcm").decrypt(blob)
        except Exception:
            await audit.log(
                AuditEntry(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    actor=_audit_actor({"user_id": "system"}),
                    action="storage.decrypt_failed",
                    resource=row.object_key,
                    phi_classification=_phi_classification(meeting),
                    outcome="failure",
                    ip_address=_client_ip(request),
                    user_agent=_client_user_agent(request),
                    details={"meeting_id": row.meeting_id, "kind": "audio"},
                )
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "storage_decrypt_failed",
                    "message": "The stored file could not be decrypted (tampered or wrong key).",
                },
            ) from None
        if hashlib.sha256(plaintext).hexdigest() != row.sha256:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "storage_decrypt_failed",
                    "message": "The stored file failed its integrity check.",
                },
            )
        return plaintext
    return blob


# ── Retention policy ───────────────────────────────────────────────────────────


async def _load_team_retention(db: AsyncSession, meeting: Meeting) -> int | None:
    """Load the team's retention_days override for *meeting* (None = inherit)."""
    if meeting.team_id is None:
        return None
    from meeting_notes_ai.db.models import Team

    team_result = await db.execute(select(Team).where(Team.id == meeting.team_id))
    team = team_result.scalar_one_or_none()
    return team.retention_days if team is not None else None


async def _recompute_team_expirations(
    db: AsyncSession, team_id: str, retention_days: int | None
) -> int:
    """Recompute ``expires_at`` for every live stored file of the team.

    Returns the number of rows updated. Called after a retention policy
    change so existing files inherit the new deadline immediately.
    """
    policy = RetentionPolicy(retention_days=retention_days)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(StoredFile)
        .join(Meeting, Meeting.id == StoredFile.meeting_id)
        .where(Meeting.team_id == team_id, StoredFile.deleted_at.is_(None))
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.expires_at = policy.compute_expires_at(now)
    if rows:
        await db.flush()
    return len(rows)


@router.put("/api/v1/teams/{team_id}/retention", response_model=RetentionResponse)
async def update_team_retention(
    team_id: str,
    body: RetentionUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
) -> RetentionResponse:
    """Set a team's retention policy (team admin only)."""
    await require_team_role(team_id, "admin", user, db)

    from meeting_notes_ai.db.models import Team

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    previous = team.retention_days
    team.retention_days = body.retention_days
    await db.flush()

    updated = await _recompute_team_expirations(db, team_id, body.retention_days)

    policy = RetentionPolicy(retention_days=body.retention_days)
    now = datetime.now(timezone.utc)
    await audit.log(
        AuditEntry(
            timestamp=now.isoformat(),
            actor=_audit_actor(user),
            action="retention.policy.update",
            resource=team_id,
            phi_classification="none",
            outcome="success",
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            details={
                "previous_days": previous,
                "retention_days": body.retention_days,
                "effective_days": policy.effective_days(),
                "files_recomputed": updated,
            },
        )
    )
    return RetentionResponse(
        retention_days=body.retention_days,
        effective_days=policy.effective_days(),
        expires_at_example=policy.compute_expires_at(now).isoformat(),
    )


@router.get("/api/v1/teams/{team_id}/retention", response_model=RetentionResponse)
async def get_team_retention(
    team_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RetentionResponse:
    """Read a team's retention policy (any team member)."""
    await require_team_role(team_id, "viewer", user, db)

    from meeting_notes_ai.db.models import Team

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    policy = RetentionPolicy(retention_days=team.retention_days)
    return RetentionResponse(
        retention_days=team.retention_days,
        effective_days=policy.effective_days(),
        expires_at_example=policy.compute_expires_at(
            datetime.now(timezone.utc)
        ).isoformat(),
    )


@router.post("/api/v1/admin/retention/sweep")
async def admin_retention_sweep(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    audit: Any = Depends(get_audit_logger),
    storage: Any = Depends(get_storage_backend_dep),
) -> dict[str, int]:
    """Run a retention sweep immediately (admin API token gate)."""
    result = await sweep_expired(db=db, storage=storage, audit=audit)
    await db.flush()
    return result.as_dict()
