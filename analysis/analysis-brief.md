# HIPAA Healthcare Mode — Analysis Brief

**Project:** MeetingNotesAI v0.3.0
**Feature:** HIPAA-compliant healthcare mode with PHI redaction, audit logging, encryption, BAA, and compliance dashboard
**Date:** 2026-07-30
**Author:** analyst (t_34388f60)

---

## 1. Current State Assessment

### 1.1 Codebase Overview

MeetingNotesAI v0.3.0 is a micro-SaaS for meeting transcription and structured notes, deployed on Railway. Current architecture:

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web framework | FastAPI 0.115+ | Async, lifespan events, APIRouter pattern |
| Database | SQLAlchemy 2.0.51 (async) | In-memory SQLite for tests, Railway Postgres in prod |
| Auth | JWT (python-jose) + bcrypt (passlib) | 24h token expiry, team roles (admin/member/viewer) |
| LLM | OpenAI client (gpt-4o) | ExtractionService for structured data from transcripts |
| Audio | OpenAI Whisper API | TranscriptionService wrapper |
| Export | Custom ExportService | JSON, Markdown, PDF (weasyprint), ZIP |
| Mode services | HealthcareService, LegalService | Thin wrappers around ExtractionService |
| Test pattern | pytest with interface + behavioral tests | 341 passing, 4 pre-existing auth failures |

### 1.2 Existing Healthcare Mode (v0.3.0 baseline)

The current `HealthcareService` in `src/meeting_notes_ai/services/healthcare.py` provides:

- **SOAP note formatting** — splits extraction result into subjective/objective/assessment/plan sections via heuristic helper functions (`_extract_subjective`, `_extract_objective`, `_extract_assessment`, `_extract_plan`)
- **HIPAA marker generation** — `_generate_hipaa_markers()` creates `HIPAAMarker` objects with field/risk_level/recommendation, triggered by presence of `patient_id` or extraction content
- **Consent tracking** — `ConsentStatus` with `confirmed` boolean and timestamp
- **De-identification flag** — `de_identified` boolean set to `True` when `patient_id` is None

**Gaps for HIPAA compliance:**
1. No PHI pattern detection or redaction — the service flags PHI risks but does not detect or remove actual PHI data (names, SSN, DOB, medical record numbers, etc.)
2. No configurable regex patterns for 18 HIPAA identifiers
3. No LLM-based validation layer to catch regex misses
4. No audit logging of PHI access or processing events
5. No encryption at rest for stored healthcare data
6. No BAA (Business Associate Agreement) template or management
7. No compliance dashboard or reporting
8. OpenAPI key hardcoded as TODO in auth.py (`SECRET_KEY`)

### 1.3 Existing Pydantic Models (relevant to healthcare)

Located in `src/meeting_notes_ai/models.py`:
- `MeetingMode.HEALTHCARE` enum value
- `SOAPNote` — subjective, objective, assessment, plan fields
- `HIPAAMarker` — field, risk_level (high/medium/low), recommendation
- `ConsentStatus` — confirmed (bool), timestamp, note
- `HealthcareNote` — soap, hipaa_markers, consent_status, de_identified

### 1.4 Test Coverage

Healthcare-specific tests in `tests/test_healthcare_mode.py`:
- 16 interface tests (class exists, signatures, defaults, instantiation)
- 5 behavioral tests (process returns HealthcareNote, patient_id markers, consent, empty transcript)
- All use mocked ExtractionService (AsyncMock)

---

## 2. Clustered Options

### 2.1 PHI Handling & Redaction

| Option | Approach | Complexity | Coverage | Maintenance |
|--------|----------|-----------|----------|-------------|
| **A. Regex-only** | Predefined patterns for the 18 HIPAA identifiers | Low | Medium (misses novel patterns) | Low |
| **B. LLM-only** | Delegate all PHI detection to LLM via prompt engineering | Medium | High (context-aware) | Medium |
| **C. Hybrid (chosen)** | Regex pre-scan for common patterns + LLM validation pass | Medium-High | High (catch + validate) | Medium |

**Chosen: Option C — Hybrid Regex + LLM Validation.** Regex catches 90%+ of standard PHI patterns (SSN, DOB, MRN, phone, email, name patterns) with near-zero latency. The LLM validation pass catches context-dependent PHI (e.g., "the patient's rare condition identifies them") and reduces false positives from regex over-match. This is the industry standard approach (ref: AWS Comprehend Medical, Azure Health Bot).

### 2.2 Audit Logging

