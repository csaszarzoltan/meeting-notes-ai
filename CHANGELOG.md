# Changelog

## [0.3.0] — 2026-07-30

### Features

- **Meeting Sharing** — New `POST /share` endpoint generates shareable links for meetings. Supports configurable expiration (TTL) and manual revocation. Access control: only meeting owner or team members (admin/member) can share; viewers cannot.
- **Public Link Access** — New `GET /public/shares/{token}` endpoint serves meeting data from a share token without requiring authentication. Supports optional password protection (future). Invalid, expired, and revoked tokens return 404.
- **SharedLink DB Model** — New `SharedLink` SQLAlchemy model tracking `meeting_id`, `created_by`, `token` (UUID), `expires_at`, `revoked`, and `created_at` timestamps. Auto-expiration query support.
- **Link Expiration & Revocation** — `DELETE /share/{share_id}` for share owners and team admins to revoke links. `expires_at` field enforces time-based expiration on public access.
- **Share Listing** — `GET /shares` returns paginated share links scoped to the authenticated user's accessible meetings.
- **Public Routes Module** — New `routes/public.py` module for unauthenticated endpoints (token-based meeting access), wired into the app router.
- **Test DB Infrastructure** — `conftest.py` updated with async test DB session fixtures, engine override pattern, and isolated SQLite in-memory database for sharing and public route tests.

### Fixes

- **Timezone comparison bug** in `public.py` — Fixed naive/aware datetime comparison by ensuring `expires_at` comparison uses UTC-aware `datetime.now(timezone.utc)`.
- **Removed .venv from git tracking** — Virtual environment directory removed from version control; `.gitignore` updated.
- **bcrypt/passlib compatibility** — bcrypt 4.x pinned to resolve passlib 1.7.4 crash on new venv installs.
- **17 ruff auto-fixes** — Unused imports cleaned across multiple modules.

### Tests

- **345 tests passing** (0 failures, 0 skipped) — 70 new tests in `test_sharing.py` covering share creation, listing, revocation, public access, expiry, invalid/revoked tokens, team-scoped access control, and edge cases.
- **All acceptance criteria verified** — Meeting Sharing, Public Links, Link Expiration & Revocation, Access Control.

### Docs

- README.md updated with v0.3.0 sharing endpoints, public link usage, and authentication notes.

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
