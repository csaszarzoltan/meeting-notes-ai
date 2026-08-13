# MeetingNotesAI 1.7.0

MeetingNotesAI is a privacy-first FastAPI and React workspace that turns uploaded or live conversations into **reviewable evidence, approved notes, accountable actions, and controlled shares**.

`research-findings.md` identified three highest-value requirements: one coherent meeting workflow, source-linked human review, and policy-driven safe execution. Version 1.1.2 closes the independent QA blockers around authentication, tenant isolation, canonical meeting persistence, review/approval, sharing, task queueing, compliance evidence, search, and real audio controls.

## Stack

- FastAPI, Pydantic, async SQLAlchemy, JWT authentication
- React 18, TypeScript, Vite
- pytest, Ruff, coverage, GitHub Actions
- Optional OpenAI transcription/extraction and S3-compatible object storage

## Install and run

```bash
uv sync --frozen
cd frontend && npm ci && npm run build && cd ..
uv run uvicorn meeting_notes_ai.main:app --reload
```

Open `http://127.0.0.1:8000/app`. Create an account through `POST /api/v1/auth/signup` or use an existing account, then sign in through the product shell. Set `OPENAI_API_KEY` for real transcription/extraction and production-grade secrets described in `.env.example` and `docs/HIPAA_MODE.md`. To connect Google Calendar (see [docs/integrations/google-calendar.md](docs/integrations/google-calendar.md)), also set `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, and — if your deployment differs from the default — `GOOGLE_CALENDAR_REDIRECT_URI`; the token encryptor additionally requires `STORAGE_ENCRYPTION_KEY` or `HIPAA_MASTER_KEY`.

## Main user flow

1. Sign in to the private, tenant-scoped workspace.
2. Record live or upload WAV, MP3, MP4, or WebM — or connect Google Calendar and import an upcoming meeting with one click (see [docs/integrations/google-calendar.md](docs/integrations/google-calendar.md)).
3. Select General, Healthcare, or Legal context and review visible privacy settings.
4. The processed result is saved as one canonical meeting.
5. Edit the summary, inspect cited evidence, seek source audio, and approve or reject.
6. Confirm owners and deadlines; configured external adapters receive queued work — confirmed actions sync to Jira, Linear, Asana, or Todoist.
7. Create an expiring share only after approval, inspect access, and revoke immediately when needed.
8. Find prior work through Cmd/Ctrl+K workspace search.

## Google Calendar integration

Connect a Google account through OAuth2, browse upcoming events, and import a meeting in one click to create a tenant-scoped meeting record:

- `POST /api/v1/integrations/google-calendar/auth` — start the OAuth2 flow (calendar.readonly scope, CSRF state token)
- `GET /api/v1/integrations/google-calendar/callback` — exchange the authorization code and store encrypted tokens
- `GET /api/v1/integrations/google-calendar/events` — list the next 7 days of events, marking already-imported ones
- `POST /api/v1/integrations/google-calendar/import/{event_id}` — create a meeting from a calendar event (409 on duplicate import)
- `GET /api/v1/integrations/google-calendar/status` and `DELETE /api/v1/integrations/google-calendar/disconnect` — manage the connection

Tokens are encrypted at rest (AES-256-GCM) and refreshed automatically; expired or revoked tokens surface a re-authorization prompt instead of a raw error. Full setup (Google Cloud Console prerequisites, env vars, user flow, API reference, troubleshooting) is in [docs/integrations/google-calendar.md](docs/integrations/google-calendar.md).

## Project management integrations (Jira, Linear, Asana, Todoist)

Confirm an action's owner and due date, then sync it straight into a project
management tool with **Sync to {provider}** in the Action Center:

- `POST /api/v1/workspace/integrations/{name}/connect` — connect a PM provider with a token (`credentials.token` plus provider-specific `site_url` / `email` / `default_project`); validates the credential and stores it encrypted
- `POST /api/v1/workspace/actions/{action_id}/queue` — create a real task in the provider, storing the provider's native `external_id` and a `external_url` link (`sync_state: "task-synced"`); idempotent, safe to retry
- `GET /api/v1/workspace/integrations` — list the catalog (PM providers expose `account_email`, `account_url`, `token_expires_at`)

Token-based credentials are stored per-user, encrypted at rest with AES-256-GCM
(`STORAGE_ENCRYPTION_KEY` / `HIPAA_MASTER_KEY`); no per-provider env vars are
required. Full setup (creating each provider's token, scopes, connect/sync
contracts, error table, troubleshooting) is in
[docs/integrations.md](docs/integrations.md).

## Security model

All `/api/v1/workspace/*` routes require the existing bearer JWT and scope local workspace state by authenticated user ID. Public share resolution exposes only approved summary content and enforces token state and expiry. The local JSON adapter is intended for single-process development; production deployments should replace it with the existing SQL repository boundary or another transactional tenant store.

## Verification

```bash
uv run ruff check .
uv run pytest -q -n 0
cd frontend && npm run typecheck && npm run build
```

See `TEST_RESULTS.md`, `review-findings.md`, `FEATURES-DONE.md`, and `docs/WORKSPACE_API.md` for verified details. The source archive intentionally excludes `frontend/dist`; the documented build creates it reproducibly.

## Trusted meeting records
Version 1.4.0 introduces evidence validation, atomic speaker correction rules, strict review-policy evaluation, tenant-scoped artifact lineage, honest external-remediation outcomes, and tamper-evident signed audit exports. The Compliance Center exposes Overview, Audit exports, and Data policies tabs. AI output remains a draft until the configured approval criteria are met.

### Verification
Run `uv run pytest -q -n 0`, `uv run ruff check .`, and in `frontend/`, run `npm ci`, `npm run typecheck`, and `npm run build`.

## Trusted-record and governance APIs

Version 1.4.1 adds persistent trusted-record endpoints under `/api/v1/trusted` for record retrieval, optimistic claim edits, speaker mapping, decisions, publishing, and activity. Governance endpoints under `/api/v1/governance` provide lineage, deletion jobs and receipts, signed audit exports, and versioned policies. Claim edits require `If-Match`; strict healthcare/legal publishing fails closed when evidence or approval is missing. Set `AUDIT_EXPORT_SIGNING_KEY` to at least 32 bytes before downloading receipts or exports.

## Trusted workflow enforcement

Version 1.4.2 adds snapshot gating to persistent share creation, quarantines meetings when deletion is requested, and moves destructive work into an idempotent deletion worker service. The meeting review workspace now includes Activity and Data tabs backed by trusted/governance APIs. Deletion receipts use canonical HMAC signatures and detect content modification. Set `AUDIT_EXPORT_SIGNING_KEY` to at least 32 bytes before worker execution when signed receipts are required.

## Trusted workflow completion foundations
Version 1.5.0 connects claim-level approve/reject/publish actions to the trusted-record API, displays immutable snapshots, adds a persistent idempotent ArtifactRegistry, persists provider preflight decisions, and provides a standalone governance worker:

```bash
python -m meeting_notes_ai.workers.governance --once
python -m meeting_notes_ai.workers.governance --interval 5
```

The worker claims pending deletion jobs, skips terminal artifact results after restart, preserves external remediation, revokes shares, and creates signed receipts when `AUDIT_EXPORT_SIGNING_KEY` contains at least 32 bytes.

## Complete trusted review interaction

Version 1.6.0 completes the central claim-review interaction: users can edit claim text, select transcript segments, add or remove evidence, approve or reject each claim, map speakers, see `Reapproval required`, publish immutable snapshots, and resolve optimistic-concurrency conflicts with `Keep current`, `Use mine as new revision`, or `Cancel`.

Published snapshots and snapshot-backed shares are registered in the artifact registry for team meetings. Strict healthcare and legal meetings continue to fail closed when no eligible snapshot exists.
