# Changelog

All notable changes to MeetingNotesAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.2] — 2026-08-06

### Features
- Google Calendar OAuth2 integration — connect Google Calendar (`calendar.readonly` scope, CSRF state tokens, AES-256-GCM encrypted tokens at rest), auto-detect upcoming meetings, and one-click import as meeting records. The router at `/api/v1/integrations/google-calendar` exposes `auth` / `callback` / `events` / `import/{event_id}` / `status` / `disconnect`; the full guide is in `docs/integrations/google-calendar.md`.

### Fixed
- Google Calendar import: uniqueness is now per (user, event); importing a shared-calendar event already imported by another user returns 409 instead of an unhandled 500. Added a composite unique index via migration 20260806_0005.
- Google Calendar events endpoint maps token expiry to 401 and upstream API failures to 502 (previously raw 500s).
- Google Calendar import endpoint distinguishes token expiry (401) from a missing event (404) without echoing raw Google API error text.
- OAuth state rows are purged once used or expired instead of accumulating forever.
- Removed the dead `calendar_connected` frontend query-param handling; the OAuth flow completes via the status poll.

---

## [1.1.0] — 2026-08-05

### Modern GUI redesign
- Reframed Home around the next best action, review queue, personal execution, workspace activity, and guided onboarding.
- Added a keyboard-first global command palette with Cmd/Ctrl+K.
- Rebuilt meeting review as an evidence-first studio with lifecycle guidance, autosave feedback, version context, confidence states, source navigation, and change comparison.
- Added dedicated mobile Notes, Transcript, Evidence, and Actions tabs plus sticky playback and approval controls.
- Added reusable loading, partial-success, offline, permission-denied, retry, empty, and skeleton states.
- Added compact density and dark theme controls while preserving WCAG-oriented focus, motion, and touch-target behavior.

### Verification
- Added modern GUI source contracts and ran the complete regression suite.

---

## [1.0.1] — 2026-08-05

### Features

- Added a persistent product workspace API for meetings, review versions, actions, connectors, settings, compliance, batches, insights, and policy-gated shares.
- Wired priority React screens to real API state instead of component-local demo arrays.
- Added durable approval/rejection, source evidence, action synchronization references, cited search, and immediate share revocation.

### Fixes

- Added Hatchling src-layout packaging so the documented Uvicorn command works after `uv sync --frozen`.
- Gated MinIO tests behind `RUN_S3_INTEGRATION=1`, stabilized the rate-limit assertion, and made frontend assets part of release verification.
- Removed unsupported sharing claims and fabricated live-transcript/intelligence content.
- Changed the legacy compliance token cache from localStorage to sessionStorage.
- Ignored runtime databases and workspace state, and made the whole repository Ruff-clean.

### Tests

- Added real temporary-file I/O and FastAPI integration tests for all persisted workspace operations.
- Replaced keyword-presence GUI tests with API-wiring and anti-facade contracts.

### Docs

- Corrected README, API documentation, and `FEATURES-DONE.md` to describe only implemented behavior and connector boundaries.

---

## [1.0.0] — 2026-08-05

### Features

- Completed guided capture across live, upload, calendar, and in-person modes with templates, consent, retention, and a visible privacy data path.
- Added a three-column live workspace with recording health, speaker-confidence correction, bookmarks, and contextual intelligence.
- Added an eight-stage processing timeline with preserved-work messaging and stage-level retry UX.
- Added Action Center task confirmation, Safe Sharing recipient preview, cited Insights, issue-first Compliance, batch recovery, integrations, governed settings, and mobile navigation.

### Fixes

- Replaced priority-area placeholders with responsive workflow surfaces.
- Embedded the durable processing timeline into the real upload flow.
- Preserved 44px mobile targets, keyboard focus, reduced motion, and non-color status communication.

### Tests

- Added RED-to-GREEN contracts in `tests/test_complete_gui_v10.py`.
- Verified the full Python suite, TypeScript typecheck, and production Vite build.

### Docs

