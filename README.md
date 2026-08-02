# MeetingNotesAI

Micro-SaaS for meeting transcription and structured notes.

![Version](https://img.shields.io/badge/version-0.6.2-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![HIPAA](https://img.shields.io/badge/HIPAA-ready-8A2BE2)

## Features

- **Transcription**: Upload audio files for transcription via OpenAI Whisper API
- **Extraction**: Automatically extract action items, decisions, and key points using LLM
- **Mode-specific processing**:
  - **General**: Standard meeting notes
  - **Healthcare**: SOAP notes with HIPAA compliance markers
  - **Legal**: Deposition summaries with objection tracking
- **HIPAA Compliance (v0.5.0+)**: PHI redaction, append-only audit logging, AES-256-GCM encryption at rest, BAA template generation, and a compliance dashboard — as a Python library **and** as REST endpoints (see [HIPAA Mode](docs/HIPAA_MODE.md))
- **Multi-format Export**: JSON, Markdown, PDF, and ZIP batch download
- **Batch Processing**: Upload up to 10 audio files per batch with per-file status tracking
- **Team Workspaces**: Multi-user teams with role-based access (admin/member/viewer)
- **Webhook Notifications**: Automatic HTTP callbacks on batch completion with HMAC-SHA256 signing
- **Meeting Sharing**: Generate shareable links with configurable expiration (1h, 24h, 7d, never). Revoke links or let them auto-expire. Public endpoint serves meeting summaries without authentication.
- **JWT Authentication**: Bearer token signup/login with 24h expiry
- **Database**: Async SQLAlchemy with Railway Postgres (Alembic-ready)
- **SSRF Protection**: Built-in URL validation to prevent server-side request forgery

## HIPAA Compliance Mode (v0.5.0+)

MeetingNotesAI ships a **HIPAA compliance library** for healthcare meeting
transcription and PHI (Protected Health Information) processing. It lives in
`meeting_notes_ai.hipaa` and covers five areas:

- **PHI Redaction** — Regex-based detection of HIPAA identifiers (SSN, DOB,
  phone, email, MRN, names) with configurable modes: `mask`, `hash`,
  `truncate`, `annotate`, plus runtime custom patterns.
- **Append-Only Audit Logging** — JSONL audit trail for all PHI access and
  processing events with mandatory fields (timestamp, actor, action, resource),
  6-year default retention, manual rotation, and date-range export.
- **AES-256 Encryption at Rest** — Envelope encryption: a master KEK (derived
  from `HIPAA_MASTER_KEY`) wraps per-tenant AES-256-GCM data keys. Field- and
  document-level encrypt/decrypt, master key rotation.
- **BAA Template & Management** — Jinja2 Business Associate Agreement template
  with all HIPAA §164.504(e) clauses, immutable agreement storage, PDF export
  via fpdf2.
- **Compliance Dashboard Data** — `ComplianceService` aggregates audit,
  encryption, BAA, and PHI statistics into a compliance summary and chart-ready
  data.

### REST Endpoints (v0.5.0+)

All HIPAA data endpoints are wired into the FastAPI app since v0.5.0 and
require a **Bearer JWT** (`Authorization: Bearer <token>` — the same
`get_current_user` dependency as `/api/v1/meetings`). The dashboard HTML page
is the one exception: `GET /api/v1/compliance/dashboard/html` is
unauthenticated (it serves the Chart.js shell; the page's client-side fetches
need the token).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/transcribe` | Transcribe audio (multipart `file`); optional `language`, `phi_redaction` (bool). Requires `OPENAI_API_KEY`. Writes an audit entry (`action=transcribe`). |
| GET | `/api/v1/audit-logs` | Query audit entries (filters: `actor`, `action`, `resource`; `limit` default 100, max 1000), newest first. |
| GET | `/api/v1/audit-logs/stats` | Aggregate audit statistics (optional `since` ISO). |
| GET | `/api/v1/audit-logs/export` | Export audit entries in a date range (`start`, `end` ISO) as a JSONL attachment. |
| POST | `/api/v1/encryption/rotate-key` | Rotate the master KEK (`new_master_key`); re-wraps all tenant DEKs. Requires `HIPAA_MASTER_KEY` (503 when missing). |
| POST | `/api/v1/compliance/baa/generate` | Generate + immutably store a BAA (`org_name`, `ba_name`, `signed_by`). |
| GET | `/api/v1/compliance/dashboard` | Combined compliance payload (`summary`, `phi_stats`, `activity`). |
| GET | `/api/v1/compliance/dashboard/summary` | Compliance summary card. |
| GET | `/api/v1/compliance/dashboard/phi-stats` | PHI detection statistics (by category/risk/date). |
| GET | `/api/v1/compliance/dashboard/activity` | Recent audit activity (`limit` default 50, max 500), newest first. |
| GET | `/api/v1/compliance/dashboard/html` | Serves the Chart.js dashboard page (unauthenticated). |

Quick examples (get a token from `POST /api/v1/auth/login` first):

```bash
# Transcribe with PHI redaction (multipart; OPENAI_API_KEY must be set)
curl -X POST http://localhost:8000/api/v1/transcribe \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@consultation.mp3" \
  -F "phi_redaction=true"

# Query audit logs (newest first, default limit 100)
curl http://localhost:8000/api/v1/audit-logs \
  -H "Authorization: Bearer $TOKEN"

# Rotate the master key
curl -X POST http://localhost:8000/api/v1/encryption/rotate-key \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_master_key": "new-kek-secret"}'

# Generate a Business Associate Agreement
curl -X POST http://localhost:8000/api/v1/compliance/baa/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"org_name": "Acme Health Systems", "ba_name": "CloudNotes Inc.", "signed_by": "Dr. Jane Smith"}'

# Compliance dashboard (combined)
curl http://localhost:8000/api/v1/compliance/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

> **Scope note:** `POST /api/v1/meetings` still does **not** redact PHI
> automatically — use `POST /api/v1/transcribe` with `phi_redaction=true`, or
> the library directly. The old analysis-brief `/api/v1/hipaa/*` paths were
> never shipped; the canonical paths are the `/api/v1/transcribe`,
> `/api/v1/audit-logs*`, `/api/v1/encryption/rotate-key`, and
> `/api/v1/compliance/*` routes above.

### Configuration

Configuration is done with the `HIPAAConfig` dataclass; defaults are safe for
development. The library reads `HIPAA_MASTER_KEY` (the encryption KEK seed);
the REST endpoints additionally require `OPENAI_API_KEY` (transcription) and
`HIPAA_MASTER_KEY` (key rotation):

| Field | Default | Description |
|----------|---------|-------------|
| `phi_patterns_path` | `hipaa/phi_patterns.json` | Path to PHI patterns JSON (falls back to built-ins) |
| `audit_log_dir` | `data/audit_logs/` | Audit log storage directory |
| `audit_log_retention_days` | `2190` | Log retention (6 years, HIPAA minimum) |
| `encryption_enabled` | `true` | Fail fast if `HIPAA_MASTER_KEY` is missing |
| `master_key_env_var` | `HIPAA_MASTER_KEY` | Env var holding the KEK seed |
| `baa_template_path` | `hipaa/templates/baa_template.md.jinja` | BAA Jinja2 template |
| `default_baa_effective_days` | `365` | Default BAA effective period in days |
| `llm_validation_enabled` | `true` | LLM validation toggle (stub in v0.5.0) |
| `llm_validation_threshold` | `0.8` | Confidence threshold (0.0–1.0) |

See [docs/HIPAA_MODE.md](docs/HIPAA_MODE.md) for the full guide, and
[`examples/`](examples/) for runnable scripts covering every feature area.

### Getting Started — Healthcare Mode

**Healthcare meeting notes (SOAP + HIPAA markers)** are a REST feature since
v0.2.0 — pass `mode=healthcare` to the meeting endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/meetings \
  -F "file=@consultation.mp3" \
  -F "mode=healthcare" \
  -F "patient_id=pat-001" \
  -F "consent_confirmed=true"
```

**PHI redaction, audit logging, encryption, BAA, and compliance metrics** are
available since v0.5.0 both as a Python library and via the REST endpoints
listed above:

```python
from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor
from meeting_notes_ai.hipaa.audit_logger import AuditLogger, AuditEntry
from meeting_notes_ai.hipaa.config import HIPAAConfig
import asyncio

async def main():
    # Redact PHI before storing a transcript
    redactor = PHIRedactor()
    redacted, matches = redactor.redact(
        "Patient John Smith, SSN 123-45-6789, DOB 03/14/1985"
    )
    print(redacted)  # [REDACTED], SSN [REDACTED], DOB [REDACTED]

    # Audit the redaction event
    logger = AuditLogger(config=HIPAAConfig(audit_log_dir="/tmp/audit-logs"))
    await logger.log(AuditEntry(
        timestamp="2026-07-31T12:00:00Z",
        actor="user-42",
        action="phi.redact",
        resource="meeting:abc-123",
        phi_classification="high",
    ))

asyncio.run(main())
```

Encryption requires `HIPAA_MASTER_KEY` to be set (any string — the 32-byte AES
key is derived via SHA-256):

```bash
export HIPAA_MASTER_KEY="$(openssl rand -hex 32)"
PYTHONPATH=src .venv/bin/python examples/hipaa_rotate_key.py
```

---

## Secure File Storage (v0.7.0)

Since v0.7.0, MeetingNotesAI stores uploaded audio durably instead of
discarding it after transcription. Files live in a **vendor-agnostic object
storage layer** (`meeting_notes_ai.storage`) with DB-persisted metadata
(`storage_files` table), RBAC-protected download endpoints, a **HIPAA
retention engine** with audit logging, and optional **AES-256-GCM
encryption at rest** that works identically on every backend.

> **Security note:** the legacy `POST /api/v1/meetings` and
> `POST /api/v1/transcribe` endpoints remain unauthenticated (out of scope).
> The storage router below is **fully authenticated** — every endpoint
> requires a Bearer JWT and meeting access is enforced per RBAC.

### Backends

`STORAGE_BACKEND` selects the backend (no code change required to switch):

| Backend | `STORAGE_BACKEND` | Notes |
|---------|-------------------|-------|
| Local filesystem | `local` (default) | Root at `STORAGE_LOCAL_DIR` (`data/storage`); files written `0600`, traversal-safe. Used by the quick test suite. |
| AWS S3 | `s3` | `S3_*` env vars; pre-provision the bucket (auto-created on first put). |
| Cloudflare R2 | `s3` + `S3_ENDPOINT_URL` | `https://<account>.r2.cloudflarestorage.com`, `S3_REGION=auto` |
| MinIO (dev) | `s3` + `S3_ENDPOINT_URL` | `docker compose -f docker-compose.dev.yml up -d minio` |

### REST endpoints (all authenticated)

| Method | Path | RBAC | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/meetings/{meeting_id}/audio` | owner / team member (write) | Upload audio (multipart `file`, MIME allowlist, 25 MB cap, streamed SHA-256). 201 + metadata; 409 on duplicate; 413 oversize; 415 bad MIME. |
| GET | `/api/v1/meetings/{meeting_id}/audio` | owner / any team member | Download stored audio (Content-Disposition attachment). 404 when none. |
| DELETE | `/api/v1/meetings/{meeting_id}/audio` | owner / team member (write) | Soft-delete the stored audio. 204. |
| GET | `/api/v1/meetings/{meeting_id}/transcript` | owner / any team member | Transcript as `.txt` attachment (stored transcript file, else `Meeting.transcript`). |
| PUT | `/api/v1/teams/{team_id}/retention` | team admin | Set retention: `{"retention_days": 365\|1095\|2555\|null}` (1y/3y/7y/inherit); recomputes `expires_at` for the team's files. |
| GET | `/api/v1/teams/{team_id}/retention` | any team member | Read `{retention_days, effective_days, expires_at_example}`. |
| POST | `/api/v1/admin/retention/sweep` | `ADMIN_API_TOKEN` | Run the retention sweep immediately; returns `{expired, deleted, failed}`. |

Every operation writes a HIPAA audit entry (`storage.upload`,
`storage.download`, `storage.delete`, `storage.expire`,
`storage.decrypt_failed`, `retention.policy.update`) — query them via
`GET /api/v1/audit-logs?action=storage.expire`.

### Encryption at rest

Set `STORAGE_ENCRYPTION=aes256gcm` to encrypt stored files
client-side (per-file random 256-bit DEK wrapped by a KEK derived from
`STORAGE_ENCRYPTION_KEY`, falling back to `HIPAA_MASTER_KEY`). Blobs carry a
versioned `MNAS1` header; tampering or a wrong key raises
`502 storage_decrypt_failed` (never raw ciphertext). The app **fails fast at
startup** when the mode is set without a key. **HIPAA deployments must set
this** — Cloudflare R2 has no customer-managed server-side keys, so
client-side encryption is the only uniform at-rest answer.

### Retention

The default retention is 6 years (`DEFAULT_RETENTION_DAYS=2190`, HIPAA
minimum). A background task in the app lifespan sweeps expired files every
`RETENTION_SWEEP_INTERVAL_SECONDS` (default 86400); expired objects are
deleted from the backend, rows soft-deleted, and `storage.expire` audit
entries written. Trigger manually via the admin sweep endpoint.

```bash
# Upload audio to a meeting (requires a JWT)
curl -X POST http://localhost:8000/api/v1/meetings/<meeting_id>/audio \
  -H "Authorization: Bearer <token>" \
  -F "file=@recording.wav"

# Download it back
curl -OJ http://localhost:8000/api/v1/meetings/<meeting_id>/audio \
  -H "Authorization: Bearer <token>"

# Set a 7-year retention policy for a team
curl -X PUT http://localhost:8000/api/v1/teams/<team_id>/retention \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"retention_days": 2555}'
```

---

## Quick Start (Standard Mode)

```bash
# Install dependencies
uv sync

# Set environment variables
export OPENAI_API_KEY=sk-...
export DATABASE_URL=sqlite+aiosqlite:///./meeting_notes.db
export JWT_SECRET=your-secret-key-change-in-production

# Initialize database
python -c "from meeting_notes_ai.db import init_db; import anyio; anyio.run(init_db)"

# Run the server
uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/healthz
```

## Database Setup

### Local Development (SQLite)

```bash
export DATABASE_URL=sqlite+aiosqlite:///./meeting_notes.db
uv sync
```

The database is auto-created on first run. For Alembic migrations:

```bash
alembic init migrations
alembic revision --autogenerate -m "initial migration"
alembic upgrade head
```

### Production (Railway Postgres)

```bash
export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/meeting_notes
```

Railway auto-provisions Postgres. Set `DATABASE_URL` in the Railway dashboard under Variables. The app calls `init_db()` on startup via lifespan events.

## Authentication

### POST /api/v1/auth/signup

Create a new user account.

**Request body** (JSON):
```json
{
  "email": "user@example.com",
  "password": "secure-password"
}
```

**Response** (201):
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "created_at": "2026-07-28T12:00:00Z"
}
```

### POST /api/v1/auth/login

Authenticate and receive a JWT bearer token (24h expiry).

**Request body** (JSON):
```json
{
  "email": "user@example.com",
  "password": "secure-password"
}
```

**Response** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

Include the token in subsequent requests:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

All team, batch, and webhook endpoints require authentication. Unauthenticated requests return **401 Unauthorized**.

## API

### POST /api/v1/meetings

Upload an audio file for processing.

**Parameters:**
- `file` (UploadFile, required): Audio file (WAV, MP3, MP4, WebM, max 25MB)
- `mode` (str, optional): `general`, `healthcare`, or `legal` (default: `general`)
- `language` (str, optional): ISO language code for transcription
- `patient_id` (str, optional): Patient identifier (healthcare mode)
- `consent_confirmed` (bool, optional): Consent confirmation (healthcare mode)
- `case_number` (str, optional): Case number (legal mode)
- `jurisdiction` (str, optional): Jurisdiction (legal mode)

### Batch Processing

#### POST /api/v1/batches

Upload multiple audio files for batch processing. Requires authentication.

**Request:** Multipart form with up to 10 audio files.

**Response** (201):
```json
{
  "batch_id": "uuid",
  "status": "pending",
  "file_count": 3,
  "created_at": "2026-07-28T12:00:00Z"
}
```

Batch status progresses: `pending` → `processing` → `completed`.

#### GET /api/v1/batches/{batch_id}

Poll batch processing status and retrieve per-file results.

**Response** (200):
```json
{
  "batch_id": "uuid",
  "status": "completed",
  "files": [
    {
      "filename": "meeting1.mp3",
      "status": "completed",
      "transcript": "...",
      "action_items": ["..."],
      "decisions": ["..."],
      "key_points": ["..."]
    },
    {
      "filename": "meeting2.mp3",
      "status": "failed",
      "error": "Unsupported format"
    }
  ],
  "created_at": "2026-07-28T12:00:00Z",
  "completed_at": "2026-07-28T12:05:00Z"
}
```

Failed files do not fail the entire batch — partial failure tolerance.

#### GET /api/v1/batches/{batch_id}/export

Export batch results in one or all formats.

**Query parameters:**
- `format` (str, required): `json`, `markdown`, `pdf`, or `all`

**Response:**
| Format | Content-Type | Body |
|--------|-------------|------|
| `json` | `application/json` | JSON array of all file results |
| `markdown` | `text/markdown` | Markdown document |
| `pdf` | `application/pdf` | PDF (via WeasyPrint) with meeting title, mode, key points, decisions, action items |
| `all` | `application/zip` | ZIP bundle containing JSON + Markdown + PDF per file |

### Team Workspaces

All team endpoints require authentication and appropriate role.

#### POST /api/v1/teams

Create a new team. The creator becomes the admin.

**Request body** (JSON):
```json
{
  "name": "Engineering Team"
}
```

**Response** (201):
```json
{
  "id": "uuid",
  "name": "Engineering Team",
  "role": "admin",
  "created_at": "2026-07-28T12:00:00Z"
}
```

#### GET /api/v1/teams

List teams the authenticated user belongs to.

**Response** (200):
```json
[
  {
    "id": "uuid",
    "name": "Engineering Team",
    "role": "admin",
    "member_count": 4
  }
]
```

#### POST /api/v1/teams/{team_id}/members

Invite a member to a team. Requires `admin` role.

**Request body** (JSON):
```json
{
  "email": "colleague@example.com",
  "role": "member"
}
```

**Roles:** `admin` (manage team, invite/remove members, all meetings), `member` (create and view team meetings), `viewer` (read-only access).

**Response** (201):
```json
{
  "id": "uuid",
  "email": "colleague@example.com",
  "role": "member",
  "status": "invited"
}
```

#### PATCH /api/v1/teams/{team_id}/members/{user_id}

Change a member's role. Requires `admin` role.

**Request body** (JSON):
```json
{
  "role": "viewer"
}
```

### Meeting Sharing

Share meeting summaries via public links with configurable expiration. All sharing endpoints require authentication (except the public view endpoint).

#### POST /api/v1/meetings/{meeting_id}/share

Generate a shareable link for a meeting summary. Requires `admin` or `member` role on the meeting's team (viewers cannot share).

**Request body** (JSON):
```json
{
  "expires_in": "24h"
}
```

| `expires_in` | Behaviour |
|--------------|-----------|
| `"1h"`       | Link expires in 1 hour |
| `"24h"`      | Link expires in 24 hours |
| `"7d"`       | Link expires in 7 days |
| `"never"`    | No expiration (permanent) |
| *(omitted)*  | Defaults to no expiration |

**Response** (201):
```json
{
  "id": "uuid",
  "token": "base64-urlsafe-token",
  "url": "/public/shares/{token}",
  "expires_at": "2026-07-31T12:00:00Z",
  "is_active": true,
  "created_at": "2026-07-30T12:00:00Z"
}
```

#### GET /api/v1/meetings/{meeting_id}/shares

List active (non-revoked) share links for a meeting. Requires authentication and access to the meeting.

**Response** (200):
```json
{
  "shares": [
    {
      "id": "uuid",
      "token": "base64-urlsafe-token",
      "url": "/public/shares/{token}",
      "expires_at": "2026-07-31T12:00:00Z",
      "is_active": true,
      "created_at": "2026-07-30T12:00:00Z"
    }
  ]
}
```

#### DELETE /api/v1/meetings/{meeting_id}/shares/{share_id}

Revoke a share link (sets `is_active` to `false`). The share creator can always revoke; team admins can revoke any share in their team's meeting.

**Response** (204): No content.

#### GET /public/shares/{token}

Public endpoint — view a shared meeting summary without authentication. Returns 404 if the token is invalid, expired, or revoked.

**Response** (200):
```json
{
  "title": "Sprint Planning — Week 30",
  "transcript": "...",
  "action_items": "...",
  "decisions": "...",
  "key_points": "...",
  "mode": "general",
  "metadata": null
}
```

### Webhook Configuration

Webhooks fire automatically when a batch completes processing. Notifications include HMAC-SHA256 payload signing for verification.

#### POST /api/v1/webhooks

Register a webhook URL for a team. Requires authentication.

**Request body** (JSON):
```json
{
  "url": "https://hooks.example.com/batch-complete",
  "team_id": "uuid",
  "events": ["batch.completed"]
}
```

**Response** (201):
```json
{
  "id": "uuid",
  "url": "https://hooks.example.com/batch-complete",
  "secret": "whsec_abc123...",
  "created_at": "2026-07-28T12:00:00Z"
}
```

Save the `secret` — it is shown only once. Use it to verify incoming webhook payloads.

#### GET /api/v1/webhooks

List webhooks for the authenticated user's teams.

#### DELETE /api/v1/webhooks/{webhook_id}

Remove a webhook subscription. Requires `admin` role on the associated team.

#### Webhook Payload Format

On batch completion, a POST request is sent to each registered webhook URL:

```json
{
  "event": "batch.completed",
  "timestamp": "2026-07-28T12:05:00Z",
  "batch_id": "uuid",
  "team_id": "uuid",
  "status": "completed",
  "file_count": 3,
  "summary": {
    "completed": 2,
    "failed": 1,
    "total_duration_seconds": 245
  }
}
```

**Headers:**
```
Content-Type: application/json
X-Webhook-Signature: sha256=abc123...
```

Verify the signature by computing HMAC-SHA256 of the raw request body using your webhook secret.

#### Delivery Guarantees

- Failed deliveries are retried 3 times with exponential backoff (5s → 15s → 30s)
- Timeout: 10 seconds per attempt
- After 3 failures, the webhook is marked as `failing` (no automatic disable)

### GET /healthz

Health check endpoint returning service status.

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "app": {
      "status": "up",
      "latency_ms": 0.0
    }
  }
}
```

## Testing

```bash
.venv/bin/python -m pytest -q
```

Test coverage by release:
- 112 v0.1.0 regression tests (transcription, extraction, export, healthcare/legal modes)
- 163 v0.2.0 tests (DB models, JWT auth, batch processing, team CRUD, webhooks, PDF/ZIP export)
- 70 v0.3.0 tests (share creation, listing, revocation, public access, expiry, access control)
- 298 v0.5.0 HIPAA tests (PHI redaction, audit logging, encryption, BAA template, compliance dashboard, HIPAA config, HIPAA REST routes)
- 111 v0.7.0 storage tests (local/S3 backends, factory, AES-256-GCM encryption, StoredFile model, storage REST API + RBAC, retention sweep, MinIO integration)

> Note: the v0.4.0 rate-limit/API-key test files (`test_ratelimit.py`,
> `test_api_keys.py`, `test_tier_config.py`, `test_middleware.py`,
> `test_app.py`, `test_auth.py`) still fail because their source never landed
> in this repository — they are pre-existing failures, unrelated to HIPAA.

## Deployment

### Railway

1. Push to GitHub repository
2. Create new Railway project from the repo
3. Provision a Postgres plugin (DATABASE_URL auto-injected)
4. Set environment variables:
   - `JWT_SECRET` (required)
   - `OPENAI_API_KEY` (required — used by `/api/v1/meetings` and `/api/v1/transcribe`)
   - `HIPAA_MASTER_KEY` (required for `/api/v1/encryption/rotate-key` and encryption at rest)
   - `STORAGE_ENCRYPTION=aes256gcm` + `STORAGE_ENCRYPTION_KEY` (recommended for HIPAA — encrypts stored audio/transcripts at rest)
   - `STORAGE_BACKEND=s3` + `S3_*` vars when using S3/R2/MinIO (defaults to local filesystem)
5. No manual migration needed — `init_db` runs on startup (Alembic migration `20260801_0002` adds `storage_files` + `teams.retention_days` for existing DBs)

See `railway.toml` for service configuration.

> **v0.6.2 operational-readiness update:** Open `/app` for an accessible upload, processing-status, and review experience. Healthcare meetings now default to PHI redaction and are marked `needs_review`. See [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) and [TEST_RESULTS.md](TEST_RESULTS.md).
