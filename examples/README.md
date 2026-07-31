# HIPAA Examples

Runnable scripts demonstrating the `meeting_notes_ai.hipaa` library API
(shipped in v0.5.0). Each script is verified to run with the repository
virtualenv.

## Prerequisites

```bash
uv sync
```

Encryption examples need a KEK seed in `HIPAA_MASTER_KEY` (any string — the
32-byte AES key is derived via SHA-256):

```bash
export HIPAA_MASTER_KEY="$(openssl rand -hex 32)"
```

## Running

All commands run from the repository root. The package is not installed into
the venv, so `PYTHONPATH=src` is required (the same mechanism pytest uses):

```bash
# PHI redaction — scan + redact with all four modes, custom patterns, stats
PYTHONPATH=src .venv/bin/python examples/hipaa_phi_redaction.py

# Audit logging — write, query, stats, rotation, export
PYTHONPATH=src .venv/bin/python examples/hipaa_audit_logs.py

# Encryption — per-tenant keys, field/document encryption, master key rotation
HIPAA_MASTER_KEY=dev-master-key PYTHONPATH=src .venv/bin/python examples/hipaa_rotate_key.py

# BAA — generate template, store agreement immutably, export PDF
PYTHONPATH=src .venv/bin/python examples/hipaa_baa_generate.py

# Compliance dashboard — aggregate all modules into a compliance summary
HIPAA_MASTER_KEY=dev-master-key PYTHONPATH=src .venv/bin/python examples/hipaa_compliance_dashboard.py
```

## Feature → script mapping

| Feature area | Script |
|--------------|--------|
| PHI redaction (scan/redact/custom patterns) | `hipaa_phi_redaction.py` |
| Audit logging (query/stats/rotate/export) | `hipaa_audit_logs.py` |
| Encryption key management (provision, encrypt, rotate) | `hipaa_rotate_key.py` |
| BAA template generation & storage | `hipaa_baa_generate.py` |
| Compliance dashboard aggregation | `hipaa_compliance_dashboard.py` |