| Option | Approach | Durability | Queryability | Complexity |
|--------|----------|-----------|-------------|-----------|
| **A. DB table** | SQLAlchemy model in same Postgres | High | High (SQL queries) | Low |
| **B. JSONL file** (chosen) | Append-only JSONL on filesystem or S3 | High | Medium (streaming grep) | Low |
| **C. External service** | Push to Splunk/DataDog/CloudWatch | High | High | High |

**Chosen: Option B — Append-only JSONL.** Rationale: immutable by design (append-only = no UPDATE/DELETE), simple to implement, HIPAA audit logs are write-once/read-rarely so SQL overhead is unnecessary. Each row is a self-contained JSON object with timestamp, actor, action, resource, PHI classification, and outcome. Can be rotated and archived. Optionally shipped to external SIEM later without schema changes.

### 2.3 AES-256 Encryption at Rest

| Option | Approach | Key Management | Performance | Complexity |
|--------|----------|---------------|-------------|-----------|
| **A. Application-level** | Encrypt/decrypt PHI fields in Python before DB write | Custom per-tenant key storage | Medium | Medium |
| **B. DB-level** | Postgres `pgcrypto` or TDE | DB-managed | High | Low (transparent) |
| **C. Hybrid (chosen)** | Application envelope encryption (AES-256-GCM + per-tenant KEK) | KEK in env, DEK per tenant stored encrypted | Medium | Medium-High |

**Chosen: Option C — Application envelope encryption.** Rationale: healthcare transcription is a multi-tenant SaaS — per-tenant keys are required to isolate PHI between practices. Postgres-level encryption (Option B) provides DB-at-rest but not per-tenant isolation. Application-level with envelope encryption (AWS KMS-inspired pattern): a master key encrypts per-tenant data encryption keys (DEKs), which encrypt individual fields. This gives us tenant isolation, key rotation capability, and auditable key access.

### 2.4 BAA Template

| Option | Approach | Flexibility | Maintenance |
|--------|----------|-----------|-------------|
| **A. Static file** | Hardcoded template in repo | Low | Low |
| **B. Markdown template** (chosen) | Jinja2/Markdown template with variable substitution | Medium | Low |
| **C. API-generated** | Dynamic PDF generation with provider-specific clauses | High | High |

**Chosen: Option B — Markdown template with Jinja2 substitution.** Generates BAA as Markdown (easily reviewed) with option to render as PDF. Template includes organization name, dates, service description, and both parties' obligations per HIPAA §164.504(e). Static clauses standard, variable fields for provider details.

### 2.5 Compliance Dashboard

| Option | Approach | Richness | Complexity |
|--------|----------|---------|-----------|
| **A. Simple HTML page** | Server-rendered dashboard with charts | Low | Low |
| **B. JSON API only** (chosen) | REST endpoints returning compliance metrics | Medium | Low |
| **C. React/Frontend app** | Full SPA with WebSocket real-time updates | High | High |

**Chosen: Option B — JSON API + simple static HTML.** A lightweight set of GET endpoints (`/compliance/dashboard/summary`, `/compliance/audit-log`, `/compliance/phi-stats`) that return structured JSON. A companion minimal HTML page with Chart.js renders the data client-side. No framework build step. This can later be upgraded to a full dashboard.

---

## 3. Chosen Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| PHI Regex patterns | `re` (stdlib) + configurable JSON file | Zero deps, easily auditable, hot-reloadable |
| LLM validation | OpenAI gpt-4o (existing) | Already in stack, async OpenAI client available |
| Audit log storage | Append-only JSONL on filesystem | Immutable, simple, no schema, rotate via logrotate |
| Encryption | `cryptography` library (AES-256-GCM) | Python stdlib alternative: `cryptography` is battle-tested, FIPS-compliant |
| Key management | Environment-based KEK + per-tenant DEK stored encrypted in DB | No external KMS dependency for v1; upgrade path to AWS KMS/HashiCorp Vault |
| BAA template | Jinja2 + markdown | `jinja2` is already an optional dep via `weasyprint`; markdown for version control |
| Compliance API | FastAPI (existing) | No new framework; reuses existing auth/db dependencies |
| Dashboard HTML | Jinja2 template + Chart.js CDN | No build step, server-rendered, skippable if pro plan |
| Testing | pytest + pytest-asyncio (existing) | Same test patterns, fixtures in conftest.py |

**New dependencies (to add to pyproject.toml):**
- `cryptography>=42.0.0` — AES-256-GCM encryption
- `jinja2>=3.1.0` — BAA template rendering (may already be installed via weasyprint dep)

**No new dependencies for:**
- PHI regex — Python stdlib `re`
- Audit logging — stdlib `json`, `logging`, `pathlib`
- JSONL rotation — stdlib `logging.handlers.RotatingFileHandler`

