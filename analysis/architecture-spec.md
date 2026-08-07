# PM Tool Adapter Architecture — Jira / Linear / Asana / Todoist Sync

**Version**: 2.0
**Date**: 2026-08-07
**Status**: Approved (replaces v1.0 Google Calendar spec, which is preserved at `analysis/architecture-gcal-v1.md`; the integration remains live)
**Project**: MeetingNotesAI v1.1.2 → v1.2.0
**Consumers**: pre-tester (`tests/test_pm_adapters.py`), backend developer (`src/meeting_notes_ai/services/integrations/`), frontend developer (`frontend/src/workspace/ActionCenter.tsx`, `IntegrationsCenter.tsx`), tester, tech-lead, release-manager, documenter.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Module Layout](#2-module-layout)
3. [Adapter Interface](#3-adapter-interface)
4. [Provider Credential Flows](#4-provider-credential-flows)
5. [Data Model & Persistence](#5-data-model--persistence)
6. [API Contract](#6-api-contract)
7. [Idempotency](#7-idempotency)
8. [Error & Retry Behavior](#8-error--retry-behavior)
9. [Frontend Contract](#9-frontend-contract)
10. [Backward Compatibility](#10-backward-compatibility)
11. [Configuration & Environment](#11-configuration--environment)
12. [Testing Strategy](#12-testing-strategy)
13. [Implementation Order](#13-implementation-order)
14. [ADR Summary](#14-adr-summary)
15. [Open Questions](#15-open-questions)

---

## 1. Overview

MeetingNotesAI extracts action items with owners and deadlines from meetings.
Today the Action Center stops at a facade: `POST /actions/{id}/queue`
(workspace.py:300) mints `adapter_job_id=uuid4()` and never calls an external
API, and every connector reports `connected: False, mode: adapter_required`
(workspace.py:39). This spec replaces the facade for **Jira, Linear, Asana,
and Todoist** with real provider calls, real stored credentials, and a real
`task-synced` end state in the UI.

The design reuses the proven in-repo patterns:

- `services/google_calendar.py` — OAuth2 `get_authorization_url` /
  `exchange_code` / `refresh_token` lifecycle, `asyncio.to_thread` for sync
  SDK calls, `TokenExpiredError` → 401 "re-authorize".
- `services/token_encryption.py` — AES-256-GCM envelope encryption
  (`TokenEncryptor().encrypt/decrypt`) for every stored credential.
- `db/models.py` `GoogleCalendarToken` / `OAuthState` — per-user credential
  rows and short-lived CSRF state tokens with TTL + purge-on-read.
- `routes/workspace.py` — JSON-file workspace document, `_find`,
  `_audit`, `get_current_user` auth, `workspaceRequest` client.

### Scope

- Real task creation in Jira / Linear / Asana / Todoist from the Action Center.
- Real credential flows per provider (API key / PAT / REST token / Jira OAuth2),
  encrypted at rest, per user.
- `POST /actions/{id}/queue` performs a real provider call, persists
  `external_id` + `external_url`, and is idempotent per meeting+action.
- `GET /integrations` reports real connection state (provider, account,
  URL, token expiry).
- Action Center UI: "Sync to {provider}", external link, `task-synced`.

### Out of scope (future work)

- Bidirectional sync / webhooks from providers (task status changes → app).
- Updating or closing provider tasks from the app.
- Team/org-wide credential sharing (each user connects their own account).
- Salesforce, Slack, Microsoft Planner real sync (legacy facade preserved for them).

### Non-goals / hard rules

- No fake `adapter_job_id` minting for the four PM providers.
- 409 stays only for truly unconnected adapters — never for provider API errors.
- Provider API errors never leak raw upstream messages into `detail` (HIPAA/PHI
  hygiene: upstream bodies may echo user-supplied text).
- No new runtime dependency: `httpx` (already a dependency) is the HTTP client
  for all four providers.

---

## 2. Module Layout

```
src/meeting_notes_ai/services/integrations/
├── __init__.py            # public exports: Adapter, PMAdapterError, registry, get_adapter
├── base.py                # Adapter ABC + AdapterAuth dataclass + create_task result model
├── jira.py                # JiraAdapter
├── linear.py              # LinearAdapter
├── asana.py               # AsanaAdapter
├── todoist.py             # TodoistAdapter
└── registry.py            # PROVIDER_REGISTRY, get_adapter(name), provider metadata (labels, scopes, required env)
```

Route layer additions:

```
src/meeting_notes_ai/routes/workspace.py   # queue_action rewrite + connect/disconnect + GET /integrations
src/meeting_notes_ai/routes/integrations.py # NEW router mounted at /api/v1/integrations
```

Shared helpers:

- `services/token_encryption.py` — unchanged; `TokenEncryptor` reused.
- `services/http_client.py` — NEW tiny factory: `get_http_client()` returning
  a shared `httpx.AsyncClient` (timeout 15s, `follow_redirects=True`), plus a
  `ProviderHTTPError` exception carrying `status_code`, `provider`, and a
  **sanitized** message. Keeps transport mocking trivial (one seam) and avoids
  per-call client churn.

DB additions (`db/models.py`):

```
class PMIntegrationToken(Base, TimestampMixin):
    __tablename__ = "pm_integration_tokens"
    id: str (UUID pk, default uuid4)
    user_id: str (FK users.id, index)
    provider: str            # "jira" | "linear" | "asana" | "todoist"
    encrypted_credentials: Text   # JSON blob encrypted with TokenEncryptor
    account_email: str = ""       # display only; never secret
    account_url: str = ""         # e.g. site base URL / workspace URL
    token_expires_at: DateTime(timezone=True) | None
    is_active: bool = True
    disconnected_at: DateTime(timezone=True) | None
    UniqueConstraint("user_id", "provider")
```

Rules:

- One active row per (user, provider). Reconnect = upsert on that key.
- Disconnect = soft delete (`is_active=False`, `disconnected_at=now`),
  mirroring `GoogleCalendarToken`.
- No new migration file: add the table via `Base.metadata.create_all` on the
  existing SQLite/Postgres path (the codebase already uses create_all for
  `GoogleCalendarToken`); document it.
- A single alembic revision may be added later by release-manager; not required
  for this task (schema_version bump of the workspace JSON doc **is** required —
  see §5).

---

## 3. Adapter Interface

### 3.1 `AdapterAuth`

```python
@dataclass(frozen=True)
class AdapterAuth:
    """Parsed, decrypted credentials handed to an adapter by the route layer.

    Each provider stores exactly one secret string in its credential blob:
      jira    -> access token (OAuth2 Bearer)      | plus site_url, email
      linear  -> API key (Bearer)                  | plus workspace_url
      asana   -> PAT (Bearer)                      | plus default_workspace_gid
      todoist -> REST token (Bearer)               | (account url derived)
    """
    provider: str
    token: str                       # decrypted secret, never persisted again
    site_url: str = ""               # jira: https://<site>.atlassian.net
    email: str = ""                  # jira/linear/asana display account
    workspace_url: str = ""          # linear: https://<workspace>.linear.app
    default_project: str = ""        # optional default project id/gid
```

### 3.2 `Adapter` ABC

```python
class Adapter(ABC):
    provider: ClassVar[str]            # "jira" | "linear" | "asana" | "todoist"
    display_name: ClassVar[str]        # "Jira" | "Linear" | "Asana" | "Todoist"
    auth_type: ClassVar[str]           # "oauth2" | "api_key" | "pat" | "rest_token"
    connect_timeout: ClassVar[float] = 15.0

    @abstractmethod
    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate credentials with a lightweight provider call.

        Returns identity + account URL for GET /integrations.
        Raises PMAdapterError on invalid/expired credentials (401/403),
        AdapterUnavailableError on provider outages (5xx/timeouts).
        """

    @abstractmethod
    async def create_task(self, action: dict[str, Any], project: str | None = None,
                          idempotency_key: str | None = None) -> AdapterTaskResult:
        """Create a real task in the provider.

        action: workspace action dict (id, title, owner, due, meeting_id, meeting, ...)
        project: provider project id/key/gid (None -> provider default)
        idempotency_key: "<meeting_id>:<action_id>" (see §7); None = no header
        """

    async def healthcheck(self, auth: AdapterAuth) -> bool:
        """Optional; default True. Implementations may probe /status."""
```

### 3.3 Result types

```python
@dataclass(frozen=True)
class AdapterConnection:
    account_email: str
    account_url: str
    token_expires_at: str | None = None   # ISO-8601 UTC; None = non-expiring token

@dataclass(frozen=True)
class AdapterTaskResult:
    external_id: str      # provider's native task id (Jira issue key, Linear UUID,
                          # Asana task gid, Todoist task id)
    external_url: str     # https link a human can open
    raw: dict[str, Any] = field(default_factory=dict)  # provider response, for tests/debug
```

### 3.4 Registry

```python
PROVIDER_REGISTRY: dict[str, type[Adapter]] = {
    "jira": JiraAdapter, "linear": LinearAdapter,
    "asana": AsanaAdapter, "todoist": TodoistAdapter,
}

def get_adapter(provider: str) -> Adapter: ...   # raises KeyError -> route maps to 404

PM_PROVIDERS = frozenset({"jira", "linear", "asana", "todoist"})
```

### 3.5 Exceptions

```python
class PMAdapterError(Exception):          # base; message is ALWAYS safe to show
class AdapterAuthError(PMAdapterError):   # 401/403 -> HTTP 401 "re-authorize"
class AdapterUnavailableError(PMAdapterError):  # 5xx/timeout -> HTTP 502 friendly retry
class AdapterValidationError(PMAdapterError):   # 400/422 (bad project, missing field) -> HTTP 422
class AdapterNotFoundError(PMAdapterError):     # unknown provider -> HTTP 404
```

Every adapter maps provider responses through `ProviderHTTPError` →
one of the above. **Never** raise a raw `httpx.HTTPError` or `ProviderHTTPError`
out of an adapter — the route layer only knows the `PMAdapterError` family.

### 3.6 Why this interface

- `connect(auth)` and `create_task(action, project)` are the exact signatures
  the parent task mandates and the pre-tester will assert.
- Adapters are stateless objects; the route layer owns decryption and passes
  `AdapterAuth`. This keeps adapters trivially unit-testable with transport
  mocks and avoids hidden DB state inside adapters.
- `idempotency_key` is a parameter (not adapter state) so the route layer can
  derive it from the workspace document without coupling adapters to the doc.

---

## 4. Provider Credential Flows

### 4.1 Jira — OAuth2 (authorization code) with JWT-basic fallback

Primary: **OAuth2 authorization-code** (Atlassian). Admin-created OAuth
consumer → client id/secret at `https://<site>.atlassian.net/plugins/servlet/ac/...`
per site. Cloud OAuth2 (marketplace-style) is an acceptable alternative when a
site-level consumer is unavailable; both share the same endpoints.

- Auth URL (per site):
  `https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id={id}&scope=read:jira-user+read:jira-work+write:jira-work+offline_access&redirect_uri={redirect}&state={state}&prompt=consent`
- Token exchange (per site): `POST https://auth.atlassian.com/oauth/token`
  with `grant_type=authorization_code`, `code`, `client_id`, `client_secret`,
  `redirect_uri`.
- Refresh: same endpoint, `grant_type=refresh_token`.
- Base URL resolution: `GET https://api.atlassian.com/oauth/token/accessible-resources`
  with the access token → `[{id, url, name}]`; store `url` as `site_url`
  (e.g. `https://acme.atlassian.net`).
- API: `GET/POST {site_url}/rest/api/3/...` with `Authorization: Bearer {token}`.
- Token expiry: access tokens ~1h; store `token_expires_at`, auto-refresh with
  a 5-minute margin exactly like `google_calendar.py` (`REFRESH_MARGIN_SECONDS`).
- `connect()`: `GET {site_url}/rest/api/3/myself` → `{accountId, emailAddress, displayName}`.
- `create_task()`: `POST {site_url}/rest/api/3/issue`
  ```json
  { "fields": { "project": {"key": "<project>"},
                "summary": "<action title>",
                "description": "<generated description>",
                "issuetype": {"name": "Task"},
                "assignee": {"accountId": "<owner account id or null>"},
                "duedate": "<YYYY-MM-DD or null>" } }
  ```
  → `201 {"id": "...", "key": "ACME-123", "self": "..."}`;
  `external_url = f"{site_url}/browse/{key}"`.
- `idempotency_key` → header `X-Idempotency-Key` (Jira accepts it; safe to send).

Fallback (documented, admin-configured only): **JWT basic auth** for Jira
Server/DC — `Authorization: Basic base64(email:api_token)`, API token from
`https://id.atlassian.com/manage-profile/security/api-tokens`, base URL from
env `JIRA_SITE_URL`. Chosen when the credential blob contains `api_token`
instead of an OAuth token. Same `rest/api/3` calls; no expiry (`token_expires_at=None`).

### 4.2 Linear — API key (personal)

- Key from Linear app → Settings → Security & access → Personal API keys.
- API: `POST https://api.linear.app/graphql` with `Authorization: {key}` (no
  "Bearer" prefix — Linear accepts the raw key).
- `connect()`: `POST /graphql` `{ viewer { id name email } organization { urlKey } }`
  → account_email, `workspace_url = https://{urlKey}.linear.app`.
- `create_task()`: GraphQL mutation
  ```graphql
  mutation CreateIssue($input: IssueCreateInput!) {
    issueCreate(input: $input) { success issue { id identifier url } } }
  ```
  variables:
  ```json
  { "input": { "teamId": "<project>",
               "title": "<action title>",
               "description": "<generated description>",
               "assigneeId": "<owner id or null>",
               "dueDate": "<YYYY-MM-DD or null>" } }
  ```
  → `issue.id` (UUID) → `external_id`; `issue.url` → `external_url`.
  `project` = **teamId** (Linear teams are the project scope).
- `idempotency_key` → header `Idempotency-Key` (Linear API v1+ supports it).
- Tokens never expire (`token_expires_at=None`).

### 4.3 Asana — Personal Access Token (PAT)

- PAT from Asana developer console (`https://app.asana.com/0/my-apps` → Create
  new token). Scopes are implicit on the PAT; no OAuth needed for v1.
- API: `https://app.asana.com/api/1.0/...` with `Authorization: Bearer {pat}`.
- `connect()`: `GET /users/me` → `{data: {gid, email, name}}`; also fetch
  `GET /workspaces` → store first workspace gid as `default_project`.
- `create_task()`: `POST /tasks` with
  `{ "data": { "workspace": "<workspace gid>", "projects": ["<project gid>"] (if given),
               "name": "<action title>", "notes": "<generated description>",
               "assignee": "<owner gid or null>", "due_on": "<YYYY-MM-DD or null>" } }`
  → `201 {"data": {"gid": "...", "permalink_url": "..."}}` →
  `external_id = gid`, `external_url = permalink_url`.
- `idempotency_key` → header `Idempotency-Key` (Asana supports it, 48h window).
- Tokens never expire (`token_expires_at=None`).

### 4.4 Todoist — REST token

- Token from Todoist app → Settings → Integrations → API token.
- API: `https://api.todoist.com/rest/v2/...` with `Authorization: Bearer {token}`.
- `connect()`: `GET /projects` (and `GET /user` for email) →
  account_email, `account_url = https://todoist.com`.
- `create_task()`: `POST /tasks`
  ```json
  { "content": "<action title>",
    "description": "<generated description>",
    "project_id": "<project id or null>",
    "due_string": "<owner due or null>",
    "due_lang": "en" }
  ```
  → `200 {"id": "...", "url": "https://todoist.com/showTask?id=..."}` →
  `external_id = id`, `external_url = url`.
- `idempotency_key` → header `X-Idempotency-Key` (Todoist REST v2 honors it).
- Tokens never expire (`token_expires_at=None`).

### 4.5 Credential flow state machine (all providers)

```
[idle] --POST /integrations/{provider}/auth--> [awaiting_callback]   (oauth2 only)
        --POST /integrations/{provider}/connect {credentials}--> [connected]

[awaiting_callback] --GET /integrations/{provider}/callback?code=&state=--> [connected]

[connected] --POST /integrations/{provider}/disconnect--> [idle]

[connected] --connect() 401/403--> [needs_reauth]  (auth_error: true, 401 on API calls)
```

- **API-key providers (linear, asana, todoist)**: single step. Frontend shows
  an inline form (key/PAT/token input + optional default project), submits to
  `POST /integrations/{provider}/connect`, backend calls `connect(auth)` to
  validate, stores encrypted, returns the connection.
- **OAuth2 provider (jira)**: two steps. `POST /integrations/jira/auth` returns
  `authorization_url` + `state` (state persisted in `OAuthState` with
  `provider="jira"`); callback exchanges, resolves `site_url`, stores tokens,
  flips the workspace doc to connected.
- **JWT-basic fallback (jira)**: single step like the API-key providers, via
  `POST /integrations/jira/connect` with `{credentials: {api_token, email, site_url}}`.
- Connect is **idempotent**: re-connecting overwrites the credential row and
  workspace doc entry (upsert semantics).

---

## 5. Data Model & Persistence

### 5.1 Workspace document (`data/workspace_state.json`, schema_version 2 → 3)

The `_seed_workspace` integrations dict (workspace.py:38-41) changes to a
canonical catalog. **Existing keys are preserved**; the four PM providers gain
real state, the three legacy connectors keep the old shape.

```json
"integrations": {
  "Jira":      {"connected": false, "provider": "jira",      "mode": "adapter_required"},
  "Linear":    {"connected": false, "provider": "linear",    "mode": "adapter_required"},
  "Asana":     {"connected": false, "provider": "asana",     "mode": "adapter_required"},
  "Todoist":   {"connected": false, "provider": "todoist",   "mode": "adapter_required"},
  "Microsoft Planner": {"connected": false, "mode": "adapter_required"},
  "Salesforce":        {"connected": false, "mode": "adapter_required"},
  "Slack":             {"connected": false, "mode": "adapter_required"}
}
```

Connected PM entries additionally carry (written on connect, cleared on
disconnect):

```json
"Jira": {
  "connected": true, "provider": "jira", "mode": "adapter_required",
  "account_email": "maya@acme.com", "account_url": "https://acme.atlassian.net",
  "token_expires_at": "2026-08-07T10:00:00+00:00"
}
```

The DB row (`pm_integration_tokens`) is the **source of truth** for credentials;
the workspace doc mirrors connection metadata for the UI and the existing
`GET /integrations` contract. `_read_document` upgrades v2 → v3 on read
(backfill the four PM entries if absent; never drop legacy keys).

### 5.2 Action record

`queue_action` (and `create_meeting` seeding, workspace.py:240) adds two fields
to every action dict:

```json
"external_id":  null,     // already seeded
"external_url": null,     // NEW
```

`adapter_job_id` is **removed** from the write path for the four PM providers
(legacy connector path may keep it). `sync_state` is derived, never stored:
`queued` + `external_id` set ⇒ `task-synced`.

### 5.3 Migrations

- `pm_integration_tokens` table: `Base.metadata.create_all` path (matches
  `GoogleCalendarToken`); optional alembic revision deferred to release-manager.
- Workspace JSON doc: schema_version 2 → 3 with read-time backfill (§5.1).
- No columns change on existing tables.

---

## 6. API Contract

All routes below are under `get_current_user`; all bodies are JSON; all
timestamps ISO-8601 UTC. Provider identifiers are **lowercase slugs**
(`jira`, `linear`, `asana`, `todoist`) in path params, while the workspace
doc/UI keeps display names (`Jira`, ...). Route layer maps both directions.

### 6.1 `GET /api/v1/workspace/integrations` (unchanged path, new shape)

Response — `200`:

```json
{
  "items": {
    "Jira": {
      "connected": true,
      "provider": "jira",
      "mode": "adapter_required",
      "account_email": "maya@acme.com",
      "account_url": "https://acme.atlassian.net",
      "token_expires_at": "2026-08-07T10:00:00+00:00"
    },
    "Linear":   { "connected": false, "provider": "linear", "mode": "adapter_required" },
    "Asana":    { "connected": false, "provider": "asana",  "mode": "adapter_required" },
    "Todoist":  { "connected": false, "provider": "todoist","mode": "adapter_required" },
    "Microsoft Planner": { "connected": false, "mode": "adapter_required" },
    "Salesforce":        { "connected": false, "mode": "adapter_required" },
    "Slack":             { "connected": false, "mode": "adapter_required" }
  }
}
```

- `connected` mirrors the **DB row** (`is_active`), not just the doc flag —
  re-read the token table so a revoked/replaced credential is reflected.
- `token_expires_at` null for non-expiring tokens (linear/asana/todoist,
  jira-basic); present for jira-oauth2.
- Legacy connectors (Planner/Salesforce/Slack) keep `{connected, mode}` only.

### 6.2 `POST /api/v1/workspace/integrations/{name}/connect` (extended)

Backward-compatible: `{"enabled": true|false}` still works **for legacy
connectors** (Planner/Salesforce/Slack) exactly as today.

For the four PM providers, body:

```json
{ "credentials": { "token": "<api key / PAT / REST token / jira api_token>",
                   "site_url": "https://acme.atlassian.net",      // jira-basic only
                   "email": "maya@acme.com",                      // jira-basic only
                   "default_project": "PROJ" } }                  // optional
```

Behavior:

1. Resolve adapter; unknown provider → `404 {"detail": "Integration not found"}`.
2. `auth = AdapterAuth(provider, token, site_url, email, default_project)`.
3. `await adapter.connect(auth)`:
   - success → upsert `pm_integration_tokens` (encrypted blob =
     `TokenEncryptor().encrypt(json.dumps({token, site_url, email}))`), update
     doc entry (`connected=true`, account fields), audit
     `integration.changed`, return `201`:
     ```json
     { "name": "Jira", "provider": "jira", "connected": true,
       "account_email": "...", "account_url": "...",
       "token_expires_at": null }
     ```
   - `AdapterAuthError` → `401 {"detail": "Invalid or expired credentials for Jira. Reconnect your account."}`
   - `AdapterUnavailableError` → `502 {"detail": "Jira is temporarily unavailable. Try again in a few minutes."}`
   - `AdapterValidationError` → `422 {"detail": "..."}`
4. `{"enabled": false}` on a PM provider → disconnect (§6.4).
5. `{"enabled": true}` on a PM provider **without** credentials →
   `422 {"detail": "Credentials required to connect Jira"}` (never flips the flag).

### 6.3 OAuth2 (Jira) endpoints — `routes/integrations.py`

`POST /api/v1/integrations/jira/auth` → `200`:

```json
{ "authorization_url": "https://auth.atlassian.com/authorize?...",
  "state": "<opaque csrf>" }
```

State persisted in `OAuthState` (add `provider` column, default `"google_calendar"`
for existing rows) with 10-minute TTL, consumed on callback, purged on read —
exactly the `google_calendar.py` helpers.

`GET /api/v1/integrations/jira/callback?code=...&state=...` → `200`:

```json
{ "connected": true, "provider": "jira",
  "account_email": "maya@acme.com",
  "account_url": "https://acme.atlassian.net",
  "token_expires_at": "2026-08-07T10:00:00+00:00" }
```

Errors: bad/expired state → `400`; code exchange failure → `400`
("Failed to exchange authorization code"); refresh failure later →
`401` ("Jira token expired. Please re-authorize.").

### 6.4 `POST /api/v1/workspace/integrations/{name}/disconnect`

```json
{ "name": "Jira", "provider": "jira", "connected": false }
```

Soft-deletes the DB row (`is_active=False`), clears the doc entry back to
`connected:false` + account fields removed, audits `integration.changed`.
Idempotent: disconnecting an unconnected provider returns the same `200`.
Legacy connectors accept this endpoint too (maps to `enabled:false`).

### 6.5 `POST /api/v1/workspace/actions/{action_id}/queue` (rewritten)

Request — unchanged: `{"destination": "Jira"}` (display name) — the UI sends
the display name; the route maps it via the doc catalog to `provider: "jira"`.
`{"destination": "jira"}` (slug) is also accepted (normalize case-insensitively,
strip spaces: `"Microsoft Planner"` → legacy).

Response — `200` (task created):

```json
{
  "id": "a1b2...", "title": "Ship the Q3 report", "owner": "Maya",
  "due": "2026-08-12", "meeting_id": "m-123", "meeting": "Q3 planning",
  "timestamp": "00:00", "status": "queued", "destination": "Jira",
  "external_id": "ACME-123", "external_url": "https://acme.atlassian.net/browse/ACME-123",
  "sync_state": "task-synced"
}
```

Behavior (exact order):

1. Load action; missing → `404`.
2. Resolve destination → provider. Unknown destination →
   `422 {"detail": "Unknown destination 'X'"}`.
3. **Legacy connector** (Planner/Salesforce/Slack): preserve today's behavior
   exactly — if `connected` false → `409`; else set
   `{destination, status:"queued", external_id:null, adapter_job_id:uuid4()}`
   and return (keeps `test_workspace_api_v102.py::test_actions_require_connected_adapter_and_are_not_fake_synced` green).
4. **PM provider**: load `pm_integration_tokens` row for
   `(user_id, provider)` with `is_active=True`.
   - No row → `409 {"detail": "Connect Jira before syncing this action"}`.
     **This is the ONLY 409 left for PM providers.**
   - Decrypt credentials; build `AdapterAuth` (+ `default_project` from the
     stored blob or the request's optional `project` field — see below).
5. **Idempotency pre-check** (see §7): if `action.external_id` is already set
   AND `action["external_id"]` matches the stored `sync_key`, return the action
   with `200` **without** calling the provider (and without 409).
6. Build `idempotency_key = f"{action['meeting_id']}:{action['id']}"`.
7. `await adapter.create_task(action, project=..., idempotency_key=...)` inside
   `asyncio.timeout(30)`.
   - Timeout/`AdapterUnavailableError` → `502` friendly message, `status` stays
     unchanged, nothing persisted — the user can retry (§8).
   - `AdapterAuthError` → `401` + mark the integration doc entry
     `auth_error: true` (frontend offers "Reconnect").
   - `AdapterValidationError` → `422`.
8. Success → persist `action.update(external_id=..., external_url=...,
   destination=..., status="queued")`, store
   `sync_key = f"{meeting_id}:{action_id}"` on the action, audit
   `action.synced {destination, external_id}`, write doc, return `200` with
   the full action (including `sync_state: "task-synced"`).

Optional request extension (not required by the pre-tester, keep optional):
`{"destination": "Jira", "project": "ACME"}` overrides the stored default
project for this one call.

Error table:

| Case | Status | detail |
|---|---|---|
| action not found | 404 | "Action not found" |
| unknown destination | 422 | "Unknown destination 'X'" |
| legacy connector, unconnected | 409 | "Connect an adapter before queuing this action" |
| PM provider, no credential row | 409 | "Connect Jira before syncing this action" |
| credentials expired/revoked | 401 | "Jira token expired. Please re-authorize." |
| provider 5xx / timeout / network | 502 | "{Provider} is temporarily unavailable. Try again in a few minutes." |
| provider 400/422 (bad project etc.) | 422 | sanitized, friendly message |
| duplicate idempotent re-sync | 200 | returns existing action untouched |

### 6.6 `GET /api/v1/workspace/actions` (unchanged path, extended item)

Action items now include `external_url` and `sync_state`; the route reads the
doc as today, so no code change beyond the seed in §5.2. UI consumes
`external_url` to render the link and `sync_state` for the pill.

---

## 7. Idempotency

- **Key**: `f"{action['meeting_id']}:{action['id']}"` — meeting id + action id.
- **Transport**: sent as the provider's idempotency header (§4) on every
  create call, so even a retry after a lost response cannot create a duplicate
  provider task.
- **App-level guard**: the action stores `sync_key` when a task is created.
  Before calling the provider, `queue_action` checks: if
  `action.get("sync_key") == idempotency_key and action.get("external_id")`,
  return the existing action with `200` — no provider call, no 409.
- This makes the endpoint naturally idempotent for the same meeting+action and
  **safe for the UI retry button** (double-click, network retry, re-sync).
- Different meeting or different action ⇒ different key ⇒ independent tasks.

---

## 8. Error & Retry Behavior

1. **Friendly messages**: every provider error is mapped to a sanitized
   `detail` (never raw upstream body — may echo user content / PHI). Map:
   - 401/403 → 401 re-authorize (auth_error flag set for UI)
   - 5xx / timeout / connection error → 502 "temporarily unavailable"
   - 400/422 → 422 with a human hint ("Check the project key in your Jira
     settings")
2. **Retry semantics**:
   - Client retries the same `POST /actions/{id}/queue` freely — idempotency
     (§7) guarantees no duplicates.
   - Backend retries transient provider failures **once** with a 1.5s
     exponential backoff inside the adapter for 5xx/timeouts; still failing →
     `AdapterUnavailableError` → 502.
   - Never auto-retry 401/403 (re-auth required) or 400/422 (user error).
3. **UI**: on 502/422 the button stays enabled with the friendly message and a
   "Try again" action; on 401 the UI offers "Reconnect {provider}".
4. **Audit**: every provider call outcome is audited
   (`action.synced`, `action.sync_failed {reason}`) so failures are visible in
   the compliance/audit trail.

---

## 9. Frontend Contract

### 9.1 `ActionCenter.tsx` — "Queue for adapter" → "Sync to {provider}"

Current dead button (line 6, one-liner component):
`i.status==='suggested' ? Confirm : i.status==='queued' ? <span>{external_id}</span> : Queue for adapter`

New rendering per action card (keep the component's compact style):

- `status === 'queued' && external_url` →
  `<a href={external_url} target="_blank" rel="noreferrer">View in {provider}</a>`
  and the status pill renders `task-synced` (via `sync_state`).
- `status === 'queued' && !external_url` (legacy path) → keep the current
  `<span>{external_id}</span>` fallback.
- `status === 'confirmed'` →
  `<button className="primary" onClick={() => sync(i)}>Sync to {i.destination}</button>`
  (label derived from the action's `destination` display name; default
  "Sync to provider" if unset).
- `status === 'suggested'` → unchanged Confirm button.

`sync(i)` becomes:

```ts
const sync = async (i: WorkAction) => {
  setSyncingId(i.id); setError('');
  try {
    const updated = await workspaceRequest<WorkAction>(`/actions/${i.id}/queue`, {
      method: 'POST',
      body: JSON.stringify({ destination: i.destination }),
    });
    setItems(prev => prev.map(a => a.id === i.id ? updated : a));  // external_url + task-synced
  } catch (e) {
    setError(friendlyMessage(e));   // e.message is already the sanitized backend detail
  } finally { setSyncingId(null); }
};
```

- `friendlyMessage` shows `e.message` (backend sanitized) plus a **"Try again"**
  button that re-invokes `sync(i)`; for 401 messages it shows "Reconnect {provider}".
- `WorkAction` interface grows: `external_url?: string|null; sync_state?: string;`
  (keep `external_id`).
- Disable the button while `syncingId === i.id` (label "Syncing…").
- On 401 the user is routed to the IntegrationsCenter via existing nav.

### 9.2 `IntegrationsCenter.tsx` — real connect UX

- Catalog from `GET /integrations` now carries `provider`, `account_email`,
  `account_url`, `token_expires_at` for the four PM providers.
- PM cards render a **Connect form** (inline, per card):
  - linear → one input "Linear API key"
  - asana → one input "Asana personal access token"
  - todoist → one input "Todoist REST API token"
  - jira → button "Connect with Atlassian" (OAuth2 popup/redirect) **and** an
    optional "Use API token instead" form (token + site URL + email)
  - all → optional "Default project/team" input (jira key / linear teamId /
    asana workspace or project gid / todoist project id)
  - Submit → `POST /integrations/{provider}/connect` with
    `{credentials: {...}}`; on success re-load catalog; on 401/422 show the
    friendly detail inline.
- Connected PM cards show `account_email`, `account_url` (linked), and
  `token_expires_at` ("expires …" / "never") plus a Disconnect button
  (`POST /integrations/{provider}/disconnect`).
- Legacy cards keep the current toggle (unchanged).

### 9.3 `workspace.ts` client

No change required — `workspaceRequest` already surfaces `detail` from error
responses, which is exactly the friendly-message channel.

### 9.4 Status pill mapping

`sync_state` values: `pending` (default/absent), `task-synced` (queued +
external_id set). CSS class `task-synced` must be styled (reuse `task-queued`
styles + accent color). No new backend status values.

---

## 10. Backward Compatibility

| Constraint | Mechanism |
|---|---|
| `test_workspace_api_v102.py:80` legacy queue 409 + fake sync | §6.5 step 3: legacy connectors keep old behavior verbatim (doc-flag `connected`, `adapter_job_id`) |
| `test_workspace_api_v102.py:124` `GET /integrations` 200 + Unknown connect 404 | path and error unchanged; unknown name still 404 |
| Existing `POST /integrations/{name}/connect {"enabled": bool}` | still works for legacy; PM providers with `enabled:true` and no credentials → 422 (never silently fake-connect) |
| Workspace JSON schema | v2 → v3 read-time backfill; no data loss |
| `ActionUpdate` / action PATCH | unchanged; new fields additive |
| Google Calendar integration | untouched; spec preserved at `analysis/architecture-gcal-v1.md` |
| Frontend build | additive props only; `tsc -b` must stay green |

---

## 11. Configuration & Environment

`src/meeting_notes_ai/config.py` additions (all optional at runtime; required
only when the corresponding flow is used):

```python
jira_client_id: str = ""            # OAuth2 consumer / marketplace app
jira_client_secret: str = ""
jira_redirect_uri: str = ""         # e.g. https://app.example.com/api/v1/integrations/jira/callback
# JWT-basic fallback:
jira_site_url: str = ""             # optional; overrides per-request site_url
```

Env vars: `JIRA_CLIENT_ID`, `JIRA_CLIENT_SECRET`, `JIRA_REDIRECT_URI`,
`JIRA_SITE_URL`. **No** env vars for linear/asana/todoist — credentials are
user-supplied at connect time and stored encrypted. `TOKEN_ENCRYPTION_KEY`
(or `HIPAA_MASTER_KEY`) already required by `TokenEncryptor`.

Docs (documenter task): `docs/integrations.md` + per-provider setup in
`docs/integrations/` (app creation, scopes, where to find the key, env vars,
troubleshooting), README section, CHANGELOG entry.

---

## 12. Testing Strategy

- **Pre-tester** (`tests/test_pm_adapters.py`, RED before implementation):
  - Interface tests: `JiraAdapter`, `LinearAdapter`, `AsanaAdapter`,
    `TodoistAdapter` exist; `connect`/`create_task` signatures match §3;
    registry maps all four; queue route wired (importable router).
  - Behavioral tests with **transport-level HTTP mocks** (real `httpx` calls
    intercepted — e.g. `respx` or `httpx.MockTransport`; the repo pins `httpx`
    already; if `respx` is needed it must be added to `dev` deps in
    `pyproject.toml`):
    - each provider `create_task` issues the correct request (URL, method,
      headers incl. auth + idempotency key, body) against a mock transport
      and parses `external_id`/`external_url` from the fixture response.
    - `POST /actions/{id}/queue` performs the provider call, persists
      `external_id` + `external_url`, returns `task-synced`.
    - 409 **only** when unconnected; 502 on provider 5xx; 401 on 401.
    - idempotency: second queue with same meeting+action returns 200 without
      a second provider call (mock counts calls).
    - `GET /integrations` reflects real connection state.
  - Stub adapters raising `NotImplementedError` make interface tests pass and
    behavioral tests fail clearly.
- **Backend developer**: run `tests/test_pm_adapters.py` + full suite +
  `ruff`. All HTTP via `get_http_client()` seam so transport mocking is
  one-line.
- **Tester**: full suite; UI E2E smoke + browser-helper visual check on the
  Action Center and Integrations Center.
- Transport mocks only — no `MagicMock`-only adapter tests, no network calls
  in CI.

---

## 13. Implementation Order

1. **pre-tester**: `tests/test_pm_adapters.py` (RED) — do not modify existing
   tests.
2. **backend developer**:
   a. `services/http_client.py` + `services/integrations/base.py` (ABC, auth,
      results, exceptions)
   b. `registry.py`, then `jira.py`, `linear.py`, `asana.py`, `todoist.py`
   c. `db/models.py` `PMIntegrationToken` + `OAuthState.provider`
   d. `routes/integrations.py` (jira auth/callback)
   e. `routes/workspace.py` — seed v3, `GET /integrations`,
      `connect/disconnect`, `queue_action` rewrite
   f. `config.py` settings; run full suite + ruff; commit & push
3. **frontend developer**: `ActionCenter.tsx`, `IntegrationsCenter.tsx`,
   `task-synced` CSS; `tsc -b` green.
4. **tester**: gates + E2E; **tech-lead** review; **release-manager** version
   bump + CHANGELOG; **documenter** docs.

---

## 14. ADR Summary

| # | Decision | Rationale |
|---|---|---|
| ADR-1 | `httpx` (already pinned) as the only HTTP client; shared client factory | no new runtime dep; one transport seam for mocking |
| ADR-2 | Credentials encrypted with existing `TokenEncryptor`, stored per-user in `pm_integration_tokens` | reuse proven AES-256-GCM DEK/KEK pattern; per-user isolation |
| ADR-3 | DB row is source of truth for credentials; workspace doc mirrors metadata | `GET /integrations` keeps its existing JSON shape without leaking secrets |
| ADR-4 | Idempotency key = `meeting_id:action_id`, sent as provider idempotency header + app-level `sync_key` guard | provider-level dedupe + cheap app-level short-circuit; safe retries |
| ADR-5 | 409 reserved for unconnected only; 401/502/422 for provider outcomes | precise semantics; UI can branch on status |
| ADR-6 | Legacy connectors keep the old facade verbatim | existing tests and product surface (Planner/Salesforce/Slack) remain valid |
| ADR-7 | OAuth2 only where it adds value (Jira); API keys/PAT/token for the rest | matches each provider's least-friction supported flow; no forced OAuth complexity |
| ADR-8 | Action status remains `queued`; `sync_state` derived (`task-synced`) | no migration of status values; existing filters keep working |

---

## 15. Open Questions

1. **Jira OAuth2 app type**: site-level OAuth consumer vs marketplace-style
   cloud OAuth2 — both use the same endpoints; pick at implementation based on
   what the deployment admin can create. The connect contract (§6.2) is
   identical either way. JWT-basic fallback covers Server/DC.
2. **`respx` vs `httpx.MockTransport`** for transport mocks: pre-tester
   chooses; both satisfy "transport-level, no MagicMock-only". If `respx`,
   add to `dev` deps.
3. **Default project resolution**: adapters fall back to provider default
   when `project` is None; whether connect() should require an explicit
   project selection in the UI is a UX call for the frontend task (optional
   field, never blocking connect).

---

*End of spec. Downstream tasks (pre-tester `t_b08f029f`, backend `t_fabaed18`,
frontend `t_adf4ff4a`) implement directly from this document; the acceptance
criteria of root task `t_b80833c2` map 1:1 to §3–§9.*
