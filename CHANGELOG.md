# Changelog

All notable changes to MeetingNotesAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
  analysis-brief `/api/v1/hipaa/*` paths from the v0.4.0 changelog entry
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

> **Note:** this entry originally described HIPAA REST endpoints
> (`/api/v1/hipaa/*`) and features that were planned but never shipped at
> this version. The implemented HIPAA compliance library ships in v0.5.0 —
> see the [0.5.0] entry above.

## [0.3.0] — 2026-07-15

### Added

- **Meeting Sharing** — Create shareable links with expiration and access controls
- **Batch Processing** — Process multiple audio files in a single batch job
- **Team Management** — Multi-user team workspaces with admin/member/viewer roles
- **Webhook Subscriptions** — Receive batch completion notifications via webhooks
- **Legal Mode** — Case metadata, testimony tracking, objection logging
- `/api/v1/sharing/*` endpoints for link management
- `/api/v1/teams/*` endpoints for team CRUD and membership
- `/api/v1/batches/*` endpoints for batch processing
- `/api/v1/webhooks/*` endpoints for subscription management
- `/api/v1/legal/*` endpoints for legal mode

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
- `/api/v1/export/*` endpoints for export operations

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
