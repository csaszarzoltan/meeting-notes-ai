# MeetingNotesAI v0.2.0 — Implementation Plan (SOP)

> **Version:** 0.2.0 (minor bump from 0.1.0)
> **Branch:** `features/batch-processing-team-collab`
> **Parent:** v0.1.0 deployed to Railway (no DB, no auth, single-file processing)

---

## 0. Pre-requisites

Before coding, install new dependencies:
```
uv add sqlalchemy[asyncio] alembic python-jose[cryptography] passlib[bcrypt]
uv add pydantic[email]
uv add --dev pytest-asyncio aiosqlite
```

---

## 1. RED Phase — Run pre-tester tests

```
.venv/bin/python -m pytest tests/test_db_models.py tests/test_auth.py tests/test_batches.py \
    tests/test_teams.py tests/test_webhooks.py tests/test_export_pdf.py \
    tests/test_app_v2.py -q --tb=short
```

**Expected:** Interface tests pass (264), app wiring tests fail (10), behavioral stubs for new code also fail with NotImplementedError. The 10 app-wiring failures are the developer's checklist.

---

## 2. GREEN Phase — Implement in Order (P0 → P1 → P2)

### P0 — Core Infrastructure (must be done first)

#### 2.1 Database models (stubs exist)
**Files to create:**
- `src/meeting_notes_ai/db/models.py` — FULLY DEFINED ✅ (SQLAlchemy ORM models)
- `src/meeting_notes_ai/db/engine.py` — implement `create_db_engine`, `create_session_factory`, `init_db`, `close_db`
- `src/meeting_notes_ai/db/session.py` — implement `get_db_session` FastAPI dependency
- Alembic initial migration

**Key details:**
- Use `sqlalchemy.ext.asyncio` (AsyncEngine, AsyncSession, async_sessionmaker)
- SQLite+aiosqlite for dev, asyncpg for prod (Railway Postgres)
- Models: User, Team, TeamMember, Meeting, BatchJob, BatchFileResult, WebhookSubscription
- All models already defined in stubs — implement the engine/session layer

**Test gate:** `test_db_models.py` interface tests must pass, behavioral tests transition from NotImplementedError → real results

#### 2.2 Authentication (stubs exist)
**Files to create:**
- `src/meeting_notes_ai/auth.py` — implement all stub functions

**Key details:**
- JWT via `python-jose` (create_access_token / decode_access_token)
- Password hashing via `passlib[bcrypt]` (hash_password / verify_password)
- FastAPI dependency `get_current_user` — extracts Bearer token from Authorization header
- `require_team_role` — checks user's role in a team
- Routes: POST /api/v1/auth/signup, POST /api/v1/auth/login, GET /api/v1/auth/me

**Test gate:** `test_auth.py` interface tests pass, behavioral tests succeed

#### 2.3 Batch processing (stubs exist)
**Files to create:**
- `src/meeting_notes_ai/routes/batches.py` — implement route handlers

**Key details:**
- POST /api/v1/batches — accepts multipart with up to 10 files, creates BatchJob
- Process files sequentially via existing pipeline (transcribe → extract → mode)
- GET /api/v1/batches/{batch_id} — returns status + per-file BatchFileResult results
- Use existing TranscriptionService, ExtractionService, HealthcareService, LegalService
- Track status per file so partial failures don't fail the whole batch

**Test gate:** `test_batches.py` interface tests pass, behavioral tests succeed

### P1 — Team Features

#### 2.4 Team workspace CRUD (stubs exist)
**Files to create:**
- `src/meeting_notes_ai/routes/teams.py` — implement all route handlers

**Key details:**
- Routes: POST (create), GET (list), GET /{team_id} (detail), POST /{team_id}/members (invite), PATCH /{team_id}/members/{member_id} (role change), DELETE /{team_id}/members/{member_id} (remove)
- Only admin can change roles / remove members
- Member roles: admin, member, viewer (viewer can only view meetings)