- Updated README and `FEATURES-DONE.md` and added `docs/GUI_SPECIFICATION.md`.

---

## [0.8.0] — 2026-08-03

### Added

#### Live Transcription Backend (`/api/v1/meetings/live`)

Real-time streaming transcription: WebSocket sessions, streaming STT, and
live action-item extraction at finalize.

- **WebSocket live session** — `WS /api/v1/meetings/live` (JWT-authenticated,
  meeting/team-workspace scoped) accepts streaming audio chunks and emits
  partial transcripts over the socket with monotonic sequence + timestamps.
- **Session persistence** — `LiveSession` state persisted to the
  `live_sessions` table (Alembic migration `20260803_0003_live_sessions`),
  survives disconnect and is resumable; finalize writes the full transcript
  through the existing transcription pipeline and creates the meeting record
  with summary, decisions, and action items.
- **Streaming STT** — raw 16 kHz PCM is framed as WAV before Whisper
  (Whisper rejects headerless PCM); WebM/Opus passed through.
- **REST fallback** — `POST /api/v1/meetings/live/upload` accepts a full
  audio file and returns the same transcript shape for non-streaming clients
  (401/415/413/429 mapped).
- **Rate limiting + retention** — per-user `TokenBucketRateLimiter` on
  ingest/finalize/upload; team HIPAA retention policy carried through to
  live sessions.
- **Session start** — `POST /api/v1/meetings/live/start` creates a draft
  meeting and returns the room/meeting scoped session.

#### Live Transcription UI (`/app/live`)

Component-based live-transcription view for the B2B dashboard, built with
React + TypeScript + Vite (`frontend/`) and served by
`routes/product_app.py`.

- **Connect button + microphone wiring** — `getUserMedia` → `MediaRecorder`
  (`audio/webm;codecs=opus`) → binary WebM chunks over the live WebSocket.
- **Streaming transcript panel** — partial updates rendered in sequence
  order with `aria-live="polite"`, auto-scrolling as new partials arrive.
- **Finalize action** — sends the `{"type":"finalize"}` control frame and
  renders the finalized transcript, summary, decisions, and a visible
  action-item list.
- **Auth + session flow** — login via `/api/v1/auth/login` (JWT kept in
  `sessionStorage`), draft meeting via the new
  `POST /api/v1/meetings/live/start` endpoint, then WS connect.
- **Security** — the live page carries its own CSP
  (`connect-src 'self' ws: wss:`) and `Permissions-Policy:
  microphone=(self)`; the security middleware no longer clobbers a
  route-provided Permissions-Policy, so every other page keeps the strict
  camera/mic/geolocation lockdown.
- **Docs + examples** — `docs/LIVE_TRANSCRIPTION.md` (WS contract),
  `examples/live_transcription_client.py` (runnable WS client),
  `examples/live_demo_server.py` (dev server with a fake AI seam, no
  `OPENAI_API_KEY` needed).

### Fixed

- **Live view Authorization header** — repaired the mangled `Authorization`
  header in the live view hook so the WebSocket connect carries a correct
  `Bearer` JWT.
- **Real-mic streaming crash** — chunk serialization no longer UTF-8-decodes
  binary WebM/Opus audio (`_chunk_to_json` now base64-encodes `data` first),
  so real microphone streams stop crashing with `UnicodeDecodeError`; the
  live view also surfaces an in-flight WebSocket close as a visible error
  instead of hanging on "Live — recording".
- **Version-drift assertions** — `tests/test_app.py` now asserts against the
  package `__version__` constant instead of a hardcoded `0.6.2`, eliminating
  the pre-existing 3-failure baseline.

### Tests

- **TDD RED contract** — 71 pre-written tests
  (`tests/test_live_session.py` 46 + `tests/test_live_transcription.py` 25)
  covering the WebSocket session lifecycle, team scoping, finalize
  persistence, and the REST fallback endpoint.
- **UI tests** — `tests/test_live_ui.py` (13 tests) for the `/app/live` view.
- **Full suite at release** — 1026 passed / 0 failed / 18 xfailed (version-drift
  assertions fixed; flake-watched upload tests deterministic).