---

## 4. Shared Infrastructure (Build First)

These components are prerequisites for all 5 feature areas. Must be constructed before any P0 feature work begins.

### 4.1 HIPAA Configuration Module

**Module:** `src/meeting_notes_ai/hipaa/config.py`

Purpose: Central configuration for HIPAA mode — PHI regex patterns, encryption settings, audit log paths, BAA defaults. Extends `Settings` dataclass.

```python
@dataclass
class HIPAAConfig:
    phi_patterns_path: str = "hipaa/phi_patterns.json"       # Relative to app root
    audit_log_dir: str = "data/audit_logs/"
    audit_log_retention_days: int = 365 * 6  # 6 years per HIPAA
    encryption_enabled: bool = True
    master_key_env_var: str = "HIPAA_MASTER_KEY"
    default_baa_effective_days: int = 365
    llm_validation_enabled: bool = True
    llm_validation_threshold: float = 0.8    # Confidence threshold
```

### 4.2 PHI Patterns Registry

**Module:** `src/meeting_notes_ai/hipaa/phi_patterns.py`
**Data file:** `src/meeting_notes_ai/hipaa/phi_patterns.json`

JSON schema for the 18 HIPAA identifiers:
```json
{
  "categories": [
    {
      "name": "name",
      "label": "Patient Names",
      "risk_level": "high",
      "patterns": ["\\b[A-Z][a-z]+\\s[A-Z][a-z]+\\b"],
      "example": "John Smith"
    },
    {
      "name": "ssn",
      "label": "Social Security Number",
      "risk_level": "high",
      "patterns": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
      "example": "123-45-6789"
    },
    {
      "name": "dob",
      "label": "Date of Birth",
      "risk_level": "high",
      "patterns": ["\\b\\d{1,2}/\\d{1,2}/\\d{2,4}\\b"],
      "example": "01/15/1980"
    },
    {
      "name": "phone",
      "label": "Phone Number",
      "risk_level": "high",
      "patterns": ["\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b"],
      "example": "555-123-4567"
    },
    {
      "name": "email",
      "label": "Email Address",
      "risk_level": "high",
      "patterns": ["\\b[\\w.-]+@[\\w.-]+\\.\\w+\\b"],
      "example": "jane@example.com"
    },
    {
      "name": "address",
      "label": "Street Address",
      "risk_level": "high",
      "patterns": ["\\b\\d+\\s[A-Z][a-zA-Z]+\\s(St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Boulevard)\\b"],
      "example": "123 Main St"
    },
    {
      "name": "mrn",
      "label": "Medical Record Number",
      "risk_level": "high",
      "patterns": ["\\bMRN[\\s:-]*\\d{4,10}\\b", "\\b\\d{4,10}\\b(?=\\s*\\|)"],
      "example": "MRN: 1234567"
    },
    {
      "name": "health_plan_id",
      "label": "Health Plan Beneficiary Number",
      "risk_level": "high",
      "patterns": ["\\b[A-Z]{2,3}\\d{5,10}\\b"],
      "example": "XYZ1234567"
    },
    {
      "name": "account_number",
      "label": "Account Number",
      "risk_level": "medium",
      "patterns": ["\\b[Aa]ccount\\s*#?:?\\s*\\d{4,10}\\b"],
      "example": "Account #123456"
    },
    {
      "name": "certificate_number",
      "label": "Certificate/License Number",
      "risk_level": "medium",
      "patterns": ["\\b(DEA|NPI|License|Lic)[\\s#:]*\\d{6,15}\\b"],
      "example": "DEA 123456789"
    },
    {
      "name": "vehicle_id",
      "label": "Vehicle Identifier",
      "risk_level": "medium",
      "patterns": ["\\b[A-Z]{1,3}\\d{2,4}[A-Z]{1,3}\\b"],
      "example": "ABC1234"
    },
    {
      "name": "device_id",
      "label": "Device Identifier/Serial",
      "risk_level": "medium",
      "patterns": ["\\b(SN|Serial)[:\\s]*[A-Z0-9]{6,15}\\b"],
      "example": "SN: X7Y8Z9A1"
    },
    {
      "name": "url",
      "label": "Web URL",
      "risk_level": "low",
      "patterns": ["https?://[\\w./-]+"],
      "example": "https://example.com"
    },
    {
      "name": "ip_address",
      "label": "IP Address",
      "risk_level": "low",
      "patterns": ["\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b"],
      "example": "192.168.1.1"
    },
    {
      "name": "biometric_id",
      "label": "Biometric Identifier",
      "risk_level": "high",
      "patterns": [],
      "example": "Fingerprint template ref"
    },
    {
      "name": "photo",
      "label": "Full Face Photo",
      "risk_level": "high",
      "patterns": [],
      "example": "Photographic image ref"
    },
    {
      "name": "medical_record_ref",
      "label": "Medical Record Reference",
      "risk_level": "medium",
      "patterns": ["\\b(Chart|Record|File)[\\s#:]*\\d{4,10}\\b"],
      "example": "Chart #12345"
    },
    {
      "name": "other_phi",
      "label": "Other Unique Identifying Number",
      "risk_level": "medium",
      "patterns": [],
      "example": "Any other unique identifier"
    }
  ]
}
```

