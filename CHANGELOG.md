# Changelog

## [0.2.0] — 2026-07-28

### Features

- **Database & Async SQLAlchemy Engine** — New `db/` module with async SQLAlchemy models for User, Team, TeamMember, Meeting, BatchJob, BatchFileResult, and WebhookSubscription. `init_db` with `create_all` for Railway Postgres provisioning. Alembic-ready structure.
- **JWT Authentication** — Signup/login endpoints with bcrypt password hashing, JWT bearer tokens (24h expiry), `get_current_user` dependency, and `require_team_role` middleware for role-based access (admin/member/viewer).
- **Batch Audio Processing** — `POST /api/v1/batches` accepts up to 10 audio files in a single multipart request. Status progression: pending → processing → completed. Per-file result tracking with partial-failure tolerance.
- **Team Workspace CRUD** — Create team (become admin), invite members, change roles (admin/member/viewer), remove members. All meetings scoped to team.
- **Webhook Notifications** — Register webhook URLs per team. Automatic firing on batch completion with HMAC-SHA256 payload signing and 3-retry exponential backoff.
- **Multi-Format Batch Export** — `GET /api/v1/batches/{batch_id}/export` supporting JSON, Markdown, PDF (weasyprint), and ZIP bundle for `format=all`. Correct Content-Type headers.
- **Route Wiring** — All 6 new routers (auth, batches, teams, webhooks) wired into `main.py` alongside existing health endpoint.

### Fixes

- **auth.py syntax error** — `authorization: str *** Header(...)` changed to `authorization: str = Header(...)`. Would cause SyntaxError at import time.
- **bcrypt 5.0.0 / passlib compatibility** — Pinned `bcrypt<5` (v4.3.0) to resolve passlib 1.7.4 crash. 4 auth tests were failing.
- **Ruff lint compliance** — 17 errors in `src/` and 22 errors in `tests/` auto-fixed (unused imports, line length, import sorting).
- **Dockerfile / railway.toml** — Fixed uv sync ordering, venv-based uvicorn path, PORT env expansion via `sh -c` wrapper.
- **Hatchling build config** — Added `[tool.hatch.build.targets.wheel] packages` for `src/` layout.

### Tests

- **275 tests** passing (0 failures, 0 skipped) — all 112 v0.1.0 regression tests plus 163 new v0.2.0 tests covering DB models, JWT auth, batch processing, team CRUD, webhooks, and PDF/ZIP export.
- **All 5 ACs verified** — Database & Auth, Batch Processing, Team Workspace, Webhooks, Batch Export.

### Docs

- README.md created with project overview, API endpoints, and setup instructions.
