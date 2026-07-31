# MeetingNotesAI

Micro-SaaS for meeting transcription and structured notes.

## Features

- **Transcription**: Upload audio files for transcription via OpenAI Whisper API
- **Extraction**: Automatically extract action items, decisions, and key points using LLM
- **Mode-specific processing**:
  - **General**: Standard meeting notes
  - **Healthcare**: SOAP notes with HIPAA compliance markers
  - **Legal**: Deposition summaries with objection tracking
- **Multi-format Export**: JSON, Markdown, PDF, and ZIP batch download
- **Batch Processing**: Upload up to 10 audio files per batch with per-file status tracking
- **Team Workspaces**: Multi-user teams with role-based access (admin/member/viewer)
- **Webhook Notifications**: Automatic HTTP callbacks on batch completion with HMAC-SHA256 signing
- **Meeting Sharing**: Generate shareable links with configurable expiration (1h, 24h, 7d, never). Revoke links or let them auto-expire. Public endpoint serves meeting summaries without authentication.
- **JWT Authentication**: Bearer token signup/login with 24h expiry
- **Database**: Async SQLAlchemy with Railway Postgres (Alembic-ready)
- **SSRF Protection**: Built-in URL validation to prevent server-side request forgery

## HIPAA Compliance Mode (v0.4.0+)

MeetingNotesAI supports **HIPAA compliance mode** for healthcare meeting transcription and PHI (Protected Health Information) processing. Enable it by setting the required environment variables.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HIPAA_MASTER_KEY` | — | Master Encryption Key (32-byte hex or base64) |
| `HIPAA_PHI_PATTERNS_PATH` | `hipaa/phi_patterns.json` | Path to PHI patterns JSON |
| `HIPAA_AUDIT_LOG_DIR` | `data/audit_logs/` | Audit log storage directory |
| `HIPAA_AUDIT_RETENTION_DAYS` | `2190` | Log retention (6 years) |
| `HIPAA_ENCRYPTION_ENABLED` | `true` | Enable/disable encryption at rest |
| `HIPAA_LLM_VALIDATION_ENABLED` | `true` | Enable/disable LLM PHI validation pass |
| `HIPAA_BAA_DEFAULT_DAYS` | `365` | Default BAA effective period in days |

### Quick Start — Enabling HIPAA Mode

```bash
# Install dependencies (includes cryptography, weasyprint)
uv sync

# Set required HIPAA environment variables
export HIPAA_MASTER_KEY=$(openssl rand -hex 32)
export DATABASE_URL=sqlite+aiosqlite:///./meeting_notes.db
export JWT_SECRET=your-secret-key-change-in-production
export OPENAI_API_KEY=sk-...

# Initialize database
python -c "from meeting_notes_ai.db import init_db; import anyio; anyio.run(init_db)"

# Run the server (HIPAA features auto-detect env vars on startup)
uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port 8000

# Verify HIPAA endpoints
curl http://localhost:8000/api/v1/hipaa/scan
```

HIPAA mode activates automatically when the `HIPAA_MASTER_KEY` environment variable is set. The `/api/v1/hipaa/*` endpoints become available, including PHI redaction, audit logging, encryption management, BAA lifecycle, and the compliance dashboard.

### HIPAA Features

- **PHI Redaction** — Regex-based detection of 18 HIPAA identifier categories with optional LLM validation pass for higher accuracy
- **Audit Logging** — Append-only JSONL audit trail with 6-year retention for all PHI access and processing events
- **Encryption at Rest** — AES-256-GCM envelope encryption with per-tenant data encryption keys
- **BAA Management** — Business Associate Agreement template generation, PDF export, and immutable storage
- **Compliance Dashboard** — Real-time metrics via Chart.js HTML dashboard and REST API

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/hipaa/scan` | Scan text for PHI matches |
| POST | `/api/v1/hipaa/redact` | Redact PHI from text |
| GET | `/api/v1/hipaa/patterns` | List active PHI patterns |
| GET | `/api/v1/hipaa/audit-log` | Query audit log entries |
| GET | `/api/v1/hipaa/audit-log/stats` | Audit log statistics |
| POST | `/api/v1/hipaa/encryption/keys` | Create encryption key for tenant |
| GET | `/api/v1/hipaa/encryption/keys/{tenant_id}` | Get tenant encryption key info |
| POST | `/api/v1/hipaa/encryption/rotate` | Rotate encryption keys |
| POST | `/api/v1/hipaa/baa/generate` | Generate BAA from template |
| GET | `/api/v1/hipaa/baa/{id}` | Get agreement details |
| GET | `/api/v1/hipaa/baa/{id}/export` | Export BAA as PDF/Markdown |
| GET | `/api/v1/hipaa/compliance/summary` | Aggregated compliance metrics |
| GET | `/api/v1/hipaa/compliance/phi-stats` | PHI detection statistics |
| GET | `/api/v1/hipaa/compliance/activity` | Recent audit entries |
| GET | `/api/v1/hipaa/compliance` | HTML compliance dashboard |

See [docs/HIPAA_MODE.md](docs/HIPAA_MODE.md) for the full HIPAA mode documentation.

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
  "version": "0.3.0",
  "database": "connected"
}
```

## Testing

```bash
.venv/bin/python -m pytest -q
```

345 tests covering:
- 112 v0.1.0 regression tests (transcription, extraction, export, healthcare/legal modes)
- 163 v0.2.0 tests (DB models, JWT auth, batch processing, team CRUD, webhooks, PDF/ZIP export)
- 70 v0.3.0 tests (share creation, listing, revocation, public access, expiry, access control)

## Deployment

### Railway

1. Push to GitHub repository
2. Create new Railway project from the repo
3. Provision a Postgres plugin (DATABASE_URL auto-injected)
4. Set environment variables:
   - `JWT_SECRET` (required)
   - `OPENAI_API_KEY` (required)
5. No manual migration needed — `init_db` runs on startup

See `railway.toml` for service configuration.