### 4.3 Database Models Extensions

**Module:** `src/meeting_notes_ai/db/models.py` (additions)

New ORM models:
- `EncryptionKey` — per-tenant data encryption key (wrapped)
- `AuditLogEntry` — lightweight reference copy for recent entries (JSONL is primary)
- `BAATemplate` — template versions
- `BAAgreement` — signed BAA records per tenant
- `ComplianceEvent` — compliance-relevant event summary

### 4.4 Middleware / Dependency Base

**Module:** `src/meeting_notes_ai/hipaa/middleware.py`

FastAPI middleware that:
- Injects `HIPAAConfig` into request scope
- Provides `get_phi_redactor` dependency
- Provides `get_audit_logger` dependency
- Provides `get_encryption_service` dependency
- Optionally wraps healthcare mode endpoints with automatic audit logging

---

## 5. Prioritized Task List

### P0 — Core HIPAA Infrastructure (Must Have)

#### T1. PHI Patterns Registry & Configurable Redaction Engine

**Module:** `src/meeting_notes_ai/hipaa/` — `phi_patterns.py`, `phi_patterns.json`, `redactor.py`
**Expected Behavior:**
- Load patterns from JSON at startup with hot-reload capability
- Scan text against all 18 HIPAA identifier regex patterns
- Return structured PHI matches with category, position, risk_level, matched_text
- Support redaction modes: `mask` (replace with `[REDACTED]`), `hash` (replace with SHA-256 hash), `truncate` (remove), `annotate` (wrap in `<PHI type="...">...</PHI>`)
- Track redaction statistics per category

**Interface:**
```python
@dataclass
class PHIMatch:
    category: str              # Pattern category name
    label: str                 # Human-readable label
    risk_level: Literal["high", "medium", "low"]
    start: int                 # Character offset
    end: int
    matched_text: str          # Original matched text
    redaction_mode: str        # Applied redaction mode

class PHIRedactor:
    def __init__(self, config: HIPAAConfig): ...
    def scan(self, text: str) -> list[PHIMatch]: ...
    def redact(self, text: str, mode: str = "mask") -> tuple[str, list[PHIMatch]]: ...
    def add_custom_pattern(self, name: str, pattern: str, risk_level: str) -> None: ...
    def get_stats(self) -> dict: ...
    def reload_patterns(self) -> int: ...  # Hot-reload patterns file
```

**Data Models:**
- `PHIMatch` dataclass (above)
- `PHIRedactionResult` — `redacted_text: str`, `matches: list[PHIMatch]`, `count_by_category: dict`

**API Endpoints:**
- `POST /api/v1/hipaa/scan` — Scan text for PHI without redacting (returns matches)
- `POST /api/v1/hipaa/redact` — Redact PHI from text (returns redacted + matches)
- `GET /api/v1/hipaa/patterns` — List configured patterns
- `GET /api/v1/hipaa/patterns/stats` — Pattern match statistics

**Dependencies:** HIPAAConfig (shared infra), phi_patterns.json

**Acceptance Criteria:**
- [ ] All 18 HIPAA identifier categories have at least one regex pattern each
- [ ] `scan()` detects SSN, DOB, phone, email in sample text
- [ ] `redact(mode="mask")` replaces with `[REDACTED]` placeholders
- [ ] `redact(mode="hash")` replaces with deterministic SHA-256 prefix
- [ ] Custom patterns can be added at runtime via `add_custom_pattern()`
- [ ] Patterns hot-reloadable via `reload_patterns()` without app restart
- [ ] Edge cases handled: empty text, nested PHI, overlapping matches, Unicode
- [ ] Performance: 50KB text scanned in < 100ms

---

#### T2. LLM PHI Validation Pass