### Docs

- **README + docs/LIVE_TRANSCRIPTION.md** — live transcription API reference:
  WS contract, REST fallback `POST /api/v1/meetings/live/upload`, rate
  limiting, and the demo-server quick start.

## [0.7.0] — 2026-08-01

### Added

#### Secure File Storage (`meeting_notes_ai.storage`)

Durable audio/transcript storage with a vendor-agnostic object-storage
layer, DB-persisted metadata, RBAC-protected download endpoints, a HIPAA
retention engine with audit logging, and optional AES-256-GCM encryption
at rest.

- **Storage abstraction** — `ObjectStorageBackend` protocol (put/get/
  delete/exists/list) with two backends: `LocalStorageBackend` (traversal-
  safe, `0600` perms, dev/quick-tests) and `S3StorageBackend` (aiobotocore;
  AWS S3, Cloudflare R2 and MinIO via `S3_ENDPOINT_URL` + path-style).
  `get_storage_backend()` factory selects by `STORAGE_BACKEND` env.
- **DB model** — `StoredFile` (`storage_files` table: meeting/user FKs,
  kind, object_key, bucket, size, plaintext SHA-256, content type,
  encryption mode, `expires_at`, soft-delete `deleted_at`) plus
  `StorageFileKind` / `StorageEncryption` enums and `Team.retention_days`
  (nullable). Alembic migration `20260801_0002` (non-destructive, tested
  against a v0.6.2 DB).
- **Storage REST API** (`routes/storage.py`, fully authenticated) —
  POST/GET/DELETE audio per meeting, GET transcript as `.txt`; MIME
  allowlist + 25 MB streaming cap with SHA-256; duplicate → 409,
  oversize → 413, bad MIME → 415; meeting access via the sharing router's
  `_verify_meeting_access` RBAC (viewers read-only).
- **Encryption at rest** (`storage/encryption.py`) — `FileEncryptor`:
  AES-256-GCM, per-file random DEK wrapped by a KEK derived from
  `STORAGE_ENCRYPTION_KEY` (fallback `HIPAA_MASTER_KEY`); versioned
  `MNAS1` blob header; tamper/wrong key → 502 `storage_decrypt_failed` +
  `storage.decrypt_failed` audit; startup fail-fast without a key.
- **HIPAA retention** (`storage/retention.py`) — `RetentionPolicy`
  (1y/3y/7y/inherit, 6-year default), `sweep_expired()` deleting expired
  objects + soft-deleting rows + `storage.expire` audit entries, asyncio
  background sweep in the app lifespan
  (`RETENTION_SWEEP_INTERVAL_SECONDS`), and a manual admin sweep endpoint
  (ADMIN_API_TOKEN gate).
- **Retention policy API** — PUT/GET per team (`retention_days` 365/1095/
  2555/null), recomputes `expires_at` for the team's stored files, audits
  `retention.policy.update`.
- **Audit integration** — all storage operations reuse
  `meeting_notes_ai.hipaa.audit_logger.AuditLogger`
  (`storage.upload/download/delete/expire/decrypt_failed`), queryable via
  the existing audit-logs endpoint.
- **Dev infra** — `docker-compose.dev.yml` starts MinIO (ports 9000/9001);
  `tests/test_storage_s3_integration.py` (marked `integration`) runs
  against real MinIO, skipping with a clear message when unreachable.

### Changed

- `Settings` gains storage/retention env vars (`STORAGE_BACKEND`,
  `STORAGE_LOCAL_DIR`, `S3_*`, `STORAGE_ENCRYPTION[_KEY]`,
  `DEFAULT_RETENTION_DAYS`, `RETENTION_SWEEP_INTERVAL_SECONDS`); see
  `.env.example`.

---

### Added

- **HIPAA Compliance Library** — `meeting_notes_ai.hipaa` package with five
  feature areas for healthcare meeting transcription and PHI processing.

