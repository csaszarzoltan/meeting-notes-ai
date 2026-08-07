# PM Tool Integrations — Jira, Linear, Asana, Todoist

MeetingNotesAI can push confirmed action items straight into a project
management tool. Each provider ships as a small adapter that (a) validates
your credentials with a lightweight call, then (b) creates a real task from a
workspace action item when you hit **Sync to {provider}** in the Action Center.

This guide covers:

- How to create the app / obtain the credential for each provider
- The scopes or permissions each credential implies
- Which environment variables matter (and which don't)
- How syncing works end-to-end and how failures surface

The four supported PM providers are **Jira**, **Linear**, **Asana**, and
**Todoist**. Google Calendar is a separate, read/import integration and is
documented in [docs/integrations/google-calendar.md](google-calendar.md).

---

## 1. How it works (one paragraph)

Action items live in a tenant-scoped workspace. When an action is confirmed
with an owner and due date, the Action Center shows a **Sync to {provider}**
button (label derived from the action's `destination`). Clicking it calls

```
POST /api/v1/workspace/actions/{action_id}/queue
{ "destination": "Jira" }
```

The server looks up the encrypted credential you stored when you connected the
provider, calls the provider's API to create a task, and stores the provider's
native `external_id` and an `external_url` back on the action
(`status: "queued"`, `sync_state: "task-synced"`). The UI then renders a
**View in {provider}** link.

Legacy connectors (Microsoft Planner, Salesforce, Slack) keep the old
queue-only behavior and do **not** create real external tasks — they are
journalled locally with `external_id: null` and a generated `adapter_job_id`.

---

## 2. Providers at a glance

| Provider | Credential type | API | Connect validates via | Token expiry |
|---|---|---|---|---|
| Jira | OAuth2 bearer token (+ `site_url`, `email`) | REST API v3 | `GET /rest/api/3/myself` | none (per current token) |
| Linear | Personal API key | GraphQL | `POST /graphql` (viewer + org) | never |
| Asana | Personal Access Token (PAT) | REST API v1 | `GET /users/me` | never |
| Todoist | REST API token | REST API v2 | `GET /projects` | never |

Credentials are stored per-user, encrypted at rest with AES-256-GCM
(`TokenEncryptor`), one row per `(user, provider)` in the
`pm_integration_tokens` table. The database row is the **source of truth** for
credentials; the workspace JSON document only mirrors display metadata
(`account_email`, `account_url`, `token_expires_at`) so the UI never sees a
secret.

### Required environment variables

Only **one** setting is required for PM sync (besides a configured JWT auth
flow, which the rest of the app already requires):

| Var | Required for | Notes |
|---|---|---|
| `STORAGE_ENCRYPTION_KEY` (or `HIPAA_MASTER_KEY`) | **all four providers** | `TokenEncryptor` uses this as the KEK seed to encrypt stored credentials. Without it, connecting fails with `ValueError: TokenEncryptor requires STORAGE_ENCRYPTION_KEY or HIPAA_MASTER_KEY`. |

There are **no** per-provider environment variables for Linear, Asana, or
Todoist — their credentials are user-supplied at connect time and stored
encrypted. The spec also defines optional `JIRA_CLIENT_ID` /
`JIRA_CLIENT_SECRET` / `JIRA_REDIRECT_URI` / `JIRA_SITE_URL` for a Jira OAuth2
browser flow, but **the shipped backend does not implement that flow yet**;
Jira connects with a bearer token + site URL directly (see below).

---

## 3. Creating the credential for each provider

### 3.1 Jira — bearer token (REST API v3)

Two ways to obtain an API token in Atlassian:

- **API token (recommended for the current build):** create one at
  <https://id.atlassian.com/manage-profile/security/api-tokens>. It is used as
  the `token` with a `site_url` like `https://<your-org>.atlassian.net`.
- **OAuth2 access token:** a site/marketplace OAuth2 consumer yields a bearer
  access token. The shipped connect path accepts it the same way — as `token`.

When you connect you must also supply:

- `site_url` — `https://<your-org>.atlassian.net` (required; `connect()` calls
  `GET {site_url}/rest/api/3/myself`).
- `email` — the account email (used as the display label if the `/myself`
  response omits it).
- `default_project` — optional Jira **project key** (e.g. `ACME`); when set, it
  becomes the project for created tasks unless a `project` override is passed.

Tasks are created as issue type **Task** with `summary` = action title, a
generated description (meeting / owner / due), and an optional `duedate`.
The response `key` (e.g. `ACME-123`) becomes the `external_id` and
`{site_url}/browse/{key}` the `external_url`.

### 3.2 Linear — personal API key

- Create a key in **Settings → Security & access → Personal API keys** in the
  Linear app.
- The key is used verbatim as the `Authorization` header (Linear accepts the
  raw key, no `Bearer ` prefix — the adapter sends it as-is).
- `default_project` — optional **team ID** (a Linear team is the project scope
  for issue creation); if omitted, `connect()` reports the org `urlKey`, but
  `create_task()` requires a team ID and raises a validation error without one.

Tasks are created via the `issueCreate` GraphQL mutation. `external_id` = the
Linear issue UUID, `external_url` = `issue.url`.

### 3.3 Asana — Personal Access Token (PAT)

- Create a token in the Asana developer console: **Settings → Apps → Manage
  developer apps → Create new token** (or the "Personal access tokens" area).
- Scopes are implicit on the PAT; no OAuth consent screen is required for the
  v1 REST API.
- `default_project` — optional **workspace GID** (or project GID). If supplied,
  created tasks are placed in that workspace (and, when a `project` override is
  given, added to that project). Without a workspace GID, `create_task()`
  raises a validation error.

Tasks are created via `POST /api/1.0/tasks`. `external_id` = task `gid`,
`external_url` = `permalink_url`.

### 3.4 Todoist — REST API token

- Find it in the Todoist app under **Settings → Integrations → API token**.
- `default_project` — optional **project ID**; when set, created tasks carry
  `project_id`.

Tasks are created via `POST /rest/v2/tasks` with
`content` = action title, `description` = generated details, and an optional
`due_string`/`due_lang`. `external_id` = task `id`, `external_url` = task `url`.

---

## 4. Connecting — the API contract

You connect a PM provider by sending its credentials (never by toggling
`enabled` — see below).

```
POST /api/v1/workspace/integrations/{name}/connect
Authorization: Bearer <your JWT>

{
  "credentials": {
    "token": "<api key / PAT / REST token / jira bearer token>",
    "site_url": "https://acme.atlassian.net",   // jira only
    "email": "maya@acme.com",                    // jira only, optional
    "default_project": "ACME"                    // optional for all
  }
}
```

`{name}` is the display name from the workspace integration catalog — `Jira`,
`Linear`, `Asana`, or `Todoist` (URL-encoded, e.g. `Jira`). The server
resolves it to the provider slug (`jira`, `linear`, `asana`, `todoist`).

On success the backend:

1. Calls `adapter.connect(auth)` to validate the credential.
2. Encrypts `{token, site_url, email, default_project}` with `TokenEncryptor`
   and upserts the `pm_integration_tokens` row for `(user, provider)`.
3. Updates the workspace integration entry with `connected: true`,
   `account_email`, `account_url`, `token_expires_at`, and returns it.

```json
{
  "name": "Jira",
  "connected": true,
  "provider": "jira",
  "mode": "adapter_required",
  "account_email": "maya@acme.com",
  "account_url": "https://acme.atlassian.net",
  "token_expires_at": null
}
```

**Disconnect:** send `{ "enabled": false }` (with no `token`) to the same
endpoint, or omit `token` with `enabled` false. That soft-deletes the credential
row, clears the account metadata, and sets `connected: false`.

**Important — don't toggle `enabled` for PM providers.** A bare
`{ "enabled": true }` without `credentials.token` returns
`422 {"detail": "Credentials required to connect {name}"}` and never silently
fake-connects. (The `{enabled: bool}` toggle still works for the **legacy**
connectors — Planner / Salesforce / Slack.)

### `GET /api/v1/workspace/integrations`

Lists the full catalog. PM providers expose `provider`, `mode`,
`account_email`, `account_url`, `token_expires_at` (null when the token never
expires). Legacy connectors expose only `{connected, mode}`.

---

## 5. Syncing an action — the API contract

```
POST /api/v1/workspace/actions/{action_id}/queue
Authorization: Bearer <your JWT>

{ "destination": "Jira" }        // display name, or lowercase slug "jira"
```

On success the action is returned with real provider fields:

```json
{
  "id": "a1b2…", "title": "Ship the Q3 report", "owner": "Maya",
  "due": "2026-08-12", "meeting_id": "m-123", "meeting": "Q3 planning",
  "timestamp": "00:00", "status": "queued", "destination": "Jira",
  "external_id": "ACME-123",
  "external_url": "https://acme.atlassian.net/browse/ACME-123",
  "sync_state": "task-synced"
}
```

Because the UI renders a **View in {provider}** link from `external_url` when
`status === "queued" && external_url` is present, the two go together: a synced
PM action always has a real `external_id` and a real (provider-hosted)
`external_url` — never a fabricated UUID.

### Idempotency

Re-syncing the same action to the same provider is safe. The server sends an
`idempotency_key` (`<meeting_id>:<action_id>`) as the provider's idempotency
header on every create, **and** stores that key on the action as `sync_key`.
If you re-`queue` an action that already has `external_id` and a matching
`sync_key`, the server returns the existing action with `200` and makes **no**
second provider call. This makes the endpoint naturally safe for double-clicks,
network retries, and the UI retry button.

### Status codes

| Case | Status | `detail` |
|---|---|---|
| Action not found | 404 | `Action not found` |
| Unknown destination | 422 | `Unknown destination 'X'` |
| Legacy connector not connected | 409 | `Connect an adapter before queuing this action` |
| PM provider, no stored credential | 409 | `Connect {provider} before syncing this action` |
| Credentials rejected (401/403) | 401 | e.g. `Invalid or expired credentials for Jira. Reconnect your account.` |
| Provider 5xx / timeout / network | 502 | `{Provider} is temporarily unavailable. Try again in a few minutes.` |
| Provider 400/422 (bad project, etc.) | 422 | sanitized, user-friendly (no raw upstream body) |
| Duplicate idempotent re-sync | 200 | existing action returned untouched |

Every provider error message is sanitized before display — raw upstream bodies
(which might echo user content) are never surfaced.

---

## 6. Security notes

- Credentials are encrypted at rest with AES-256-GCM (`TokenEncryptor`,
  per-stored-blob DEK wrapped by a KEK derived from `STORAGE_ENCRYPTION_KEY` /
  `HIPAA_MASTER_KEY`). The `pm_integration_tokens` table is the only place a
  secret lives; the workspace JSON doc mirrors non-secret metadata only.
- The adapter never persists a decrypted token back to the doc or logs.
- All routes require the existing bearer JWT and scope state to the
  authenticated user.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `422 Credentials required to connect {name}` on connect | You sent `{"enabled": true}` without `credentials.token`. PM providers require the credential blob. |
| `409 Connect Jira before syncing this action` on queue | No active credential row for that provider. Connect it first. |
| `401 Invalid or expired credentials…` | The stored token was revoked or expired. Reconnect with a fresh credential. |
| `502 … temporarily unavailable` | Upstream 5xx, timeout, or network error. The action is left untouched; retry. |
| `422 Check the project key…` / team ID / workspace GID / project ID | The `default_project` (or the value prefilled at connect) is wrong or missing for that provider. |
| Linear `422 A team ID is required…` | Linear needs a `default_project` (team ID) before `create_task()`. |
| Asana `422 A workspace GID is required…` | Asana needs a `default_project` (workspace GID) before `create_task()`. |

---

## 8. Reference: where the code lives

- Adapter interface + shared types: `src/meeting_notes_ai/services/integrations/base.py`
- Adapters: `src/meeting_notes_ai/services/integrations/{jira,linear,asana,todoist}.py`
- Shared HTTP client seam: `src/meeting_notes_ai/services/http_client.py`
- Credential store: `PMIntegrationToken` in `src/meeting_notes_ai/db/models.py`
- Connect + queue routes: `src/meeting_notes_ai/routes/workspace.py`
- Token encryption: `src/meeting_notes_ai/services/token_encryption.py`