**Module:** `src/meeting_notes_ai/hipaa/llm_validator.py`
**Expected Behavior:**
- After regex scan, pass redacted text + original PHI matches to LLM for validation
- LLM identifies: false positives (non-PHI caught by regex), missed PHI (not caught by regex), contextual PHI (e.g., rare condition + location = identifying)
- Returns validated match list with confidence scores
- Optional mode: LLM can request re-redaction of previously missed PHI
- No LLM call if `llm_validation_enabled` is False

**Interface:**
```python
@dataclass
class LLMValidationResult:
    confirmed_matches: list[PHIMatch]        # Regex matches confirmed by LLM
    false_positives: list[PHIMatch]          # Regex matches rejected by LLM
    new_matches: list[PHIMatch]              # PHI found by LLM, missed by regex
    confidence_scores: dict[str, float]      # Per-match confidence
    llm_analysis: str                        # Raw LLM response for audit

class LLMValidator:
    def __init__(self, extraction_service: ExtractionService, config: HIPAAConfig): ...
    async def validate(self, original_text: str, regex_matches: list[PHIMatch]) -> LLMValidationResult: ...
    async def suggest_redactions(self, text: str) -> list[PHIMatch]: ...
```

**Prompt Design:**
The LLM receives the transcript with regex-identified PHI callouts and asks it to confirm/correct each, plus flag any missed PHI.

**Dependencies:** ExtractionService (existing), PHIRedactor (T1), HIPAAConfig

**Acceptance Criteria:**
- [ ] LLM validator correctly identifies a false positive (e.g., "10/10/2020" flagged as DOB but is a meeting date)
- [ ] LLM validator catches a missed PHI (e.g., context: "the mayor of Springfield" → identify as location + title → PHI risk)
- [ ] Returns confidence scores per match
- [ ] Graceful degradation when LLM API is unavailable (falls through to regex-only)
- [ ] Configurable toggle in HIPAAConfig
- [ ] Async implementation matching existing codebase patterns

---

#### T3. Append-Only Audit Logging

**Module:** `src/meeting_notes_ai/hipaa/audit_logger.py`
**Expected Behavior:**
- Append-only JSONL file writer (no overwrite, no delete, no update)
- Each entry: `{"timestamp": "<ISO8601>", "actor": "<user_id>", "action": "<action>", "resource": "<resource_type>:<id>", "phi_classification": "high|medium|none", "details": {}, "outcome": "success|failure"}`
- Automatic log rotation (daily or 100MB, 6-year retention via config)
- FastAPI dependency `get_audit_logger` for route injection
- Thread-safe async file writes via `aiofile` or stdlib `asyncio.Lock`
- HIPAA-required fields: timestamp, user ID, action description, resource ID, IP/device info, outcome

**Interface:**
```python
@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    action: str                      # e.g., "phi.scan", "phi.redact", "encryption.key_generate"
    resource: str                    # e.g., "meeting:<uuid>", "patient:<id>"
    phi_classification: str          # "high", "medium", "low", "none"
    details: dict = field(default_factory=dict)
    outcome: str = "success"
    ip_address: str = ""
    user_agent: str = ""

class AuditLogger:
    def __init__(self, config: HIPAAConfig): ...
    async def log(self, entry: AuditEntry) -> None: ...
    async def query(self, filters: dict, limit: int = 100) -> list[AuditEntry]: ...
    async def get_stats(self, since: str = None) -> dict: ...
    async def rotate(self) -> Path: ...     # Force manual rotation
    async def export_range(self, start: str, end: str) -> Path: ...  # Export date range
```

**API Endpoints:**
- `GET /api/v1/hipaa/audit-log` — Query audit log (paginated, filterable by actor/action/resource/date range)
- `GET /api/v1/hipaa/audit-log/stats` — Summary statistics (count by action, by day, by PHI level)

**Dependencies:** HIPAAConfig

**Acceptance Criteria:**
- [ ] Writing 1000 entries sequentially all succeed
- [ ] File is valid JSONL (each line is valid JSON, parseable with `ijson` or line-by-line)
- [ ] Concurrent writes from multiple coroutines do not corrupt the file
- [ ] Log rotation creates timestamped archive files
- [ ] Query with date range filter returns correct subset
- [ ] Query with actor filter returns correct subset
- [ ] HIPAA mandatory fields are always populated (validation on write)
- [ ] Stale log files older than `retention_days` are marked for cleanup

---

#### T4. AES-256 Encryption at Rest with Per-Tenant Keys

**Module:** `src/meeting_notes_ai/hipaa/encryption.py`
**Expected Behavior:**
- Envelope encryption model: Master Key Encryption Key (KEK) stored in `HIPAA_MASTER_KEY` env var
- Per-tenant Data Encryption Key (DEK) generated on tenant provisioning
- DEK encrypted with KEK before storage in `EncryptionKey` DB model
- AES-256-GCM for authenticated encryption (integrity + confidentiality)
- Two operation modes: `field_encrypt` (encrypt individual string fields) and `document_encrypt` (encrypt full JSON blobs)
- Key rotation support: re-wrap DEKs with new KEK

