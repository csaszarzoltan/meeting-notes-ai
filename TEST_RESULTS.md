# Test Results

## Environment

- Python 3.12.9 via `uv`
- Dependencies installed with `uv sync --dev`
- Test date: 2026-08-01

## TDD workflow

The v0.6 acceptance suite was created before implementation. It initially failed because the workflow policy module did not exist. The minimum workflow implementation was then added, followed by targeted regression passes and refactoring.

Rate limiting, middleware, tier configuration, bcrypt compatibility, and API-key contracts were continued with the same RED → GREEN → refactor approach. Historical `xfail` markers were removed only where the underlying feature was implemented. Remaining `xfail` cases document deliberately deferred integration scenarios.

## Acceptance and targeted regression suite

```bash
.venv/bin/python -m pytest -q -n 0 \
  tests/test_product_workflow_v06.py \
  tests/test_healthcare_mode.py \
  tests/test_phi_redaction.py \
  tests/test_app_v2.py
```

Result: **99 passed**.

## Full repository suite

```bash
.venv/bin/python -m pytest -q -n 0 --tb=short
```

Result: **exit code 0, zero failures** across **842 collected tests**. Expected deferred scenarios remain reported as `xfail` rather than being deleted or hidden.

## Static validation

Ruff passes for all newly added and modified production modules.

## Remaining warnings and gaps

- Starlette currently emits a deprecation warning for its `httpx` TestClient integration.
- Two legacy tests call the asynchronous token factory without awaiting it and therefore emit runtime warnings while remaining expected failures.
- Browser automation and automated WCAG tooling are not part of the original stack. Accessibility is covered with semantic contract tests and manually auditable markup.
- External OpenAI calls stay mocked in deterministic CI.
- The in-memory rate limiter and telemetry collector are single-process implementations. Production multi-instance deployment should use Redis or another shared atomic store.


## Production-readiness continuation

Additional RED-first acceptance tests cover production secret rejection, secure secret acceptance, the local database default, active API-key authentication, invalid-key rejection, and last-used tracking.