**Test gate:** `test_teams.py` interface tests pass, behavioral tests succeed

#### 2.5 Webhook notifications (stubs exist)
**Files to create:**
- `src/meeting_notes_ai/services/webhooks.py` — implement service functions
- `src/meeting_notes_ai/routes/webhooks.py` — implement route handlers

**Key details:**
- Service: register_webhook, list_webhooks, delete_webhook, fire_webhook, fire_batch_completed_webhooks, sign_payload
- Webhook fire uses httpx async POST with retry: 3 attempts (5s, 15s, 30s backoff)
- Payload signing with HMAC-SHA256 (sign_payload)
- Routes: POST /api/v1/webhooks (register), GET /api/v1/webhooks (list), DELETE /api/v1/webhooks/{webhook_id} (delete)

**Test gate:** `test_webhooks.py` interface tests pass, behavioral tests succeed

### P2 — Export & Polish

#### 2.6 Multi-format batch export
**Files to modify:**
- `src/meeting_notes_ai/services/export.py` — implement export_pdf and export_batch_zip

**Key details:**
- PDF via weasyprint: convert meeting Markdown to HTML, then to PDF bytes
- export_batch_zip: collect all meeting results in all formats, zip into bytes
- GET /api/v1/batches/{batch_id}/export?format=json|markdown|pdf|all (stub in batches.py)

**Test gate:** `test_export_pdf.py` interface tests pass, behavioral tests succeed

#### 2.7 Wire app routers
**File to modify:**
- `src/meeting_notes_ai/main.py` — add new routers

```python
from meeting_notes_ai import auth
from meeting_notes_ai.routes import batches, teams, webhooks
app.include_router(auth.router)
app.include_router(batches.router)
app.include_router(teams.router)
app.include_router(webhooks.router)
```

**Test gate:** `test_app_v2.py` — ALL 10 tests must pass after wiring

---

## 3. Full test suite verification

After implementing all P0+P1+P2:
```
.venv/bin/python -m pytest tests/ -q --tb=short
```

**Expected:** 374+ passing (264 original interface + new passing behavioral + 112 existing)

---

## 4. Implementation Order Summary

```
1. db/engine.py + db/session.py     (fast, enables everything else)
2. auth.py                           (required by all protected routes)
3. routes/batches.py                 (core P0 feature)
4. routes/teams.py                   (P1 team features)
5. services/webhooks.py + routes/    (P1 webhook)
6. services/export.py (PDF+ZIP)      (P2 export improvements)
7. main.py (wire all routers)        (final glue)
```

---

## 5. Key Files Reference

| Path | Purpose |
|------|---------|
| `src/meeting_notes_ai/db/__init__.py` | DB package marker |
| `src/meeting_notes_ai/db/models.py` | ORM models ✅ defined |
| `src/meeting_notes_ai/db/engine.py` | Async engine factory ⚠️ implement |
| `src/meeting_notes_ai/db/session.py` | FastAPI session dep ⚠️ implement |
| `src/meeting_notes_ai/auth.py` | JWT auth + routes ⚠️ implement |
| `src/meeting_notes_ai/routes/batches.py` | Batch endpoints ⚠️ implement |
| `src/meeting_notes_ai/routes/teams.py` | Team CRUD ⚠️ implement |
| `src/meeting_notes_ai/services/webhooks.py` | Webhook service ⚠️ implement |
| `src/meeting_notes_ai/routes/webhooks.py` | Webhook routes ⚠️ implement |
| `src/meeting_notes_ai/services/export.py` | PDF+ZIP export ⚠️ implement stubs |
| `src/meeting_notes_ai/main.py` | Wire routers ⚠️ update |

✅ = already defined in stubs
⚠️ = needs implementation

---

## 6. Dependencies added

```
sqlalchemy[asyncio]>=2.0
alembic>=1.13
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
pydantic[email]       # already in project
pytest-asyncio>=0.23  # dev only
aiosqlite             # dev only
asyncpg               # prod (Railway)
weasyprint            # PDF export
```