**Interface:**
```python
class EncryptionService:
    def __init__(self, config: HIPAAConfig, db_factory: Callable): ...

    async def generate_tenant_key(self, tenant_id: str) -> str: ...   # Returns key fingerprint
    async def encrypt_field(self, tenant_id: str, plaintext: str) -> str: ...   # Returns base64 ciphertext
    async def decrypt_field(self, tenant_id: str, ciphertext: str) -> str: ...
    async def encrypt_document(self, tenant_id: str, data: dict) -> dict: ...
    async def decrypt_document(self, tenant_id: str, data: dict) -> dict: ...
    async def rotate_master_key(self, new_kek: str) -> int: ...       # Re-wrap all DEKs, returns count
    async def get_key_info(self, tenant_id: str) -> dict: ...         # Key metadata (no plaintext key ever returned)

    # Internal
    def _generate_dek(self) -> bytes: ...
    def _wrap_key(self, dek: bytes, kek: bytes) -> str: ...
    def _unwrap_key(self, wrapped_key: str, kek: bytes) -> bytes: ...
    def _aes_encrypt(self, key: bytes, plaintext: str) -> str: ...
    def _aes_decrypt(self, key: bytes, ciphertext: str) -> str: ...
```

**Data Model (DB addition — `meeting_notes_ai/db/models.py`):**
```python
class EncryptionKey(Base, TimestampMixin):
    __tablename__ = "encryption_keys"
    id: str = Column(String(36), primary_key=True, default=uuid4_str)
    tenant_id: str = Column(String(100), unique=True, nullable=False, index=True)
    wrapped_key: str = Column(Text, nullable=False)       # DEK encrypted with KEK (base64)
    key_fingerprint: str = Column(String(64), nullable=False)  # SHA-256 of KEK version
    algorithm: str = Column(String(20), default="AES-256-GCM")
    is_active: bool = Column(Boolean, default=True)
    rotated_at: DateTime = Column(DateTime(timezone=True), nullable=True)
```

**API Endpoints:**
- `POST /api/v1/hipaa/encryption/keys` — Generate new tenant key (admin only)
- `GET /api/v1/hipaa/encryption/keys/{tenant_id}` — Get key metadata
- `POST /api/v1/hipaa/encryption/rotate` — Rotate master KEK (admin only)
- `POST /api/v1/hipaa/encryption/encrypt` — Encrypt a field (internal use)
- `POST /api/v1/hipaa/encryption/decrypt` — Decrypt a field (internal use, audit logged)

**Dependencies:** HIPAAConfig, `cryptography` library, EncryptionKey DB model

**Acceptance Criteria:**
- [ ] `generate_tenant_key()` creates a unique DEK and stores it wrapped with the KEK
- [ ] `encrypt_field()` + `decrypt_field()` round-trip produces original plaintext
- [ ] AES-256-GCM nonces are unique per encryption (no nonce reuse)
- [ ] Ciphertext is authenticated: tampered ciphertext raises `DecryptionError`
- [ ] Two tenants with same plaintext produce different ciphertexts
- [ ] Key rotation generates new KEK fingerprint, re-wraps all DEKs
- [ ] Old DEKs remain decryptable until `is_active=False` (grace period)
- [ ] No plaintext key material is ever exposed via API or logs

---

### P1 — Compliance Aids (Should Have)

#### T5. BAA Template Generation & Management

**Module:** `src/meeting_notes_ai/hipaa/baa.py`
**Template:** `src/meeting_notes_ai/hipaa/templates/baa_template.md.jinja`

**Expected Behavior:**
- Generate a business associate agreement per HIPAA §164.504(e)
- Fill template fields: covered entity name, business associate name, effective date, service description, termination clause
- Store signed BAA agreements in DB
- List/retrieve/regenerate BAA documents
- Export as Markdown or PDF

**Interface:**
```python
class BAAService:
    def __init__(self, db_factory: Callable): ...

    async def generate_template(self, org_name: str, ba_name: str, effective_date: str) -> str: ...  # Returns markdown
    async def generate_pdf(self, agreement_id: str) -> bytes: ...         # Returns PDF bytes
    async def store_agreement(self, org_name: str, ba_name: str, signed_by: str) -> str: ...  # Returns id
    async def get_agreement(self, agreement_id: str) -> BAAgreement: ...
    async def list_agreements(self) -> list[BAAgreementSummary]: ...
```