#### PHI Redaction (`hipaa.phi_patterns`, `hipaa.redactor`)
- `PHIRedactor` — regex-based scan/redact with built-in patterns for SSN, DOB,
  phone, email, MRN, and patient/provider names (plus generic capitalized name
  pairs with false-positive filtering)
- Redaction modes: `mask` (`[REDACTED]`), `hash` (SHA-256 prefix),
  `truncate`, `annotate` (`[PHI:<len>]`)
- Runtime custom patterns (`add_custom_pattern`), cumulative stats
  (`get_stats`), hot-reloadable patterns JSON (`reload_patterns`)
- `PHIMatch`, `PHIRedactionResult` dataclasses; `hipaa.redactor` re-exports
  for backward compatibility

#### Append-Only Audit Logging (`hipaa.audit_logger`)
- `AuditLogger` + `AuditEntry` — JSONL append-only trail with mandatory fields
  (timestamp, actor, action, resource) validated before write
- Query with filters, aggregate stats (`get_stats`), manual rotation
  (`rotate`), date-range export (`export_range`)
- 6-year default retention (`audit_log_retention_days = 365 * 6`)

#### AES-256 Encryption at Rest (`hipaa.encryption`)
- `EncryptionService` — envelope encryption: master KEK (SHA-256 of
  `HIPAA_MASTER_KEY` env var) wrapping per-tenant AES-256-GCM DEKs
- Field-level (`encrypt_field`/`decrypt_field`) and document-level
  (`encrypt_document`/`decrypt_document`) encryption
- Master key rotation (`rotate_master_key`) re-wraps all DEKs; key metadata
  (`get_key_info`) never exposes plaintext keys
- Exception hierarchy: `EncryptionError`, `DecryptionError`,
  `KeyNotFoundError`

#### BAA Template & Management (`hipaa.baa`)
- `BAAService` — Jinja2 BAA template with all HIPAA §164.504(e) required
  clauses (permitted uses, safeguards, breach notification, minimum
  necessary, term/termination, return-or-destruction of PHI within 30 days)
- Template generation (`generate_template`), immutable agreement storage
  (`store_agreement`/`get_agreement`/`list_agreements`), PDF export via
  fpdf2 (`generate_pdf` — no weasyprint dependency)

#### Compliance Dashboard Data (`hipaa.dashboard`)
- `ComplianceService` — aggregates audit, encryption, BAA, and PHI stats
  into `ComplianceSummary` (compliance score 0.0–1.0), `PHIStats`
  (chart-ready category/risk breakdown), and recent activity
- `hipaa.middleware` — FastAPI dependencies (`get_phi_redactor`,
  `get_audit_logger`, `get_encryption_service`) as process-wide singletons

#### HIPAA REST Endpoints (`routes/hipaa.py`)

All HIPAA features are now wired into the FastAPI app (registered in
`main.py`). Data endpoints require a Bearer JWT (the standard
`get_current_user` dependency); `GET /api/v1/compliance/dashboard/html`
serves the Chart.js dashboard page unauthenticated.

- `POST /api/v1/transcribe` — multipart audio upload with optional
  `language` and `phi_redaction` (bool); returns `{text, language,
  duration_seconds, segments[], phi_redacted, redaction_matches}`; requires
  `OPENAI_API_KEY` (Whisper API); writes an audit entry (`action=transcribe`)
- `GET /api/v1/audit-logs` — filterable audit query (`actor`, `action`,
  `resource`; `limit` 1–1000, default 100), newest first
- `GET /api/v1/audit-logs/stats` — aggregate stats (optional `since` ISO)
- `GET /api/v1/audit-logs/export` — JSONL attachment for an ISO date range
  (`start`, `end` required)
- `POST /api/v1/encryption/rotate-key` — body `{new_master_key}`; re-wraps
  all tenant DEKs; requires `HIPAA_MASTER_KEY` (503 when missing)
- `POST /api/v1/compliance/baa/generate` — body `{org_name, ba_name,
  signed_by}`; stores a HIPAA §164.504(e) agreement immutably, returns the
  rendered markdown
