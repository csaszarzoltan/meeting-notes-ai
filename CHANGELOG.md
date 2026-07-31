# Changelog

All notable changes to MeetingNotesAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] — 2026-07-30

### Added

- **HIPAA Mode** — Full HIPAA compliance feature suite for healthcare meeting notes.

#### PHI Redaction (P0)
- PHI Patterns Registry with 18 HIPAA identifier categories (names, SSN, DOB, phone, email, etc.)
- Configurable redaction modes: mask, hash, truncate, annotate
- Hot-reloadable patterns without app restart
- API endpoints: `POST /api/v1/hipaa/scan`, `POST /api/v1/hipaa/redact`, `GET /api/v1/hipaa/patterns`

#### LLM PHI Validation (P0)
- LLM validation pass to catch regex misses and reduce false positives
- Confidence scoring per match
- Graceful degradation when LLM API is unavailable
- Configurable toggle in HIPAAConfig

#### Append-Only Audit Logging (P0)
- JSONL-based append-only audit trail
- HIPAA-required fields: timestamp, actor, action, resource, outcome
- Automatic log rotation with 6-year retention
- API endpoints: `GET /api/v1/hipaa/audit-log`, `GET /api/v1/hipaa/audit-log/stats`

#### AES-256 Encryption at Rest (P0)
- Envelope encryption with master KEK + per-tenant DEKs
- AES-256-GCM authenticated encryption
- Key rotation support
- API endpoints: `POST /api/v1/hipaa/encryption/keys`, `GET .../keys/{tenant_id}`, `POST .../rotate`

#### BAA Template & Management (P1)
- Jinja2-based BAA template with all HIPAA §164.504(e) required clauses
- PDF export via fpdf2
- Immutable storage for signed agreements
- API endpoints: `POST /api/v1/hipaa/baa/generate`, `GET .../baa/{id}`, `GET .../baa/{id}/export`

#### Compliance Dashboard (P1)
- REST API for compliance metrics aggregation
- Chart.js HTML dashboard with summary cards, PHI category pie chart, risk level bar chart
- API endpoints: `GET /api/v1/hipaa/compliance/summary`, `GET .../compliance/phi-stats`, `GET .../compliance/activity`

#### Thread-safe Crypto Context Cleanup (P2)
- Fernet/AES contexts not reused across coroutines
- Warning log when KEK env var is missing
- Graceful degradation to "not enabled" mode

### Changed

- Updated `src/meeting_notes_ai/__init__.py` version to `0.4.0`

### Security

- All PHI processing is now audit-logged
- Encryption keys are never exposed in plaintext via API or logs
- Per-tenant key isolation for multi-tenant deployments

---

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