**Data Models (DB additions):**
```python
class BAATemplate(Base, TimestampMixin):
    __tablename__ = "baa_templates"
    id: str = Column(String(36), primary_key=True, default=uuid4_str)
    version: str = Column(String(10), nullable=False)
    content: str = Column(Text, nullable=False)        # Markdown template body
    is_active: bool = Column(Boolean, default=True)

class BAAgreement(Base, TimestampMixin):
    __tablename__ = "baa_agreements"
    id: str = Column(String(36), primary_key=True, default=uuid4_str)
    org_name: str = Column(String(200), nullable=False)
    ba_name: str = Column(String(200), nullable=False)
    effective_date: str = Column(String(20), nullable=False)
    signed_by: str = Column(String(100), nullable=False)
    content_md: str = Column(Text, nullable=False)     # Rendered markdown
    status: str = Column(String(20), default="active") # active, expired, terminated
```

**API Endpoints:**
- `POST /api/v1/hipaa/baa/generate` — Generate BAA from template (body: org_name, ba_name, effective_date)
- `GET /api/v1/hipaa/baa/{agreement_id}` — Get agreement details
- `GET /api/v1/hipaa/baa/{agreement_id}/export?format=pdf|markdown` — Download agreement
- `GET /api/v1/hipaa/baa` — List all agreements

**Dependencies:** Jinja2, HIPAAConfig, BAAgreement DB model

**Acceptance Criteria:**
- [ ] BAA template includes all HIPAA §164.504(e) required clauses
- [ ] Template substitution correctly fills org_name, ba_name, effective_date
- [ ] PDF export produces valid PDF with proper formatting
- [ ] Signed agreements are stored immutably (no UPDATE after signed)
- [ ] Agreement listing returns paginated results

---

#### T6. Compliance Dashboard API & HTML

**Module:** `src/meeting_notes_ai/hipaa/dashboard.py`
**Template:** `src/meeting_notes_ai/hipaa/templates/dashboard.html.jinja`

**Expected Behavior:**
- REST API returns compliance metrics aggregated from audit log + encryption + BAA status
- Summary endpoint: total PHI scans, redactions performed, active keys, BAA agreements, audit entries in last 30 days
- PHI stats endpoint: matches by category (pie chart data), by risk level, by day (time series)
- Recent activity endpoint: last 50 audit entries
- Simple HTML dashboard page rendering Chart.js visualizations

**Interface:**
```python
class ComplianceService:
    def __init__(self, audit_logger: AuditLogger, encryption_service: EncryptionService,
                 baa_service: BAAService, phi_redactor: PHIRedactor): ...

    async def get_summary(self) -> ComplianceSummary: ...
    async def get_phi_stats(self, since: str = "30d") -> PHIStats: ...
    async def get_recent_activity(self, limit: int = 50) -> list[AuditEntry]: ...
    async def get_encryption_status(self) -> dict: ...
    async def get_baa_compliance(self) -> dict: ...

@dataclass
class ComplianceSummary:
    total_phi_scans: int
    total_redactions: int
    active_encryption_keys: int
    active_baa_agreements: int
    audit_entries_30d: int
    overall_compliance_score: float   # 0.0 - 1.0
    last_audit_entry: str | None
    encryption_health: str            # "healthy", "degraded", "unhealthy"

@dataclass
class PHIStats:
    by_category: dict[str, int]       # {"name": 42, "ssn": 7, "dob": 15, ...}
    by_risk_level: dict[str, int]     # {"high": 50, "medium": 30, "low": 20}
    by_date: dict[str, int]           # Time series {"2026-07-01": 12, ...}
    total_false_positives: int
    total_llm_corrections: int
```

**API Endpoints:**
- `GET /api/v1/hipaa/compliance/summary` — Compliance summary metrics
- `GET /api/v1/hipaa/compliance/phi-stats` — PHI statistics (accepts `since` query param)
- `GET /api/v1/hipaa/compliance/activity` — Recent audit entries
- `GET /api/v1/hipaa/compliance` — HTML dashboard page

**Dependencies:** AuditLogger (T3), EncryptionService (T4), BAAService (T5), PHIRedactor (T1)

**Acceptance Criteria:**
- [ ] Summary endpoint returns all fields with correct aggregations
- [ ] PHI stats by_category matches actual pattern scan totals from audit log
- [ ] Dashboard HTML page loads without errors (no broken JS or CSS)
- [ ] Chart.js renders at least one chart (pie or bar)
- [ ] Activity endpoint returns most recent entries with correct ordering
- [ ] Empty-state handling when no data exists yet