- `GET /api/v1/compliance/dashboard` — combined `{summary, phi_stats,
  activity}`
- `GET /api/v1/compliance/dashboard/summary` — compliance summary card
- `GET /api/v1/compliance/dashboard/phi-stats` — PHI detection statistics
- `GET /api/v1/compliance/dashboard/activity` — recent audit activity
  (`limit` 1–500, default 50)
- `GET /api/v1/compliance/dashboard/html` — serves
  `templates/dashboard.html.jinja` (Chart.js page fetching the three data
  endpoints above)

### Changed

- Version bumped `0.4.0` → `0.5.0`
- `README.md` — HIPAA section rewritten to document the library API and the
  wired REST endpoints (endpoint table, curl examples, auth/env requirements);
  added badges, healthcare-mode getting started, examples links, verified
  config table
- `docs/HIPAA_MODE.md` — rewritten from TODO scaffolding to a full guide
  (PHI redaction config, audit log interpretation, encryption key
  management, BAA usage, dashboard interpretation, REST API reference with
  request/response examples, config reference, troubleshooting, compliance
  checklist)
- `examples/` — new runnable scripts: `hipaa_phi_redaction.py`,
  `hipaa_audit_logs.py`, `hipaa_rotate_key.py`, `hipaa_baa_generate.py`,
  `hipaa_compliance_dashboard.py` (library API) and
  `hipaa_rest_endpoints.py` (full REST surface via TestClient; all verified
  with the repo venv)
- `CHANGELOG.md` — v0.4.0 entry corrected: it previously claimed REST
  endpoints that were never implemented; HIPAA features ship as a library
  plus a wired REST surface in this release

### Fixed

- `PHIRedactor.scan()` — the regex pattern set (including the generic
  capitalized-name pattern) is compiled once at load/reconfigure time;
  scan() no longer recompiles patterns on every call
- `scan()` now enforces `HIPAAConfig.scan_timeout_ms` (default 100 ms):
  a scan past the budget raises `PHIScanTimeoutError` and aborts fast
  instead of hanging the request path (`scan_timeout_ms <= 0` disables
  the guard)
- `_recompile()` rejects empty and zero-width regex patterns from the
  patterns JSON (they would match at every position); scan() additionally
  skips zero-width matches at runtime
- `BAAService` — signed agreements now persist to a file-backed store
  (0600 + atomic writes) when `store_path` (or a `db_factory` returning
  one) is configured; the REST route and example persist to
  `~/.meeting-notes-ai/baa_agreements.json`, so agreements survive
  restarts
- `BAAService.generate_template()` — Jinja2 environment is now a
  `SandboxedEnvironment` with `autoescape=True`, so user-supplied
  `org_name`/`ba_name`/`effective_date` values are escaped and template
  attribute escapes raise `SecurityError`
- Removed dead `BAATemplate`/`BAAgreement` SQLAlchemy models from
  `db/models.py` (nothing referenced them; BAA data is file-backed)

### Breaking changes

- **The canonical HIPAA paths are `/api/v1/transcribe`, `/api/v1/audit-logs*`,
  `/api/v1/encryption/rotate-key`, and `/api/v1/compliance/*`.** The
  analysis-brief `hipaa/*` REST paths from the v0.4.0 changelog entry
  (scan/redact/audit-log/encryption/baa/compliance) were never implemented
  and are not part of v0.5.0.
- `POST /api/v1/meetings` does **not** redact PHI automatically — use
  `POST /api/v1/transcribe` with `phi_redaction=true`, or the library API.
- `HIPAAConfig.load()` returns defaults — env-var overrides are not
  implemented; configure via the dataclass constructor.
- LLM PHI validation (`hipaa.llm_validator`) is a stub in this release
  (confirms regex matches, never calls an external LLM).
