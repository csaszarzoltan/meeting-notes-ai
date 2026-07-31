# HIPAA Mode — MeetingNotesAI

**Version:** 0.5.0

HIPAA-compliant healthcare mode for MeetingNotesAI. This document covers the
HIPAA compliance library shipped in v0.5.0: PHI redaction, audit logging,
encryption, BAA lifecycle, and the compliance dashboard data service.

> **Scope note (v0.5.0):** the HIPAA suite ships as a **Python library**
> (`meeting_notes_ai.hipaa.*`). No HTTP endpoints are exposed in this release —
> there is no `/api/v1/hipaa/*` route group yet, and the meeting endpoint
> (`POST /api/v1/meetings`) does not perform PHI redaction automatically.
> Integrate the library directly, or wire the FastAPI dependencies in
> `hipaa/middleware.py` into your own routes.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [PHI Redaction](#phi-redaction)
4. [Audit Logging](#audit-logging)
5. [Encryption](#encryption)
6. [BAA Lifecycle](#baa-lifecycle)
7. [Compliance Dashboard](#compliance-dashboard)
8. [Configuration Reference](#configuration-reference)
9. [Library API Surface](#library-api-surface)
10. [Troubleshooting](#troubleshooting)
11. [HIPAA Compliance Checklist](#hipaa-compliance-checklist)

---

## Overview

### Features

- **PHI Redaction** — Regex-based detection of HIPAA identifiers (SSN, DOB,
  phone, email, MRN, patient/provider names) with configurable redaction modes
  (`mask`, `hash`, `truncate`, `annotate`) and runtime custom patterns.
- **Audit Logging** — Append-only JSONL audit trail for all PHI access and
  processing events, with configurable retention (default 6 years) and manual
  rotation.
- **Encryption at Rest** — AES-256-GCM envelope encryption with a master KEK
  (from `HIPAA_MASTER_KEY`) and per-tenant data encryption keys (DEKs).
- **BAA Management** — Business Associate Agreement template generation
  (HIPAA §164.504(e) clauses), immutable storage, and PDF export.
- **Compliance Dashboard** — `ComplianceService` aggregates audit, encryption,
  BAA, and PHI statistics into a compliance summary and chart-ready data.

### What is NOT in this release

Documented here so nobody relies on it:

- No REST endpoints (`/api/v1/hipaa/*`) are registered in `main.py`.
- The bundled `templates/dashboard.html.jinja` exists but is not served by any
  route.
- `HIPAAConfig.load()` returns defaults — **no environment-variable overrides
  are implemented yet**. Configuration is done by constructing `HIPAAConfig`
  with explicit values.
- The LLM validation pass is a stub: `LLMValidator.validate()` confirms all
  regex matches and never calls an external LLM in this release.

---

## Quick Start

```bash
# Install dependencies (includes cryptography and fpdf2)
uv sync

# The KEK seed — any string; the 32-byte AES key is derived via SHA-256
export HIPAA_MASTER_KEY="$(openssl rand -hex 32)"
```

```python
# Minimal end-to-end example
from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor
from meeting_notes_ai.hipaa.audit_logger import AuditLogger, AuditEntry
from meeting_notes_ai.hipaa.config import HIPAAConfig
import asyncio

async def main():
    redactor = PHIRedactor()
    redacted, matches = redactor.redact(
        "Patient John Smith, SSN 123-45-6789, DOB 03/14/1985"
    )
    print(redacted)   # [REDACTED], SSN [REDACTED], DOB [REDACTED]

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

See [`examples/`](../examples/) for five runnable scripts covering every
feature area.

---

## PHI Redaction

### Configuration

`PHIRedactor(config: HIPAAConfig | None = None)` loads patterns from
`HIPAAConfig.phi_patterns_path` when the file exists, otherwise falls back to
the built-in defaults. The patterns JSON is a dict of category name → `{
"pattern": <regex>, "label": <str>, "risk_level": <"high"|"medium"|"low"> }`:

```json
{
  "ssn": {
    "pattern": "\\b\\d{3}-\\d{2}-\\d{4}\\b",
    "label": "Social Security Number",
    "risk_level": "high"
  },
  "phone": {
    "pattern": "\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b",
    "label": "Phone Number",
    "risk_level": "medium"
  }
}
```

Built-in default categories: `ssn`, `dob`, `phone`, `email`, `mrn`, `name`.
The scanner also detects generic capitalized name pairs ("John Smith") and
skips common false positives (month/day names, "Today", "Yesterday", ...).
Invalid regexes in the patterns file are skipped at load; an invalid regex in
`add_custom_pattern()` raises `ValueError`.

### Usage

```python
from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

redactor = PHIRedactor()

# Scan only — returns PHIMatch objects (category, label, risk_level, start, end, matched_text)
matches = redactor.scan("MRN: 123456789, email john.smith@example.com")

# Redact — returns (redacted_text, matches)
redacted, matches = redactor.redact("SSN 123-45-6789", mode="mask")
```

### Redaction Modes

| Mode | Behavior | Example |
|------|----------|---------|
| `mask` (default) | Replace with `[REDACTED]` | `[REDACTED]` |
| `hash` | Deterministic SHA-256 prefix (12 hex chars) | `a5b1aa0b980f` |
| `truncate` | First character + `...` | `P...` |
| `annotate` | `[PHI:<length>]` | `[PHI:18]` |

### Custom Patterns & Stats

```python
redactor.add_custom_pattern("medicare_id", r"\b\d{11}\b", "high")
redacted, matches = redactor.redact("Medicare ID 12345678901 on file.")
# -> "Medicare ID [REDACTED] on file."

redactor.get_stats()
# {'by_category': {...}, 'by_risk_level': {...}, 'total_matches': N}
# NOTE: stats are cumulative across all scans/redactions on this instance.

redactor.reload_patterns()  # hot-reload the patterns JSON file; returns pattern count
```

---

## Audit Logging

### Log Format

`AuditLogger(config: HIPAAConfig | None = None)` writes one JSON object per
line (JSONL) to `audit_log_dir/audit-YYYY-MM-DD-<instance-id>.jsonl`. Each
`AuditEntry` has:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timestamp` | str (ISO8601) | `""` | **Required** — when the event occurred |
| `actor` | str | `""` | **Required** — user/service identifier |
| `action` | str | `""` | **Required** — e.g. `phi.scan`, `phi.redact` |
| `resource` | str | `""` | **Required** — e.g. `meeting:<uuid>` |
| `phi_classification` | str | `"none"` | `high`, `medium`, `low`, `none` |
| `details` | dict | `{}` | Additional context |
| `outcome` | str | `"success"` | `success` or `failure` |
| `ip_address` | str | `""` | Client IP address |
| `user_agent` | str | `""` | Client user agent |

Missing any of the four required fields (`timestamp`, `actor`, `action`,
`resource`) raises `ValueError` — entries are never written half-populated.
Writes are serialized with an `asyncio.Lock` and executed in a thread
executor, so concurrent `log()` calls cannot interleave lines.

Example line:

```json
{"timestamp": "2026-07-31T08:00:00Z", "actor": "user-42", "action": "phi.redact", "resource": "meeting:abc-123", "phi_classification": "high", "details": {}, "outcome": "success", "ip_address": "10.0.0.1", "user_agent": ""}
```

### Reading the Log

```python
import asyncio
from meeting_notes_ai.hipaa.audit_logger import AuditLogger, AuditEntry
from meeting_notes_ai.hipaa.config import HIPAAConfig

async def main():
    logger = AuditLogger(config=HIPAAConfig(audit_log_dir="/tmp/audit-logs"))
    await logger.log(AuditEntry(
        timestamp="2026-07-31T08:00:00Z", actor="user-42",
        action="phi.redact", resource="meeting:abc-123",
    ))

    # Query — optional filters on any field, sorted newest-first, limit 100 default
    entries = await logger.query(filters={"actor": "user-42"}, limit=10)

    # Stats — totals, per-action/actor/outcome/PHI-level counts, earliest/latest
    stats = await logger.get_stats()          # {"total_entries": N, "actions": {...}, ...}
    stats_30d = await logger.get_stats(since="2026-07-01T00:00:00Z")

    # Rotation — rename the active file to an archive; returns the archive path
    archive = await logger.rotate()

    # Export — filter by timestamp range into exports/audit-export-<start>-<end>-<id>.jsonl
    export = await logger.export_range("2026-07-01", "2026-12-31")

asyncio.run(main())
```

### Retention & Rotation

- `audit_log_retention_days` defaults to `365 * 6` (6 years, HIPAA minimum).
- `audit_log_max_bytes` (default 100 MB) and `audit_log_backup_count` (default
  0 = unlimited) are configured for future automatic rotation; **automatic
  size-based rotation is not implemented in this release** — call
  `rotate()` manually or on a schedule.
- `query()` and `get_stats()` read only the **current** active file. Archived
  files are not aggregated until you read them yourself (e.g. via
  `export_range` on the archive, or a custom reader over the directory).

---

## Encryption

### Key Hierarchy

1. **Master KEK** — derived as `SHA-256(HIPAA_MASTER_KEY)` from the
   `HIPAA_MASTER_KEY` environment variable. Any string works; there is no
   length requirement.
2. **Per-tenant DEK** — a fresh 256-bit AES-GCM key generated per tenant and
   *wrapped* (encrypted) with the KEK before storage.
3. **Ciphertext** — field or document values encrypted with the tenant DEK
   using AES-256-GCM (authenticated encryption: confidentiality + integrity).

If `HIPAA_MASTER_KEY` is unset and `encryption_enabled` is `True` (the
default), `EncryptionService.__init__` raises `EncryptionError` immediately —
fail fast rather than encrypt with an empty key.

### Usage

```python
import asyncio, os
from meeting_notes_ai.hipaa.config import HIPAAConfig
from meeting_notes_ai.hipaa.encryption import EncryptionService

os.environ["HIPAA_MASTER_KEY"] = "some-strong-secret"

async def main():
    svc = EncryptionService(config=HIPAAConfig())

    # Provision a tenant key; returns a fingerprint (never the key material)
    fp = await svc.generate_tenant_key("tenant-1")

    # Field-level
    ct = await svc.encrypt_field("tenant-1", "PHI: John Smith 123-45-6789")
    pt = await svc.decrypt_field("tenant-1", ct)          # "PHI: John Smith 123-45-6789"

    # Document-level: strings (and nested dicts) are encrypted; ints/floats/None kept as-is
    doc = {"name": "John Smith", "age": 42, "nested": {"mrn": "123456789"}}
    enc = await svc.encrypt_document("tenant-1", doc)
    dec = await svc.decrypt_document("tenant-1", enc)

    # Key info (metadata only — plaintext keys are never exposed)
    info = await svc.get_key_info("tenant-1")  # KeyInfo(... is_active=True, rotated_at=None)

asyncio.run(main())
```

### Master Key Rotation

```python
import asyncio

async def rotate():
    # Re-wraps every stored DEK with the new KEK. Returns the number of keys rotated.
    count = await svc.rotate_master_key("brand-new-master-key")
    # After rotation, store the new secret in HIPAA_MASTER_KEY for future process starts.
    return count

count = asyncio.run(rotate())
```

`rotate_master_key(new_kek_secret)` derives the new KEK from the argument,
re-wraps all existing DEKs, stamps `rotated_at` on their metadata, and updates
the in-memory KEK. The new secret must then be persisted to the environment so
restarts keep working.

### Errors

| Exception | Raised when |
|-----------|-------------|
| `EncryptionError` | Master key missing at init (and encryption enabled) |
| `KeyNotFoundError` | No key provisioned for the requested tenant |
| `DecryptionError` | Decryption fails (tampered data, wrong key) |

> **Storage caveat:** the key store is **in-memory** in this release
> (`EncryptionService._key_store`). Provisioned keys and metadata do not
> survive a process restart. The optional `db_factory` parameter is accepted
> but not yet used. Plan persistence before production use.

---

## BAA Lifecycle

### Template

`BAAService` renders the bundled Jinja2 template
(`hipaa/templates/baa_template.md.jinja`) with the HIPAA §164.504(e) required
clauses: permitted uses and disclosures, safeguards, breach notification,
minimum necessary, term and termination, **return or destruction of PHI
within 30 days**, and miscellaneous terms.

Template variables:

| Variable | Description |
|----------|-------------|
| `{{ org_name }}` | Covered entity name |
| `{{ ba_name }}` | Business associate name |
| `{{ effective_date }}` | Agreement effective date |

A custom template path can be set via `HIPAAConfig.baa_template_path`
(absolute path that exists, or a path relative to the package's `templates/`
directory); the bundled template is the fallback.

### Usage

```python
import asyncio
from meeting_notes_ai.hipaa.baa import BAAService

async def main():
    svc = BAAService()

    # 1. Generate markdown from the template
    markdown = await svc.generate_template(
        org_name="Acme Health Systems",
        ba_name="CloudNotes Inc.",
        effective_date="2026-08-01",
    )

    # 2. Store a signed agreement — immutable: no update after signing
    agreement_id = await svc.store_agreement(
        org_name="Acme Health Systems",
        ba_name="CloudNotes Inc.",
        signed_by="Dr. Jane Smith",
    )   # effective_date is set to today automatically

    # 3. Retrieve / list / export
    agreement = await svc.get_agreement(agreement_id)   # BAAgreement dataclass
    summaries = await svc.list_agreements()             # BAAgreementSummary list, newest first
    pdf_bytes = await svc.generate_pdf(agreement_id)    # PDF via fpdf2 (no weasyprint needed)

asyncio.run(main())
```

### Immutability

Once stored, an agreement cannot be updated — only read
(`get_agreement`), listed (`list_agreements`), or exported as PDF
(`generate_pdf`). `get_agreement` raises `ValueError` for unknown IDs.
Status is a string field (`active` by default; `expired`/`terminated` are
valid values for your own bookkeeping — no automatic status transitions are
implemented).

> **Storage caveat:** agreements are stored **in-memory** in this release
> (`BAAService._agreements`). The optional `db_factory` parameter is accepted
> but not yet used. Plan persistence before production use.

---

## Compliance Dashboard

`ComplianceService` aggregates the other four modules into a single summary
and chart-ready statistics.

### Wiring

```python
compliance = ComplianceService(
    audit_logger=audit_logger,
    encryption_service=encryption_service,
    baa_service=baa_service,
    phi_redactor=phi_redactor,
)
```

### Summary — `get_summary()`

Returns a `ComplianceSummary` dataclass:

| Field | Meaning |
|-------|---------|
| `total_phi_scans` | Cumulative PHI **matches** seen by the redactor (`stats.total_matches`) |
| `total_redactions` | Reserved — always `0` in this release |
| `active_encryption_keys` | `0` unless a tenant literally named `__dashboard__` has a key (the probe key used by `get_summary`) |
| `active_baa_agreements` | Count from `baa_service.list_agreements()` |
| `audit_entries_30d` | `total_entries` from `audit_logger.get_stats()` |
| `overall_compliance_score` | 0.0–1.0, see formula below |
| `last_audit_entry` | Latest timestamp in the audit log (`None` if empty) |
| `encryption_health` | Always `"healthy"` in this release (no health check is wired) |

**Compliance score formula** (verified in `_calc_compliance_score`):

```
score = 1.0
      - 0.3  if encryption_health == "unhealthy"   (never in this release)
      - 0.1  if encryption_health == "degraded"    (never in this release)
      - 0.2  if active_baa_agreements == 0
      - 0.1  if audit_entries == 0
clamped to [0.0, 1.0]
```

So an empty system scores `0.7`; adding one BAA + one audit entry brings it to
`1.0`.

### Charts — `get_phi_stats(since="30d")`

Returns a `PHIStats` dataclass: `by_category` and `by_risk_level` come from the
redactor's cumulative stats (pie/bar chart data). `by_date`,
`total_false_positives`, and `total_llm_corrections` are reserved (empty/0) in
this release.

### Activity — `get_recent_activity(limit=50)`

Returns the most recent audit entries as a list of dicts
(`timestamp`, `actor`, `action`, `resource`, `outcome`). Reads only the
current active audit file (same caveat as `AuditLogger.query`).

### Status helpers

- `get_encryption_status()` → `{"status": "healthy", "total_keys": 0, "active_keys": 0}` (static in this release)
- `get_baa_compliance()` → `{"total_agreements": 0, "active": 0, "expired": 0, "terminated": 0}` (static in this release)

---

## Configuration Reference

`HIPAAConfig` is a validated dataclass. All defaults below are verified in
`hipaa/config.py`; `HIPAAConfig.load()` returns `HIPAAConfig()` (defaults —
no env overrides yet).

| Field | Default | Description |
|-------|---------|-------------|
| `phi_patterns_path` | `"hipaa/phi_patterns.json"` | Path to PHI patterns JSON (falls back to built-ins) |
| `scan_timeout_ms` | `100` | Reserved scan timeout budget (not enforced in this release) |
| `audit_log_dir` | `"data/audit_logs/"` | Audit log storage directory |
| `audit_log_retention_days` | `2190` (6 years) | Retention window (validated `>= 1`) |
| `audit_log_max_bytes` | `100 * 1024 * 1024` | Max single-file size (rotation hook, not enforced yet) |
| `audit_log_backup_count` | `0` | Backups to keep (`0` = unlimited) |
| `encryption_enabled` | `True` | If `True`, missing `HIPAA_MASTER_KEY` fails fast |
| `master_key_env_var` | `"HIPAA_MASTER_KEY"` | Env var holding the KEK seed |
| `encryption_key_length` | `32` | AES-256 key length in bytes |
| `encryption_nonce_length` | `12` | GCM nonce length (96 bits) |
| `baa_template_path` | `"hipaa/templates/baa_template.md.jinja"` | BAA Jinja2 template |
| `default_baa_effective_days` | `365` | Default BAA effective period in days |
| `llm_validation_enabled` | `True` | LLM validation toggle (stub in this release) |
| `llm_validation_threshold` | `0.8` | Confidence threshold, validated `0.0–1.0` |

Validation in `__post_init__` raises `ValueError` for
`llm_validation_threshold` outside `[0.0, 1.0]` or `audit_log_retention_days < 1`.

Environment variables actually read by the code:

| Variable | Read by | Purpose |
|----------|---------|---------|
| `HIPAA_MASTER_KEY` | `EncryptionService.__init__` | KEK seed (SHA-256-derived 32-byte key) |

---

## Library API Surface

| Module | Public API |
|--------|-----------|
| `hipaa.config` | `HIPAAConfig` (dataclass), `HIPAAConfig.load()` |
| `hipaa.phi_patterns` | `PHIRedactor`, `PHIMatch`, `PHIRedactionResult`, `DEFAULT_PHI_PATTERNS` |
| `hipaa.redactor` | Re-exports `PHIRedactor`, `PHIMatch`, `PHIRedactionResult` |
| `hipaa.llm_validator` | `LLMValidator`, `LLMValidationResult` (stub — confirms regex matches) |
| `hipaa.audit_logger` | `AuditLogger`, `AuditEntry` |
| `hipaa.encryption` | `EncryptionService`, `KeyInfo`, `EncryptionError`, `DecryptionError`, `KeyNotFoundError` |
| `hipaa.baa` | `BAAService`, `BAATemplate`, `BAAgreement`, `BAAgreementSummary` |
| `hipaa.dashboard` | `ComplianceService`, `ComplianceSummary`, `PHIStats` |
| `hipaa.middleware` | FastAPI dependencies `get_phi_redactor`, `get_audit_logger`, `get_encryption_service` (not wired to routes in this release) |

---

## Troubleshooting

1. **`EncryptionError: Master key not found: set HIPAA_MASTER_KEY`**
   - Set `HIPAA_MASTER_KEY` before constructing `EncryptionService`, or pass
     `HIPAAConfig(encryption_enabled=False)` to disable the fail-fast check.

2. **PHI patterns not matching**
   - The patterns JSON must map category names to objects with `pattern`,
     `label`, `risk_level`. Invalid regexes are silently skipped at load.
   - Patterns are hot-reloadable: call `PHIRedactor.reload_patterns()`.
   - Only 6 built-in categories exist (SSN, DOB, phone, email, MRN, names) —
     add more via `add_custom_pattern()` or the patterns file.

3. **`ValueError: Missing required fields: ...` on `log()`**
   - `AuditEntry.timestamp`, `actor`, `action`, and `resource` are all
     mandatory.

4. **Audit log looks empty after `rotate()`**
   - `query()`/`get_stats()` read only the current active file. Read the
     archived file directly (JSONL) or via `export_range`.

5. **Dashboard shows `active_encryption_keys: 0`**
   - Expected in this release: `get_summary()` probes a `__dashboard__` tenant
     that only exists if you provision it. `total_redactions` is also always 0.

6. **PDF export fails**
   - Confirm the agreement ID is valid (`ValueError: Agreement not found`).
     PDF export uses `fpdf2` (bundled) — **weasyprint is not required**.

7. **Keys/agreements vanish on restart**
   - Both stores are in-memory in this release (`db_factory` is accepted but
     unused). Add persistence before relying on them across restarts.

---

## HIPAA Compliance Checklist

- [ ] PHI redaction configured (built-in patterns + custom patterns for your
      organization's identifiers)
- [ ] Redaction mode chosen per data class (`mask`/`hash`/`truncate`/`annotate`)
- [ ] Audit logging enabled with 6-year retention (`audit_log_retention_days`)
- [ ] Every PHI access/processing event logged with actor, action, resource,
      outcome (`AuditEntry` required fields)
- [ ] `HIPAA_MASTER_KEY` set from a secret manager and backed up
- [ ] Master key rotation scheduled (`rotate_master_key` + env update)
- [ ] Per-tenant key isolation used (one DEK per tenant via `generate_tenant_key`)
- [ ] BAA template customized for your organization
- [ ] Signed BAA agreements stored (immutably — no updates after signing)
- [ ] Compliance summary reviewed (`get_summary`) with BAA + audit entries in
      place (score `1.0`)
- [ ] No plaintext secrets in logs or API responses (`KeyInfo` exposes
      fingerprints only)
- [ ] Persistence planned for key store and BAA agreements before production
