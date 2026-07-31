"""Behavioral and interface tests for the HIPAA REST endpoints (v0.5.0).

Covers the REST surface that was missing from the library-only HIPAA release:

- POST /api/v1/transcribe                 (with ``phi_redaction`` parameter)
- GET  /api/v1/audit-logs                 (+ ``/stats``, ``/export``)
- POST /api/v1/encryption/rotate-key
- POST /api/v1/compliance/baa/generate
- GET  /api/v1/compliance/dashboard       (+ ``/summary``, ``/phi-stats``,
                                           ``/activity``, ``/html``)

The HIPAA middleware dependencies (``get_audit_logger``, etc.) are overridden
in the ``client`` fixture so tests never touch the real ``data/audit_logs``
store and never need a live OpenAI key.
"""

from __future__ import annotations

import pytest

from meeting_notes_ai.auth import create_access_token
from meeting_notes_ai.hipaa.audit_logger import AuditEntry, AuditLogger
from meeting_notes_ai.hipaa.config import HIPAAConfig
from meeting_notes_ai.hipaa.encryption import EncryptionService
from meeting_notes_ai.hipaa.middleware import (
    get_audit_logger,
    get_encryption_service,
)
from meeting_notes_ai.main import app
from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment

# ── Helpers ─────────────────────────────────────────────────────────────────────


def _collect_routes(fastapi_app) -> list:
    """Collect all APIRoute objects, traversing _IncludedRouter wrappers."""
    collected = []
    for r in fastapi_app.routes:
        if type(r).__name__ == "_IncludedRouter":
            collected.extend(r.original_router.routes)
        elif hasattr(r, "path"):
            collected.append(r)
    return collected


def _make_logger(log_dir, instance_id: str = "apitest") -> AuditLogger:
    """Build an AuditLogger pinned to a stable file inside *log_dir*.

    ``_instance_id`` is private, but pinning it makes the file name
    deterministic across the writer instance (test) and the reader
    instances created by the dependency override (endpoint), so the
    API tests exercise the real JSONL round-trip.
    """
    logger = AuditLogger(config=HIPAAConfig(audit_log_dir=str(log_dir)))
    logger._instance_id = instance_id
    return logger


class FakeTranscriber:
    """Fake TranscriptionService that returns a canned transcript.

    Returns two segments mirroring the N1 probe shape: the PHI is split
    across segment boundaries ("Patient John Smith called" / "with SSN
    123-45-6789.") so a regression test can assert no segment leaks
    plaintext PHI.
    """

    def __init__(self, text: str) -> None:
        self.text = text

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.text,
            language=language or "en",
            duration_seconds=1.5,
            segments=[
                TranscriptSegment(
                    start=0.0, end=1.0, text="Patient John Smith called"
                ),
                TranscriptSegment(
                    start=1.0, end=1.5, text="with SSN 123-45-6789."
                ),
            ],
        )


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(_setup_test_db, tmp_path):
    """TestClient with HIPAA audit logging redirected to a temp dir."""
    from fastapi.testclient import TestClient

    audit_dir = tmp_path / "audit"

    def _audit_override() -> AuditLogger:
        return _make_logger(audit_dir)

    app.dependency_overrides[get_audit_logger] = _audit_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_real(_setup_test_db, tmp_path, monkeypatch):
    """TestClient WITHOUT HIPAA dependency overrides.

    ``monkeypatch.chdir`` makes the singleton's relative ``data/audit_logs/``
    config resolve into the temp dir, so the real middleware path is
    exercised without polluting the repository.
    """
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def auth_headers() -> dict:
    """Bearer token for the seeded ``test-user-id`` user."""
    token = await create_access_token("test-user-id")
    return {"Authorization": f"Bearer {token}"}


# ── Interface tests (route registration) ────────────────────────────────────────

EXPECTED_ROUTES = [
    ("POST", "/api/v1/transcribe"),
    ("GET", "/api/v1/audit-logs"),
    ("GET", "/api/v1/audit-logs/stats"),
    ("GET", "/api/v1/audit-logs/export"),
    ("POST", "/api/v1/encryption/rotate-key"),
    ("POST", "/api/v1/compliance/baa/generate"),
    ("GET", "/api/v1/compliance/dashboard"),
    ("GET", "/api/v1/compliance/dashboard/summary"),
    ("GET", "/api/v1/compliance/dashboard/phi-stats"),
    ("GET", "/api/v1/compliance/dashboard/activity"),
    ("GET", "/api/v1/compliance/dashboard/html"),
]


