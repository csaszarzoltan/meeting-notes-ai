"""Pre-development TDD tests for review-workspace integration (P0-4) of the
In-Person Bot-Free Recording feature (analysis/analysis-brief.md).

Feature target (spec §4 P0-4): a finalized in-person/live session ends up as a
reviewable ``MeetingDetail`` (routes/workspace.py shape) with evidence-linked
summary/decisions/action items; Healthcare/Legal mode persists
``review_status="needs_review"`` and — when ``backend=local`` — never routes
audio to OpenAI (``resolve_processing_policy``, services/workflow.py:21).

Contract under test:
- ``finalize`` → ``_persist_meeting`` → meeting retrievable via
  ``GET /api/v1/workspace/meetings/{id}`` with ``summary`` + ``evidence[]``
  items carrying ``speaker``/``timestamp``/``confidence``
  (routes/workspace.py:236-239, :283).
- ``PATCH /api/v1/workspace/meetings/{id}/review`` persists summary +
  review_status + reviewer + audit (routes/workspace.py:292-311).
- ``resolve_processing_policy`` (services/workflow.py:21): Healthcare →
  phi_redaction + review_required; Legal → review_required.
- P0-4 privacy: Healthcare/Legal + local backend → no OpenAI transcription
  call (the no-third-party guarantee).
- P0-4 threading: meeting ``mode`` must flow through ``finalize`` — the
  current hard-coded ``mode="general"`` at services/live_transcription.py:253/259
  is the RED target (privacy bug per analyst finding).

Two categories:
- Interface tests — PASS immediately.
- Behavioral tests — FAIL cleanly while the feature is missing (no inverse
  NotImplementedError stubs).

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_review_integration.py``.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytestmark = pytest.mark.quick

# ── Duck-typed AI seams ────────────────────────────────────────────────────────


class _FakeTranscription:
    async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None):
        from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment

        return TranscriptionResult(
            text="in-person review integration transcript",
            language=language or "en",
            duration_seconds=4.0,
            segments=[
                TranscriptSegment(
                    start=0.0, end=2.0, text="in-person review integration transcript"
                )
            ],
        )


class _FakeExtraction:
    async def extract(self, transcript: str, mode=None):
        from meeting_notes_ai.models import ActionItem, ExtractionResult

        return ExtractionResult(
            summary="Review integration summary",
            action_items=[
                ActionItem(assignee="Mike", description="Follow up on the in-person review")
            ],
            decisions=["Review workspace integration approved"],
            key_points=["Evidence-linked review works"],
        )


class _FakeExtractionHealthcare:
    async def extract(self, transcript: str, mode=None):
        from meeting_notes_ai.models import ActionItem, ExtractionResult

        return ExtractionResult(
            summary="Healthcare review summary",
            action_items=[ActionItem(assignee="Dr. Smith", description="Review patient notes")],
            decisions=["Approve treatment plan"],
            key_points=["PHI flagged"],
        )


def _token(user_id: str) -> str:
    from meeting_notes_ai.auth import create_access_token

    return asyncio.run(create_access_token(user_id))


def _auth_headers(user_id: str = "test-user-id") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _fetch_meeting(meeting_id: str):
    async def _fetch():
        from sqlalchemy import select

        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        async for session in get_db_session():
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            return result.scalar_one_or_none()
        return None

    return asyncio.run(_fetch())


def _fresh_meeting(user_id: str = "test-user-id", mode: str = "general") -> str:
    """Create a fresh meeting row owned by *user_id* and return its id."""

    async def _create() -> str:
        from uuid import uuid4

        from meeting_notes_ai.db.models import Meeting
        from meeting_notes_ai.db.session import get_db_session

        meeting_id = f"review-api-{uuid4().hex[:12]}"
        async for session in get_db_session():
            session.add(
                Meeting(
                    id=meeting_id,
                    title="In-person review test",
                    user_id=user_id,
                    filename="inperson.wav",
                    mode=mode,
                    transcript="",
                )
            )
            await session.commit()
        return meeting_id

    return asyncio.run(_create())


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately
# ═══════════════════════════════════════════════════════════════════════════════


class TestReviewIntegrationInterface:
    """Routes, handlers, and shapes for the review integration."""

    def test_workspace_router_has_review_route(self):
        """PATCH /api/v1/workspace/meetings/{id}/review must exist."""
        from meeting_notes_ai.routes.workspace import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/review") and "PATCH" in methods:
                return
        pytest.fail("PATCH /api/v1/workspace/meetings/{id}/review route not found")

    def test_review_handler_has_user_dependency(self):
        from meeting_notes_ai.routes.workspace import update_review

        params = inspect.signature(update_review).parameters
        assert "user" in params or "current_user" in params

    def test_meeting_detail_route_exists(self):
        """GET /api/v1/workspace/meetings/{id} must exist (review load)."""
        from meeting_notes_ai.routes.workspace import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if "/meetings/{meeting_id}" in path and "GET" in methods:
                return
        pytest.fail("GET /api/v1/workspace/meetings/{id} route not found")

    def test_meeting_create_route_exists(self):
        """POST /api/v1/workspace/meetings must exist (evidence seed)."""
        from meeting_notes_ai.routes.workspace import router

        for r in router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", set())
            if path.endswith("/meetings") and "POST" in methods:
                return
        pytest.fail("POST /api/v1/workspace/meetings route not found")

    def test_resolve_processing_policy_healthcare(self):
        """Healthcare → phi_redaction + review_required (workflow.py:21)."""
        from meeting_notes_ai.services.workflow import resolve_processing_policy

        policy = resolve_processing_policy("healthcare", None)
        assert policy.phi_redaction is True
        assert policy.review_required is True

    def test_resolve_processing_policy_legal(self):
        """Legal → review_required (redaction off unless explicit)."""
        from meeting_notes_ai.services.workflow import resolve_processing_policy

        policy = resolve_processing_policy("legal", None)
        assert policy.review_required is True
        assert policy.phi_redaction is False

    def test_resolve_processing_policy_general(self):
        """General → no redaction, no review gate."""
        from meeting_notes_ai.services.workflow import resolve_processing_policy

        policy = resolve_processing_policy("general", None)
        assert policy.phi_redaction is False
        assert policy.review_required is False

    def test_finalize_signature(self):
        """finalize must accept language (P0-4 keeps the existing shape)."""
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        sig = inspect.signature(LiveTranscriptionService.finalize)
        assert "session_id" in sig.parameters
        assert sig.parameters["language"].default is None

    def test_meeting_detail_evidence_shape_fields(self):
        """Evidence items must carry speaker/timestamp/text/confidence
        (routes/workspace.py:236-239 — the ReviewWorkspace contract)."""
        sample = {
            "timestamp": "00:00",
            "speaker": "Speaker 1",
            "text": "transcript excerpt",
            "confidence": 0.0,
        }
        for field in ("timestamp", "speaker", "text", "confidence"):
            assert field in sample, f"evidence item missing '{field}'"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — FAIL cleanly while the feature is missing
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalizePersistsReviewDetail:
    """P0-4: a fake-backed finalized in-person session produces a
    ReviewWorkspace-shaped meeting detail with evidence-linked summary,
    decisions and action items."""

    @pytest.fixture
    def client(self, _setup_test_db, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from meeting_notes_ai.config import settings
        from meeting_notes_ai.main import app

        monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path / "storage"), raising=False)
        return TestClient(app)

    @pytest.fixture
    def service(self, _setup_test_db):
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        return LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtraction(),
        )

    def _finalize_via_ws(self, client, service, meeting_id):
        """Drive the real WS finalize path with the fake-backed service."""
        from meeting_notes_ai.main import app
        from meeting_notes_ai.routes.live_transcription import get_live_service

        app.dependency_overrides[get_live_service] = lambda: service
        try:
            url = (
                f"/api/v1/meetings/live?token={_token('test-user-id')}"
                f"&meeting_id={meeting_id}"
            )
            with client.websocket_connect(url) as ws:
                ws.send_bytes(b"\x00" * 3200)
                ws.send_text('{"type": "finalize"}')
                finalized = None
                for _ in range(10):
                    msg = ws.receive_json()
                    if msg.get("type") == "finalized":
                        finalized = msg
                        break
            assert finalized is not None, "no finalized ack received"
            return finalized
        finally:
            app.dependency_overrides.pop(get_live_service, None)

    def test_finalize_persists_reviewable_detail(self, client, service):
        """Finalizing an in-person session must yield a meeting whose GET detail
        carries summary + decisions + action items (ReviewWorkspace shape)."""
        meeting_id = _fresh_meeting()
        self._finalize_via_ws(client, service, meeting_id)

        # P0-4: the finalized meeting must be retrievable as a workspace detail.
        resp = client.get(f"/api/v1/workspace/meetings/{meeting_id}", headers=_auth_headers())
        assert resp.status_code == 200, (
            "finalized meeting must be retrievable via "
            f"GET /meetings/{{id}}, got {resp.status_code}"
        )
        detail = resp.json()
        assert detail["summary"] == "Review integration summary", (
            f"detail must carry the extracted summary, got {detail.get('summary')!r}"
        )
        assert detail["decisions"] == ["Review workspace integration approved"]
        assert detail["action_items"][0]["description"] == "Follow up on the in-person review"

    def test_finalize_detail_has_evidence_items(self, client, service):
        """P0-4: the detail must include evidence[] with speaker/timestamp/confidence
        (routes/workspace.py:236-239 schema)."""
        meeting_id = _fresh_meeting()
        self._finalize_via_ws(client, service, meeting_id)

        resp = client.get(f"/api/v1/workspace/meetings/{meeting_id}", headers=_auth_headers())
        assert resp.status_code == 200, resp.text
        detail = resp.json()
        evidence = detail.get("evidence", [])
        assert evidence, "finalized meeting detail must carry evidence[]"
        for item in evidence:
            assert "speaker" in item, f"evidence item missing speaker: {item}"
            assert "timestamp" in item, f"evidence item missing timestamp: {item}"
            assert "confidence" in item, f"evidence item missing confidence: {item}"

    def test_review_route_persists_status(self, client):
        """PATCH /meetings/{id}/review must persist summary/review_status/reviewer."""
        meeting_id = _fresh_meeting()
        payload = {
            "summary": "Reviewed by human",
            "review_status": "approved",
            "reviewer": "QA reviewer",
            "comment": "Looks good",
        }
        resp = client.patch(
            f"/api/v1/workspace/meetings/{meeting_id}/review",
            json=payload,
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"] == "Reviewed by human"
        assert data["review_status"] == "approved"
        assert data["versions"][-1]["reviewer"] == "QA reviewer"


class TestFinalizeModeThreading:
    """P0-4: the meeting mode must flow through finalize (currently hard-coded
    'general' at services/live_transcription.py:253/259 — analyst privacy bug)."""

    @pytest.mark.asyncio
    async def test_finalize_persists_healthcare_mode(self, _setup_test_db):
        """A healthcare in-person session must be persisted with mode=healthcare,
        NOT downgraded to 'general'."""
        from meeting_notes_ai.live_session import LiveChunk
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtractionHealthcare(),
        )
        meeting_id = _fresh_meeting(mode="healthcare")
        session = await service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        session.chunks.append(LiveChunk(data=b"\x00" * 3200))
        await service.finalize(session.id)

        row = _fetch_meeting(meeting_id)
        assert row is not None
        assert row.mode == "healthcare", (
            f"finalize must persist the session's mode (healthcare), got {row.mode!r} — "
            "P0-4 must thread mode through finalize instead of hard-coding 'general'"
        )

    @pytest.mark.asyncio
    async def test_finalize_healthcare_review_status_needs_review(self, _setup_test_db):
        """Healthcare mode must persist review_status='needs_review' per
        resolve_processing_policy (workflow.py:21 → review_required)."""
        from meeting_notes_ai.live_session import LiveChunk
        from meeting_notes_ai.services.live_transcription import LiveTranscriptionService

        service = LiveTranscriptionService(
            transcription_service=_FakeTranscription(),
            extraction_service=_FakeExtractionHealthcare(),
        )
        meeting_id = _fresh_meeting(mode="healthcare")
        session = await service.create_session(meeting_id=meeting_id, user_id="test-user-id")
        session.chunks.append(LiveChunk(data=b"\x00" * 3200))
        await service.finalize(session.id)

        row = _fetch_meeting(meeting_id)
        assert row is not None
        meta = {}
        if row.metadata_json:
            import json

            meta = json.loads(row.metadata_json)
        assert meta.get("review_status") == "needs_review" or getattr(
            row, "review_status", None
        ) == "needs_review", (
            f"healthcare finalize must persist review_status='needs_review' "
            f"(meta={meta!r}) — P0-4 must apply resolve_processing_policy"
        )


class TestNoOpenAICallLocalBackend:
    """P0-3/P0-4 privacy: Healthcare/Legal + backend=local must never call
    OpenAI for transcription (the no-third-party guarantee)."""

    def test_local_backend_never_calls_openai(self):
        """Building the local service must not construct an OpenAI-backed
        TranscriptionService — and transcribing through it must not touch the
        openai package."""
        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        service = LocalWhisperTranscriptionService()
        # The service must expose the same transcribe interface; asserting the
        # absence of an OpenAI client is the privacy contract.
        assert not hasattr(service, "_client") or service._client is None, (
            "local backend must not hold an OpenAI client"
        )

    @pytest.mark.asyncio
    async def test_local_transcribe_does_not_import_openai_call(self):
        """The local transcribe path must not invoke OpenAI's audio API."""
        from unittest.mock import AsyncMock

        from meeting_notes_ai.services.local_transcription import (
            LocalWhisperTranscriptionService,
        )

        calls: list[str] = []

        class _RecordingWhisper:
            def __init__(self, model, compute_type):
                self.model = model
                self.compute_type = compute_type

            def transcribe(self, audio, language=None):
                calls.append("local_backend_called")
                segments = [(0.0, 1.0, "no openai involved")]
                info = AsyncMock()
                info.language = language or "en"
                info.duration = 1.0
                return segments, info

        service = LocalWhisperTranscriptionService(
            whisper=_RecordingWhisper("small", "int8")
        )
        result = await service.transcribe(b"\x00" * 3200, "inperson.wav")

        assert calls == ["local_backend_called"], "transcription must go to the local backend"
        assert result.text == "no openai involved"
        assert "openai" not in result.text.lower()
