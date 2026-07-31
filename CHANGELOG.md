# Changelog

All notable changes to MeetingNotesAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0] — 2026-07-31

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
  `get_audit_logger`, `get_encryption_service`) ready for route wiring

### Changed

- Version bumped `0.4.0` → `0.5.0`
- `README.md` — HIPAA section rewritten to document the library API (the
  v0.4.0 entry previously listed `/api/v1/hipaa/*` REST endpoints that were
  never implemented); added badges, healthcare-mode getting started,
  examples links, verified config table
- `docs/HIPAA_MODE.md` — rewritten from TODO scaffolding to a full guide
  (PHI redaction config, audit log interpretation, encryption key
  management, BAA usage, dashboard interpretation, config reference,
  troubleshooting, compliance checklist)
- `examples/` — new runnable scripts: `hipaa_phi_redaction.py`,
  `hipaa_audit_logs.py`, `hipaa_rotate_key.py`, `hipaa_baa_generate.py`,
  `hipaa_compliance_dashboard.py` (all verified with the repo venv)
- `CHANGELOG.md` — v0.4.0 entry corrected: it previously claimed REST
  endpoints that were never implemented; HIPAA features ship as a library
  in this release

### Breaking changes

- **No `/api/v1/hipaa/*` HTTP endpoints in this release.** The v0.4.0
  changelog entry listed REST endpoints (scan/redact/audit-log/encryption/
  baa/compliance) that never existed in the codebase — they are not part of
  v0.5.0 either. HIPAA features are consumed via the Python library API;
  wire the `hipaa.middleware` FastAPI dependencies into your own routes to
  expose them over HTTP.
- `HIPAAConfig.load()` returns defaults — env-var overrides are not
  implemented; configure via the dataclass constructor.
- LLM PHI validation (`hipaa.llm_validator`) is a stub in this release
  (confirms regex matches, never calls an external LLM).
- Key store (`EncryptionService`) and BAA agreements (`BAAService`) are
  in-memory; `db_factory` is accepted but unused — persistence is planned.

### Tests

- 269 HIPAA tests passing across 7 files: `test_phi_redaction` (52),
  `test_audit_logging` (38), `test_encryption` (39), `test_baa_template`
  (23), `test_compliance_dashboard` (43), `test_hipaa_config` (36),
  `test_dashboard` (38)
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