---

### P2 — Docs & Polish (Nice to Have)

#### T7. HIPAA Mode Documentation

**Module:** `docs/HIPAA_MODE.md`
**Expected Behavior:**
- Comprehensive documentation covering: PHI redaction setup, audit logging, encryption configuration, BAA lifecycle, compliance dashboard
- Step-by-step configuration guide for new tenants
- Security best practices section
- HIPAA compliance checklist

**Acceptance Criteria:**
- [ ] All 5 feature areas documented with code examples
- [ ] Configuration reference (environment variables, JSON schemas)
- [ ] Troubleshooting section for common issues

#### T8. Version Bump & Changelog

**Module:** `src/meeting_notes_ai/__init__.py`, `CHANGELOG.md`
**Expected Behavior:**
- Bump version to `0.4.0`
- Update CHANGELOG with all HIPAA features

**Acceptance Criteria:**
- [ ] Version string updated
- [ ] CHANGELOG entries for all new features

#### T9. Thread-safe Crypto Context Cleanup

**Module:** `src/meeting_notes_ai/hipaa/encryption.py`
**Expected Behavior:**
- Ensure `cryptography` Fernet/AES contexts are not reused across coroutines without reinitialization
- Add warning log when KEK env var is missing at startup
- Graceful degradation: without KEK, encryption defaults to "not enabled" mode

---

## 6. Dependency Graph

```
                          ┌──────────────────┐
                          │  HIPAAConfig      │ (shared infra)
                          │  (config.py)      │
                          └────────┬─────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
   ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │ PHIRedactor    │    │ AuditLogger      │    │ EncryptionService│
   │ (phi_patterns, │    │ (audit_logger.py)│    │ (encryption.py)  │
   │  redactor.py)  │    └────────┬─────────┘    └────────┬─────────┘
   └────────┬───────┘             │                       │
            │                     │                       │
            ▼                     ▼                       │
   ┌────────────────┐    ┌──────────────────┐            │
   │ LLMValidator   │◄───│ Audit entries    │            │
   │ (llm_validator)│    │ from all modules │            │
   └────────┬───────┘    └──────────────────┘            │
            │                                            │
            ▼                                            ▼
   ┌────────────────┐    ┌──────────────────┐   ┌──────────────────┐
   │ ComplianceSvc  │◄───│ All 3 P0 modules  │◄──│ BAA Service      │
   │ (dashboard.py) │    │ (aggregation)     │   │ (baa.py)         │
   └────────────────┘    └──────────────────┘   └──────────────────┘
```

**Build order:**
1. HIPAAConfig (shared infra)
2. PHIRedactor + phi_patterns.json (T1)
3. AuditLogger (T3)
4. EncryptionService (T4) — needs config + db model
5. LLMValidator (T2) — needs PHIRedactor
6. BAAService (T5) — needs config + db model
7. ComplianceService (T6) — needs T1, T3, T4, T5

---

## 7. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| KEK stored in env var compromises security model | High | Low | Document that env is for v1; upgrade path to AWS KMS/HashiCorp Vault documented |
| LLM validation adds latency to PHI processing | Medium | Medium | Configurable toggle; timeout + fallback to regex-only; async parallel execution |
| JSONL audit log performance under heavy write load | Medium | Low | Write batching (flush every 100ms or 50 entries); separate file per day |
| Encryption key loss = data loss | Critical | Low | KEK backup must be documented; add `HIPAA_MASTER_KEY_BACKUP` env var support |
| PHI regex false negatives in unstructured medical text | Medium | Medium | LLM validation pass catches regex misses; documented limitation |
| Concurrent test DB state contamination | Medium | Low | Use pytest fixtures with isolated test DB per test module |

---

## 8. Acceptance Criteria (Cross-Cutting)

- [ ] All P0 tasks have ≥90% test coverage (interface + behavioral + edge cases)
- [ ] All tests pass: `uv run pytest -q` — zero regressions from existing 341 passing tests
- [ ] Ruff lint clean: `uv run ruff check src/ tests/` — zero new errors
- [ ] New DB models have Alembic migration scripts or documented auto-create path
- [ ] All new API endpoints follow existing patterns: `prefix="/api/v1/..."`, proper status codes, auth where appropriate
- [ ] Healthcare mode toggle: existing `MeetingMode.HEALTHCARE` continues to work; new HIPAA features are additive
- [ ] Hot-reloadable PHI patterns file without app restart
- [ ] No plaintext secrets in logs, error messages, or API responses
- [ ] All async operations have timeout handling (default 30s)
- [ ] README updated with HIPAA mode configuration instructions
