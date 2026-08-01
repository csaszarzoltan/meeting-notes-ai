"""Pydantic models for MeetingNotesAI."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# ── Shared Enums ──────────────────────────────────────────────────────────────


class MeetingMode(str, Enum):
    GENERAL = "general"
    HEALTHCARE = "healthcare"
    LEGAL = "legal"


# ── Action Item ───────────────────────────────────────────────────────────────


class ActionItem(BaseModel):
    assignee: str | None = None
    description: str = ""
    deadline: str | None = None


# ── Meeting Request / Response ────────────────────────────────────────────────


class MeetingRequest(BaseModel):
    mode: MeetingMode = MeetingMode.GENERAL


class MeetingResponse(BaseModel):
    id: str = ""
    transcript: str = ""
    summary: str = ""
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    mode: MeetingMode = MeetingMode.GENERAL
    review_status: Literal["ready", "needs_review"] = "ready"
    phi_redacted: bool = False
    redaction_matches: int = 0
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# ── Health ────────────────────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    status: Literal["up", "down", "unknown"] = "unknown"
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    version: str = "0.1.0"
    services: dict[str, ServiceHealth] = {}


# ── Transcription ─────────────────────────────────────────────────────────────


class TranscriptionResult(BaseModel):
    text: str = ""
    language: str = ""
    duration_seconds: float = 0.0
    segments: list[TranscriptSegment] = []


class TranscriptSegment(BaseModel):
    start: float = 0.0
    end: float = 0.0
    text: str = ""


# ── Extraction ────────────────────────────────────────────────────────────────


class ExtractionResult(BaseModel):
    action_items: list[ActionItem] = []
    decisions: list[str] = []
    key_points: list[str] = []
    summary: str = ""
    raw_llm_response: str = ""


# ── Healthcare ────────────────────────────────────────────────────────────────


class SOAPNote(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class HIPAAMarker(BaseModel):
    field: str = ""
    risk_level: Literal["high", "medium", "low"] = "low"
    recommendation: str = ""


class ConsentStatus(BaseModel):
    confirmed: bool = False
    timestamp: str | None = None
    note: str | None = None


class HealthcareNote(BaseModel):
    soap: SOAPNote = SOAPNote()
    hipaa_markers: list[HIPAAMarker] = []
    consent_status: ConsentStatus = ConsentStatus()
    de_identified: bool = False


# ── Legal ─────────────────────────────────────────────────────────────────────


class CaseMetadata(BaseModel):
    case_number: str | None = None
    parties: list[str] = []
    date: str = ""
    jurisdiction: str | None = None


class TestimonyPoint(BaseModel):
    witness: str | None = None
    topic: str = ""
    excerpt: str = ""
    timestamp_range: tuple[float, float] | None = None


class Objection(BaseModel):
    type: str = ""
    context: str = ""
    ruling: str | None = None


class LegalNote(BaseModel):
    summary: str = ""
    key_testimony: list[TestimonyPoint] = []
    objections: list[Objection] = []
    case_metadata: CaseMetadata | None = None


# ── Export ────────────────────────────────────────────────────────────────────


class ExportFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    PDF = "pdf"
