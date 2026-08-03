"""SQLAlchemy ORM models for MeetingNotesAI v0.2.0.

Models: User, Team, TeamMember, Meeting, SharedLink, BatchJob,
BatchFileResult, WebhookSubscription, BAATemplate, BAAgreement
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ── Enums ──────────────────────────────────────────────────────────────────────


class BatchStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TeamRole(str, PyEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class WebhookEvent(str, PyEnum):
    BATCH_COMPLETED = "batch.completed"
    BATCH_FAILED = "batch.failed"


class StorageFileKind(str, PyEnum):
    """Kind of a stored object (analysis brief §6.2)."""

    AUDIO = "audio"
    TRANSCRIPT = "transcript"


class StorageEncryption(str, PyEnum):
    """Encryption mode of a stored object (analysis brief §6.2)."""

    NONE = "none"
    AES256GCM = "aes256gcm"


# ── Mixins ─────────────────────────────────────────────────────────────────────


class TimestampMixin:
    """Add created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


# ── User ───────────────────────────────────────────────────────────────────────


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)

    # Relationships
    team_memberships: Mapped[list["TeamMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="user")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ── API keys ───────────────────────────────────────────────────────────────────


class ApiKey(Base, TimestampMixin):
    """Hashed, revocable API credential. The plaintext key is never stored."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    hashed_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")


# ── Team ───────────────────────────────────────────────────────────────────────


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    retention_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # NULL → DEFAULT_RETENTION_DAYS (inherit)

    # Relationships
    owner: Mapped["User"] = relationship()
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="team")
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    stored_files: Mapped[list["StoredFile"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


# ── TeamMember ──────────────────────────────────────────────────────────────────


class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole), default=TeamRole.MEMBER, nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="team_memberships")


# ── Meeting ─────────────────────────────────────────────────────────────────────


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(300), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    team_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(50), default="general")
    transcript: Mapped[str] = mapped_column(Text, nullable=True)
    action_items: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    decisions: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    key_points: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)  # JSON

    # Relationships
    user: Mapped["User"] = relationship(back_populates="meetings")
    team: Mapped[Optional["Team"]] = relationship(back_populates="meetings")
    shared_links: Mapped[list["SharedLink"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


# ── SharedLink ──────────────────────────────────────────────────────────────────


class SharedLink(Base, TimestampMixin):
    __tablename__ = "shared_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(String(36), ForeignKey("meetings.id"), nullable=False)
    team_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="shared_links")
    creator: Mapped["User"] = relationship()


# ── BatchJob ────────────────────────────────────────────────────────────────────


class BatchJob(Base, TimestampMixin):
    __tablename__ = "batch_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    team_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True
    )
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), default=BatchStatus.PENDING, nullable=False
    )
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    completed_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    file_results: Mapped[list["BatchFileResult"]] = relationship(
        back_populates="batch_job", cascade="all, delete-orphan"
    )


# ── BatchFileResult ─────────────────────────────────────────────────────────────


class BatchFileResult(Base, TimestampMixin):
    __tablename__ = "batch_file_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("batch_jobs.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), default=BatchStatus.PENDING, nullable=False
    )
    meeting_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("meetings.id"), nullable=True
    )
    transcript_summary: Mapped[str] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    batch_job: Mapped["BatchJob"] = relationship(back_populates="file_results")


# ── WebhookSubscription ─────────────────────────────────────────────────────────


class WebhookSubscription(Base, TimestampMixin):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=True)
    events: Mapped[str] = mapped_column(Text, nullable=False, default="batch.completed")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="webhook_subscriptions")


# ── StoredFile (secure file storage, v0.7.0) ───────────────────────────────────


class StoredFile(Base, TimestampMixin):
    """A durable audio/transcript object stored on the storage backend.

    Metadata lives in the DB (checksum, size, content type, retention);
    the bytes live on the object backend under ``object_key``. Rows are
    soft-deleted (``deleted_at``) so the HIPAA audit trail can always
    point at what was stored, even after the object is gone.
    """

    __tablename__ = "storage_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id"), nullable=False, index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True, index=True
    )
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[StorageFileKind] = mapped_column(
        Enum(StorageFileKind), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    bucket: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    encryption: Mapped[StorageEncryption] = mapped_column(
        Enum(StorageEncryption), default=StorageEncryption.NONE, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship()
    team: Mapped[Optional["Team"]] = relationship(back_populates="stored_files")
    uploader: Mapped["User"] = relationship()


# ── LiveSessionRecord (streaming STT, v0.7.0) ─────────────────────────────────


class LiveSessionRecord(Base, TimestampMixin):
    """Durable state of a live transcription session.

    The Pydantic ``LiveSession`` (``meeting_notes_ai.live_session``) is the
    wire/domain shape; this row is its persistent storage so a session
    survives client disconnects and can be resumed. ``chunks`` and
    ``partials`` are stored as JSON (see the live transcription service),
    carrying the HIPAA retention fields (``retention_days``, ``hipaa``,
    ``phi_classification``) through the v0.7.0 storage integration.
    """

    __tablename__ = "live_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True
    )
    room_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="live", nullable=False)
    chunks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    partials_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    retention_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hipaa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phi_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