@pytest.mark.parametrize("method,path", EXPECTED_ROUTES)
def test_hipaa_route_registered(method, path):
    """Every HIPAA endpoint must be registered on the FastAPI app."""
    for r in _collect_routes(app):
        if getattr(r, "path", None) == path:
            methods = getattr(r, "methods", None) or set()
            if method in methods:
                return
    pytest.fail(f"{method} {path} not registered on the app")


# ── POST /api/v1/transcribe ─────────────────────────────────────────────────────


class TestTranscribe:
    async def test_transcribe_requires_auth(self, client):
        resp = client.post(
            "/api/v1/transcribe",
            files={"file": ("meeting.wav", b"RIFFdata", "audio/wav")},
        )
        assert resp.status_code == 401, resp.text

    async def test_transcribe_redacts_phi(self, client, auth_headers):
        from meeting_notes_ai.routes.hipaa import get_transcription_service

        app.dependency_overrides[get_transcription_service] = lambda: FakeTranscriber(
            "Patient John Smith called with SSN 123-45-6789."
        )
        resp = client.post(
            "/api/v1/transcribe",
            files={"file": ("meeting.wav", b"RIFFdata", "audio/wav")},
            data={"phi_redaction": "true"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "123-45-6789" not in data["text"], "SSN was not redacted"
        assert "[REDACTED]" in data["text"]
        assert data["phi_redacted"] is True
        assert data["redaction_matches"] >= 1

        # N1 regression: no segments[].text may carry plaintext PHI.
        # The audit entry certifies phi_classification="phi" — the response
        # must not contradict that by leaking identifiers in segments.
        segment_texts = [s.get("text", "") for s in data["segments"]]
        assert segment_texts, "expected segments in response"
        for seg_text in segment_texts:
            assert "123-45-6789" not in seg_text, (
                f"SSN leaked through segment text: {seg_text!r}"
            )
            assert "John Smith" not in seg_text, (
                f"patient name leaked through segment text: {seg_text!r}"
            )

    async def test_transcribe_without_redaction_returns_raw(self, client, auth_headers):
        from meeting_notes_ai.routes.hipaa import get_transcription_service

        text = "Patient John Smith called with SSN 123-45-6789."
        app.dependency_overrides[get_transcription_service] = lambda: FakeTranscriber(
            text
        )
        resp = client.post(
            "/api/v1/transcribe",
            files={"file": ("meeting.wav", b"RIFFdata", "audio/wav")},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["text"] == text
        assert data["phi_redacted"] is False
        assert data["redaction_matches"] == 0


# ── GET /api/v1/audit-logs (+ stats, export) ────────────────────────────────────


class TestAuditLogs:
    async def test_audit_logs_requires_auth(self, client):
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 401

    async def test_audit_logs_query_and_filter(self, client, auth_headers, tmp_path):
        logger = _make_logger(tmp_path / "audit")
        await logger.log(
            AuditEntry(
                timestamp="2026-07-31T08:00:00Z",
                actor="user-42",
                action="phi.redact",
                resource="meeting:abc",
                phi_classification="high",
                outcome="success",
            )
        )
        await logger.log(
            AuditEntry(
                timestamp="2026-07-31T08:05:00Z",
                actor="user-7",
                action="phi.scan",
                resource="meeting:def",
                phi_classification="medium",
                outcome="success",
            )
        )

        resp = client.get("/api/v1/audit-logs", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 2
        # Most recent first
        assert data[0]["actor"] == "user-7"

        resp = client.get(
            "/api/v1/audit-logs?actor=user-42", headers=auth_headers
        )
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "phi.redact"

    async def test_audit_logs_stats(self, client, auth_headers, tmp_path):
        logger = _make_logger(tmp_path / "audit")
        await logger.log(
            AuditEntry(
                timestamp="2026-07-31T08:00:00Z",
                actor="user-42",
                action="phi.redact",
                resource="meeting:abc",
                phi_classification="high",
                outcome="success",
            )
        )
        resp = client.get("/api/v1/audit-logs/stats", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        stats = resp.json()
        assert stats["total_entries"] == 1
        assert stats["actions"] == {"phi.redact": 1}
        assert stats["unique_actors"] == 1

    async def test_audit_logs_export(self, client, auth_headers, tmp_path):
        logger = _make_logger(tmp_path / "audit")
        await logger.log(
            AuditEntry(
                timestamp="2026-07-31T08:00:00Z",
                actor="user-42",
                action="phi.redact",
                resource="meeting:abc",
                phi_classification="high",
                outcome="success",
            )
        )
        resp = client.get(
            "/api/v1/audit-logs/export?start=2026-07-01&end=2026-12-31",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert "jsonl" in resp.headers.get("content-disposition", "").lower()
        assert "phi.redact" in resp.text


# ── Real middleware singleton wiring (no dependency overrides) ──────────────────


class TestRealMiddlewareWiring:
    """Verify the process-wide singleton deps make state persist across requests.

    Without the singleton fix, every request would get a fresh AuditLogger
    with a random instance id — a different log file per request — and the
    audit-logs endpoint would never see entries written by other requests.
    """

    async def test_audit_entries_persist_across_requests(
        self, client_real, auth_headers
    ):
        from meeting_notes_ai.routes.hipaa import get_transcription_service

        app.dependency_overrides[get_transcription_service] = lambda: FakeTranscriber(
            "Patient John Smith called with SSN 123-45-6789."
        )
        try:
            resp = client_real.post(
                "/api/v1/transcribe",
                files={"file": ("meeting.wav", b"RIFFdata", "audio/wav")},
                data={"phi_redaction": "true"},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["phi_redacted"] is True

            # A second request must observe the first request's audit entry.
            resp = client_real.get("/api/v1/audit-logs", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            entries = resp.json()
            assert any(e["action"] == "transcribe" for e in entries)
        finally:
            app.dependency_overrides.clear()


# ── POST /api/v1/encryption/rotate-key ──────────────────────────────────────────


class TestRotateKey:
    async def test_rotate_key_rewraps_tenant_keys(
        self, client, auth_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HIPAA_MASTER_KEY", "apitest-master-key")
        svc = EncryptionService(config=HIPAAConfig())
        await svc.generate_tenant_key("tenant-1")
        app.dependency_overrides[get_encryption_service] = lambda: svc

        resp = client.post(
            "/api/v1/encryption/rotate-key",
            json={"new_master_key": "rotated-master-key"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["re_wrapped_keys"] == 1
        assert data["rotated_at"]

    async def test_rotate_key_rejects_empty_secret(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setenv("HIPAA_MASTER_KEY", "apitest-master-key")
        resp = client.post(
            "/api/v1/encryption/rotate-key",
            json={"new_master_key": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ── POST /api/v1/compliance/baa/generate ────────────────────────────────────────


class TestBAAGenerate:
    async def test_baa_generate_stores_agreement(self, client, auth_headers):
        resp = client.post(
            "/api/v1/compliance/baa/generate",
            json={
                "org_name": "Acme Health Systems",
                "ba_name": "CloudNotes Inc.",
                "signed_by": "Dr. Jane Smith",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["agreement_id"]
        assert data["org_name"] == "Acme Health Systems"
        assert data["ba_name"] == "CloudNotes Inc."
        assert data["status"] == "active"
        assert len(data["content_md"]) > 100, "Rendered BAA content missing"

    async def test_baa_generate_validates_required_fields(self, client, auth_headers):
        resp = client.post(
            "/api/v1/compliance/baa/generate",
            json={"org_name": "Acme Health Systems"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ── GET /api/v1/compliance/dashboard ────────────────────────────────────────────


class TestComplianceDashboard:
    async def test_dashboard_requires_auth(self, client):
        resp = client.get("/api/v1/compliance/dashboard")
        assert resp.status_code == 401

    async def test_dashboard_combined_payload(self, client, auth_headers):
        resp = client.get("/api/v1/compliance/dashboard", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "summary" in data
        assert "phi_stats" in data
        assert "activity" in data
        assert "overall_compliance_score" in data["summary"]
        assert isinstance(data["activity"], list)

    async def test_dashboard_summary(self, client, auth_headers):
        resp = client.get(
            "/api/v1/compliance/dashboard/summary", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        for key in (
            "total_phi_scans",
            "total_redactions",
            "active_encryption_keys",
            "active_baa_agreements",
            "audit_entries_30d",
            "overall_compliance_score",
            "encryption_health",
        ):
            assert key in summary, f"summary missing '{key}'"

    async def test_dashboard_phi_stats(self, client, auth_headers):
        resp = client.get(
            "/api/v1/compliance/dashboard/phi-stats", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        stats = resp.json()
        assert "by_category" in stats
        assert "by_risk_level" in stats

    async def test_dashboard_activity(self, client, auth_headers, tmp_path):
        logger = _make_logger(tmp_path / "audit")
        await logger.log(
            AuditEntry(
                timestamp="2026-07-31T08:00:00Z",
                actor="user-42",
                action="phi.redact",
                resource="meeting:abc",
                outcome="success",
            )
        )
        resp = client.get(
            "/api/v1/compliance/dashboard/activity?limit=10",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["actor"] == "user-42"

    async def test_dashboard_html_page_served(self, client):
        resp = client.get("/api/v1/compliance/dashboard/html")
        assert resp.status_code == 200
        assert "HIPAA Compliance Dashboard" in resp.text
        assert "text/html" in resp.headers.get("content-type", "")
