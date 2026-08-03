# Examples

Runnable scripts demonstrating the `meeting_notes_ai` APIs — the HIPAA
library surface and the live-transcription WebSocket contract. Each script
is verified to run with the repository virtualenv.

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

# REST endpoints — exercise the full /api/v1 HIPAA surface in-process
# (TestClient; faked transcriber, temp audit dir, in-memory DB — no server,
# no OPENAI_API_KEY, no database needed)
HIPAA_MASTER_KEY=dev-master-key PYTHONPATH=src .venv/bin/python examples/hipaa_rest_endpoints.py

# Live transcription WS client — full contract: login -> draft meeting ->
# WebM chunks -> partials -> finalize -> action items (needs a running server)
PYTHONPATH=src .venv/bin/python examples/live_transcription_client.py \
    --email you@example.com --password s3cret --chunks 4

# Live transcription demo server — dev-only; swaps the AI seam for
# deterministic fakes so the /app/live UI runs without OPENAI_API_KEY
PYTHONPATH=src .venv/bin/python examples/live_demo_server.py
```

## Live transcription examples

`live_transcription_client.py` and `live_demo_server.py` implement the
WebSocket contract documented in `docs/LIVE_TRANSCRIPTION.md`. The demo
server exposes the real app at http://127.0.0.1:8000 with the external
STT/LLM calls faked, so the component-based UI (`GET /app/live`) can be
exercised end-to-end without an OpenAI key (login: `demo@example.com` /
`demo1234`).

## Feature → script mapping

| Feature area | Script |
|--------------|--------|
| PHI redaction (scan/redact/custom patterns) | `hipaa_phi_redaction.py` |
| Audit logging (query/stats/rotate/export) | `hipaa_audit_logs.py` |
| Encryption key management (provision, encrypt, rotate) | `hipaa_rotate_key.py` |
| BAA template generation & storage | `hipaa_baa_generate.py` |
| Compliance dashboard aggregation | `hipaa_compliance_dashboard.py` |
| REST endpoints (transcribe, audit-logs*, rotate-key, baa, dashboard) | `hipaa_rest_endpoints.py` |
| Live transcription WS client (full contract flow) | `live_transcription_client.py` |
| Live transcription demo server (fake AI seam, no API key) | `live_demo_server.py` |