- `BAAService()` with no `store_path`/`db_factory` stays in-memory —
  agreements vanish on restart; pass a store path to persist. The REST
  route and example persist to `~/.meeting-notes-ai/baa_agreements.json`
  (0600 + atomic writes, mirroring `EncryptionService`'s `key_store.json`)

### Tests

- 355 HIPAA tests passing across 9 files: `test_phi_redaction` (56),
  `test_audit_logging` (42), `test_encryption` (40), `test_baa_template`
  (23), `test_baa` (43), `test_compliance_dashboard` (48),
  `test_hipaa_config` (36), `test_dashboard` (38), `test_hipaa_routes`
  (29) — includes 10 regression tests for S4/S7 (compile-once scan
  patterns, `scan_timeout_ms` enforcement, zero-width pattern rejection,
  BAA persistence, Jinja sandboxing) and 10 for S9-S12 (audit tail-write
  robustness, in-memory chain head, `unprovisioned` health label,
  `_store_error` recovery, `audit_log_max_bytes` auto-rotation)
- Test tooling: pytest-xdist parallel execution (`addopts = -n auto -q`),
  `quick`/`integration`/`slow` markers, `pytest-testmon` dev dependency
- Pre-existing failures (85) in the v0.4.0 rate-limit/API-key chain are
  unchanged and unrelated to HIPAA

---

## [0.4.0] — 2026-07-30

### Changed

- Version bumped `0.3.0` → `0.4.0`
- `README.md` — added HIPAA mode section (subsequently rewritten in v0.5.0)
- `CHANGELOG.md` — initial HIPAA changelog entry (superseded by v0.5.0)
- `docs/HIPAA_MODE.md` — added as TODO scaffolding (completed in v0.5.0)
- Added HIPAA scaffolding: `hipaa/baa.py`, `hipaa/dashboard.py`, BAA +
  dashboard templates, and pre-written HIPAA tests

> **Note:** this entry originally described analysis-brief `hipaa/*` REST
> paths and features that were planned but never shipped at this version. The
> implemented HIPAA compliance library ships in v0.5.0 —
> see the [0.5.0] entry above.

## [0.3.0] — 2026-07-15

### Added

- **Meeting Sharing** — Create shareable links with expiration and access controls
- **Batch Processing** — Process multiple audio files in a single batch job
- **Team Management** — Multi-user team workspaces with admin/member/viewer roles
- **Webhook Subscriptions** — Receive batch completion notifications via webhooks
- **Legal Mode** — Case metadata, testimony tracking, objection logging (via `mode=legal` on meeting creation)
- `/api/v1/meetings/{meeting_id}/share` and related share endpoints for link management
- `/api/v1/teams/*` endpoints for team CRUD and membership
- `/api/v1/batches/*` endpoints for batch processing
- `/api/v1/webhooks/*` endpoints for subscription management

### Changed

- `MeetingMode` enum extended with `LEGAL` value
- Pydantic models updated for LegalNote, CaseMetadata, TestimonyPoint, Objection
- Database models added: `Team`, `TeamMember`, `SharedLink`, `BatchJob`, `BatchFileResult`, `WebhookSubscription`

---

## [0.2.0] — 2026-06-20

### Added

- **Healthcare Mode** — SOAP note formatting, HIPAA marker generation, consent tracking
- **JWT Authentication** — Signup, login, token-based auth with 24h expiry
- **Role-Based Access** — Admin/member/viewer team roles
- **Export Service** — JSON, Markdown, PDF (weasyprint), ZIP export
- **Audio Transcription** — OpenAI Whisper API integration
- **LLM Extraction** — Structured data extraction via gpt-4o
- `/api/v1/auth/*` endpoints for authentication
- `/api/v1/meetings/*` endpoints for meeting CRUD
- `GET /api/v1/batches/{batch_id}/export` — batch results export (JSON, Markdown, PDF, ZIP)

### Changed

- FastAPI application structure refactored with APIRouter pattern
- SQLAlchemy async session pattern established
- Test suite expanded with interface + behavioral pattern

---

## [0.1.0] — 2026-05-15

### Added

- Initial project scaffold
- FastAPI application with basic health check endpoint
- In-memory SQLite test database setup
- Basic Pydantic models for meetings and transcription
