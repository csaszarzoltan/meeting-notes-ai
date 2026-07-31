# HIPAA Mode — MeetingNotesAI

**Version:** 0.4.0 (planned)

HIPAA-compliant healthcare mode for MeetingNotesAI. This document covers all
HIPAA-related features: PHI redaction, audit logging, encryption, BAA lifecycle,
and the compliance dashboard.

---

## Table of Contents

1. [Overview](#overview)
2. [PHI Redaction Setup](#phi-redaction-setup)
3. [Audit Logging Configuration](#audit-logging-configuration)
4. [Encryption Configuration](#encryption-configuration)
5. [BAA Lifecycle](#baa-lifecycle)
6. [Compliance Dashboard](#compliance-dashboard)
7. [Configuration Reference](#configuration-reference)
8. [Troubleshooting](#troubleshooting)
9. [HIPAA Compliance Checklist](#hipaa-compliance-checklist)

---

## Overview

> **TODO:** Write overview of HIPAA mode, how to enable it, and what it provides.

### Features

- **PHI Redaction** — Automatic detection and redaction of 18 HIPAA identifiers
  using regex patterns with optional LLM validation pass.
- **Audit Logging** — Append-only JSONL audit trail for all PHI access and
  processing events, with 6-year retention.
- **Encryption at Rest** — AES-256-GCM envelope encryption with per-tenant keys.
- **BAA Management** — Business Associate Agreement template generation, PDF
  export, and immutable storage.
- **Compliance Dashboard** — Real-time compliance metrics with Chart.js
  visualizations.

### Quick Start

> **TODO:** Add a 2-minute quick start example.

```python
# Example: enabling HIPAA mode
from meeting_notes_ai.hipaa.config import HIPAAConfig

config = HIPAAConfig(
    phi_patterns_path="hipaa/phi_patterns.json",
    encryption_enabled=True,
)
```

---

## PHI Redaction Setup

> **TODO:** Document how to configure and use PHI redaction with code examples.

### Configuration

> **TODO:** phi_patterns.json schema, custom patterns, risk levels.

### Usage

```python
# TODO: Add PHI redaction code example
```

### Redaction Modes

- `mask` — Replace PHI with `[REDACTED]` (default)
- `hash` — Replace with deterministic SHA-256 hash prefix
- `truncate` — Remove PHI entirely
- `annotate` — Wrap in `<PHI type="...">...</PHI>` tags

### LLM Validation

> **TODO:** Describe LLM validation pass, how to enable/disable, confidence thresholds.

---

## Audit Logging Configuration

> **TODO:** Document audit logger setup, JSONL format, rotation, and querying.

### Log Format

Each audit entry is a JSON object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO8601 | When the event occurred |
| `actor` | string | User ID who performed the action |
| `action` | string | Action type (e.g., `phi.scan`, `phi.redact`) |
| `resource` | string | Resource identifier (`meeting:<uuid>`) |
| `phi_classification` | string | `high`, `medium`, `low`, `none` |
| `outcome` | string | `success` or `failure` |
| `ip_address` | string | Client IP address |
| `details` | object | Additional context |

### Retention

> **TODO:** Document 6-year retention policy and log rotation.

### Querying

> **TODO:** Document audit log query API with examples.

---

## Encryption Configuration

> **TODO:** Document AES-256-GCM envelope encryption setup.

### Prerequisites

- `cryptography>=42.0.0` Python package
- `HIPAA_MASTER_KEY` environment variable

### Key Hierarchy

1. **Master Key Encryption Key (KEK)** — stored in `HIPAA_MASTER_KEY` env var
2. **Per-tenant Data Encryption Key (DEK)** — generated per tenant, wrapped with KEK
3. **Field-level ciphertext** — AES-256-GCM encrypted with DEK

### Usage

```python
# TODO: Add encryption service code example
```

---

## BAA Lifecycle

> **TODO:** Document BAA template, generation, signing, and export.

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{ org_name }}` | Covered entity name |
| `{{ ba_name }}` | Business associate name |
| `{{ effective_date }}` | Agreement effective date |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/hipaa/baa/generate` | Generate BAA from template |
| GET | `/api/v1/hipaa/baa/{id}` | Get agreement details |
| GET | `/api/v1/hipaa/baa/{id}/export` | Export as PDF or Markdown |
| GET | `/api/v1/hipaa/baa` | List all agreements |

### Immutability

> **TODO:** Explain that signed agreements cannot be modified — only read or exported.

---

## Compliance Dashboard

> **TODO:** Document dashboard API endpoints and HTML page.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/hipaa/compliance/summary` | Aggregated compliance metrics |
| GET | `/api/v1/hipaa/compliance/phi-stats` | PHI detection statistics |
| GET | `/api/v1/hipaa/compliance/activity` | Recent audit entries |
| GET | `/api/v1/hipaa/compliance` | HTML dashboard page |

### Dashboard HTML

> **TODO:** Describe the Chart.js dashboard, summary cards, and activity table.

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HIPAA_MASTER_KEY` | — | Master Encryption Key (32-byte hex or base64) |
| `HIPAA_PHI_PATTERNS_PATH` | `hipaa/phi_patterns.json` | Path to PHI patterns JSON |
| `HIPAA_AUDIT_LOG_DIR` | `data/audit_logs/` | Audit log storage directory |
| `HIPAA_AUDIT_RETENTION_DAYS` | `2190` | Log retention (6 years) |
| `HIPAA_ENCRYPTION_ENABLED` | `true` | Enable/disable encryption |
| `HIPAA_LLM_VALIDATION_ENABLED` | `true` | Enable/disable LLM validation pass |
| `HIPAA_BAA_DEFAULT_DAYS` | `365` | Default BAA effective period |

### HIPAAConfig Dataclass

> **TODO:** Document the HIPAAConfig dataclass fields.

---

## Troubleshooting

### Common Issues

1. **"Encryption key not found"**
   - Ensure `HIPAA_MASTER_KEY` env var is set
   - Check that the KEK is exactly 32 bytes (when hex-encoded: 64 hex chars)

2. **PHI patterns not matching**
   - Verify `phi_patterns.json` is valid JSON
   - Check the file path matches `HIPAA_PHI_PATTERNS_PATH`
   - Patterns are hot-reloadable: call `PHIRedactor.reload_patterns()`

3. **Audit log not writing**
   - Check directory permissions for `HIPAA_AUDIT_LOG_DIR`
   - Verify disk space is not full

4. **Dashboard shows no data**
   - Ensure at least one PHI scan has been performed
   - Check that audit logging is enabled

5. **PDF export fails**
   - Ensure `weasyprint` is installed
   - Check agreement ID is valid

> **TODO:** Add more troubleshooting entries.

---

## HIPAA Compliance Checklist

- [ ] PHI Redaction configured for all 18 HIPAA identifier categories
- [ ] Audit logging enabled with 6-year retention
- [ ] Encryption at rest enabled with per-tenant keys
- [ ] `HIPAA_MASTER_KEY` environment variable set and backed up
- [ ] BAA template customized for your organization
- [ ] Signed BAA agreements stored immutably
- [ ] Compliance dashboard accessible to compliance officer
- [ ] `MeetingMode.HEALTHCARE` toggle works alongside new HIPAA features
- [ ] No plaintext secrets in logs or API responses
- [ ] All async operations have timeout handling (30s default)
