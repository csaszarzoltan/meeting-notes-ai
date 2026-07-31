#!/usr/bin/env python3
"""HIPAA REST endpoints example — exercise the full v0.5.0 REST surface.

Walks every HIPAA endpoint of the FastAPI app in-process (TestClient — no
server or network needed) with a real JWT bearer token:

    POST /api/v1/transcribe                       (with phi_redaction)
    GET  /api/v1/audit-logs                       (+ /stats, /export)
    POST /api/v1/encryption/rotate-key
    POST /api/v1/compliance/baa/generate
    GET  /api/v1/compliance/dashboard             (+ /summary, /phi-stats,
                                                   /activity, /html)

Notes:
- The transcription service is faked so the example runs without an
  ``OPENAI_API_KEY``; in production the endpoint calls the OpenAI Whisper
  API and requires that env var.
- The audit logger is redirected to a temp directory so the repository's
  ``data/audit_logs/`` store is untouched. In production the middleware
  dependencies resolve to process-wide singletons writing to that store.
- A fresh in-memory SQLite database is seeded with one user for auth; the
  example never touches a real database.

Run from the repository root:

    HIPAA_MASTER_KEY=dev-master-key PYTHONPATH=src .venv/bin/python \\
        examples/hipaa_rest_endpoints.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault("HIPAA_MASTER_KEY", "dev-master-key")

from fastapi.testclient import TestClient

from meeting_notes_ai.auth import create_access_token
from meeting_notes_ai.db.engine import create_db_engine, create_session_factory, init_db
from meeting_notes_ai.db.models import User
from meeting_notes_ai.db.session import set_session_factory
from meeting_notes_ai.hipaa.audit_logger import AuditLogger
from meeting_notes_ai.hipaa.config import HIPAAConfig
from meeting_notes_ai.hipaa.middleware import get_audit_logger
from meeting_notes_ai.main import app
from meeting_notes_ai.models import TranscriptionResult, TranscriptSegment
from meeting_notes_ai.routes.hipaa import get_transcription_service


class FakeTranscriber:
    """Canned transcript — stands in for the OpenAI Whisper API."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text="Patient John Smith called with SSN 123-45-6789.",
            language=language or "en",
            duration_seconds=1.5,
            segments=[TranscriptSegment(start=0.0, end=1.5, text="Patient John Smith")],
        )


def _setup_db() -> None:
    """Create an in-memory SQLite DB and seed one active user for auth."""

    async def _setup() -> None:
        engine = create_db_engine("sqlite+aiosqlite://", echo=False)
        factory = create_session_factory(engine)
        set_session_factory(factory)
        await init_db(engine)
        async with factory() as session:
            session.add(
                User(
                    id="rest-example-user",
                    email="rest@example.com",
                    hashed_password="hashed_placeholder",
                    display_name="REST Example User",
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(_setup())


def main() -> None:
    _setup_db()
    token = asyncio.run(create_access_token("rest-example-user"))
    headers = {"Authorization": f"Bearer {token}"}

    # Redirect audit logging to a temp dir (keeps the repo store clean).
    audit_dir = tempfile.mkdtemp(prefix="hipaa-rest-example-")
    logger = AuditLogger(config=HIPAAConfig(audit_log_dir=audit_dir))
    logger._instance_id = "rest-example"
    app.dependency_overrides[get_transcription_service] = lambda: FakeTranscriber()
    app.dependency_overrides[get_audit_logger] = lambda: logger

    with TestClient(app) as client:
        # ── Auth is enforced: no token → 401 ────────────────────────────────
        r = client.get("/api/v1/audit-logs")
        print("GET  /api/v1/audit-logs (no token)      ->", r.status_code)

        # ── POST /api/v1/transcribe ─────────────────────────────────────────
        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("consultation.mp3", b"RIFFdata", "audio/mpeg")},
            data={"phi_redaction": "true"},
            headers=headers,
        )
        print("POST /api/v1/transcribe (phi_redaction) ->", r.status_code)
        body = r.json()
        print(f"    text={body['text']!r}")
        print(f"    language={body['language']!r} duration={body['duration_seconds']}s")
        print(f"    phi_redacted={body['phi_redacted']} matches={body['redaction_matches']}")

        # ── GET /api/v1/audit-logs (+ stats, export) ────────────────────────
        r = client.get("/api/v1/audit-logs", headers=headers)
        entries = r.json()
        print(
            "GET  /api/v1/audit-logs                ->",
            r.status_code,
            f"({len(entries)} entries)",
        )
        for e in entries:
            print(f"    {e['timestamp']} actor={e['actor']} action={e['action']} "
                  f"resource={e['resource']} outcome={e['outcome']}")

        r = client.get("/api/v1/audit-logs/stats", headers=headers)
        print("GET  /api/v1/audit-logs/stats          ->", r.status_code)
        print(f"    {r.json()}")

        r = client.get(
            "/api/v1/audit-logs/export?start=2026-01-01&end=2026-12-31",
            headers=headers,
        )
        print("GET  /api/v1/audit-logs/export         ->", r.status_code,
              f"({r.headers.get('content-type')}, {len(r.content)} bytes)")

        # ── POST /api/v1/encryption/rotate-key ──────────────────────────────
        r = client.post(
            "/api/v1/encryption/rotate-key",
            json={"new_master_key": "rotated-master-key-123"},
            headers=headers,
        )
        print("POST /api/v1/encryption/rotate-key     ->", r.status_code)
        print(f"    {r.json()}")

        # ── POST /api/v1/compliance/baa/generate ────────────────────────────
        r = client.post(
            "/api/v1/compliance/baa/generate",
            json={
                "org_name": "Acme Health Systems",
                "ba_name": "CloudNotes Inc.",
                "signed_by": "Dr. Jane Smith",
            },
            headers=headers,
        )
        print("POST /api/v1/compliance/baa/generate   ->", r.status_code)
        body = r.json()
        print(f"    id={body['agreement_id']} org={body['org_name']} ba={body['ba_name']}")
        print(f"    status={body['status']} effective={body['effective_date']}")
        print(f"    content_md: {len(body['content_md'])} chars (HIPAA §164.504(e) markdown)")

        # ── GET /api/v1/compliance/dashboard (+ summary, phi-stats, activity) ─
        r = client.get("/api/v1/compliance/dashboard", headers=headers)
        print("GET  /api/v1/compliance/dashboard      ->", r.status_code)
        print(f"    keys: {sorted(r.json().keys())}")

        r = client.get("/api/v1/compliance/dashboard/summary", headers=headers)
        print("GET  /api/v1/compliance/dashboard/summary ->", r.status_code)
        print(f"    {r.json()}")

        r = client.get("/api/v1/compliance/dashboard/phi-stats", headers=headers)
        print("GET  /api/v1/compliance/dashboard/phi-stats ->", r.status_code)
        print(f"    keys: {sorted(r.json().keys())}")

        r = client.get("/api/v1/compliance/dashboard/activity?limit=5", headers=headers)
        print("GET  /api/v1/compliance/dashboard/activity ->", r.status_code,
              f"({len(r.json())} entries)")

        # ── GET /api/v1/compliance/dashboard/html (no auth) ─────────────────
        r = client.get("/api/v1/compliance/dashboard/html")
        print("GET  /api/v1/compliance/dashboard/html (no token) ->", r.status_code,
              f"({r.headers.get('content-type')})")

    app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
