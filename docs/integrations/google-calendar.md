# Google Calendar Integration (v1.1.2)

Connect a Google account through OAuth2, browse upcoming events, and import a
meeting in one click. The imported event becomes a tenant-scoped `Meeting`
record with `source="calendar_import"` and `review_status="needs_review"`,
ready for the standard review/approval workflow.

This guide covers the OAuth2 flow, environment setup, the user flow, the full
API surface, and troubleshooting.

---

## 1. Feature overview

What the integration does:

- **Connect** a Google account via OAuth2 (`calendar.readonly` scope) with a
  CSRF-protected state token (10-minute TTL, purged after use).
- **Browse** the next N days (default 7, max 30) of calendar events, with
  already-imported events flagged `imported: true`.
- **Import** any upcoming event as a meeting record in one click. The meeting
  gets the event summary as title, attendees, location, and Meet link as
  `calendar_context`, and starts in `needs_review` — it flows through the same
  review, approval, and sharing pipeline as any uploaded meeting.
- **Manage** the connection: poll `/status` for connected/needs-reauth state
  and disconnect via `/disconnect`.

Why it matters: it removes the manual "create a meeting, copy the title,
paste the attendees" step. One click from the calendar surface creates a
reviewable record, and the same event cannot be imported twice (409).

Design notes (verified against `src/meeting_notes_ai/`):

- All endpoints except `/callback` require the existing Bearer JWT and scope
  data by authenticated user ID (tenant isolation).
- OAuth access/refresh tokens are encrypted at rest with AES-256-GCM envelope
  encryption (`services/token_encryption.py`, `TokenEncryptor`), never stored
  or returned in plaintext.
- Expired access tokens are refreshed automatically using the stored refresh
  token; a revoked/expired refresh token surfaces a clean 401
  ("re-authorize") instead of a raw error.
- Network targets are hardcoded Google domains — no user-supplied URL is ever
  fetched (SSRF-safe by construction).
- Duplicate import is rejected globally per event (shared calendars): once any
  user imports an event, a second import attempt returns 409.

## 2. Prerequisites

1. A **Google Cloud project** with the **Google Calendar API** enabled.
2. An **OAuth2 client** of type **Web application** in that project.
3. The **redirect URI** registered on the client must match
   `GOOGLE_CALENDAR_REDIRECT_URI` exactly (see below).
4. A `STORAGE_ENCRYPTION_KEY` (or the legacy `HIPAA_MASTER_KEY`) set — the
   token encryptor raises at startup otherwise.
5. Python dependencies already pinned in `pyproject.toml`:
   `google-auth>=2.35.0`, `google-auth-oauthlib>=1.2.1`,
   `google-api-python-client>=2.160.0`.

### 2.1 Google Cloud Console setup

1. Go to <https://console.cloud.google.com> and select/create a project.
2. **APIs & Services → Library** → enable **Google Calendar API**.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs: add
     `http://localhost:8000/api/v1/integrations/google-calendar/callback`
     (development) or your deployed callback URL.
4. Copy the **Client ID** and **Client secret** into the environment variables
   below.

## 3. Setup instructions

### 3.1 Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CALENDAR_CLIENT_ID` | yes | — | OAuth2 web client ID from Google Cloud Console |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | yes | — | OAuth2 web client secret |
| `GOOGLE_CALENDAR_REDIRECT_URI` | no | `http://localhost:8000/api/v1/integrations/google-calendar/callback` | Must match the authorized redirect URI registered in the console |
| `STORAGE_ENCRYPTION_KEY` | yes* | — | AES-256-GCM KEK seed for token encryption (*or `HIPAA_MASTER_KEY`) |

`.env` example:

```bash
GOOGLE_CALENDAR_CLIENT_ID=1234567890-abc123.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxx
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google-calendar/callback
STORAGE_ENCRYPTION_KEY=replace-with-a-long-random-secret
```

All settings are read from the environment in
`src/meeting_notes_ai/config.py` (`Settings.google_calendar_*`). There is no
migration or DB setup step for the integration itself: the
`google_calendar_tokens`, `oauth_states`, and the `meetings` calendar columns
ship with migrations `20260806_0004` and `20260806_0005`.

### 3.2 Backend

No code change is required — the router is already mounted in
`src/meeting_notes_ai/main.py`:

```bash
uv sync --frozen
uv run uvicorn meeting_notes_ai.main:app --reload
```

### 3.3 Frontend

The React workspace surfaces the integration in four places
(`frontend/src/`):

- `api/googleCalendar.ts` — typed API client for the endpoints below.
- `workspace/CalendarEventPicker.tsx` — shared picker with skeleton/empty/error
  states and one-click import.
- `workspace/MeetingSetup.tsx` (calendar capture mode),
  `workspace/UploadFlow.tsx` (Import-calendar tab),
  `workspace/Dashboard.tsx` (onboarding OAuth step with Connected ✓ status),
  `workspace/IntegrationsCenter.tsx` (featured card).

```bash
cd frontend && npm ci && npm run build && cd ..
```

## 4. User flow

1. **Connect** — from the Integrations Center, Dashboard onboarding, or the
   calendar capture mode, click **Connect Google Calendar**. The frontend calls
   `POST /auth`, then redirects the browser to Google's consent screen
   (calendar.readonly, offline access).
2. **Consent** — the user picks an account and grants read-only calendar
   access. Google redirects to `GOOGLE_CALENDAR_REDIRECT_URI?code=...&state=...`.
   The backend verifies and consumes the state token, exchanges the code, and
   stores the tokens encrypted. The frontend completes the flow via the
   `/status` poll (the callback returns JSON, it does not redirect back to the
   SPA).
3. **Browse** — the event picker calls `GET /events` and renders the next 7
   days of events, marking already-imported ones.
4. **Import** — clicking an event calls `POST /import/{event_id}`, which
   creates the `Meeting` record (`needs_review`) and opens it in the review
   studio. A second click on the same event returns 409.
5. **Disconnect** — Integrations Center → Disconnect calls `DELETE /disconnect`
   (idempotent soft-delete).

## 5. API reference

Base path: `/api/v1/integrations/google-calendar`

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/auth` | Bearer JWT | Start OAuth2 flow; returns authorization URL + state |
| `GET` | `/callback?code=...&state=...` | none (state-verified) | Exchange code, store encrypted tokens |
| `GET` | `/events?days=7&calendar_id=primary` | Bearer JWT | List upcoming events, mark imported |
| `POST` | `/import/{event_id}?calendar_id=primary` | Bearer JWT | Create a meeting from a calendar event (201) |
| `GET` | `/status` | Bearer JWT | Connection status, token expiry, needs_reauth |
| `DELETE` | `/disconnect` | Bearer JWT | Soft-delete tokens (204, idempotent) |

### 5.1 POST /auth

Starts the OAuth2 flow. Generates a fresh CSRF state token (stored with a
10-minute TTL) and returns the Google consent URL.

**Request:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/integrations/google-calendar/auth \
  -H "Authorization: Bearer <JWT>"
```

**Response 200:**

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&redirect_uri=...&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar.readonly&state=...",
  "state": "opaque-csrf-state-token"
}
```

### 5.2 GET /callback

Handles Google's redirect after consent. `state` must match a stored, unexpired
token — the state row is consumed and purged on read. Exchanges the code and
upserts the user's encrypted tokens.

**Request:**

```bash
curl "http://127.0.0.1:8000/api/v1/integrations/google-calendar/callback?code=AUTH_CODE&state=opaque-csrf-state-token"
```

**Response 200:**

```json
{
  "connected": true,
  "calendar_id": "primary",
  "expires_at": "2026-08-06T15:30:00+00:00"
}
```

**Errors:** `400` — invalid or expired OAuth state; `400` — code exchange
failed. Token material is never present in the response body.

### 5.3 GET /events

Lists upcoming events. Expired access tokens are refreshed automatically
before the request; events already imported by any user are marked
`imported: true`.

**Query params:** `days` (1–30, default 7), `calendar_id` (default `primary`).

**Request:**

```bash
curl "http://127.0.0.1:8000/api/v1/integrations/google-calendar/events?days=7" \
  -H "Authorization: Bearer <JWT>"
```

**Response 200:**

```json
{
  "events": [
    {
      "id": "event-1",
      "summary": "Q3 Planning",
      "description": "Review quarterly goals",
      "start": "2026-08-07T10:00:00+02:00",
      "end": "2026-08-07T11:00:00+02:00",
      "attendees": [
        {
          "email": "alice@example.com",
          "display_name": "Alice",
          "response_status": "accepted"
        }
      ],
      "location": "Conference Room A",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "organizer": {
        "email": "bob@example.com",
        "display_name": "Bob"
      },
      "calendar_id": "primary",
      "html_link": "https://calendar.google.com/calendar/event?eid=...",
      "imported": false
    }
  ],
  "calendar_id": "primary",
  "days": 7
}
```

> Note: the API serializes attendee and organizer fields in snake_case. Google's
> camelCase `displayName` / `responseStatus` are mapped onto the Pydantic
> schema by the calendar service, so `display_name` and `response_status`
> carry the values Google provides. `email` is always populated.

**Errors:** `409` — Google Calendar not connected; `401` — token expired and
could not be refreshed (re-authorize); `502` — Google Calendar API
unavailable.

### 5.4 POST /import/{event_id}

Creates a `Meeting` record from a calendar event: title = event summary,
`source="calendar_import"`, `mode="general"`, attendees/location/meet_link/
description carried in `calendar_context`, `review_status="needs_review"`.
Duration is computed from start/end when both are present.

**Query params:** `calendar_id` (default `primary`).

**Request:**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/integrations/google-calendar/import/event-123" \
  -H "Authorization: Bearer <JWT>"
```

**Response 201:**

```json
{
  "meeting": {
    "id": "6f9b2c1e-...",
    "title": "Q3 Planning",
    "source": "calendar_import",
    "google_calendar_event_id": "event-123",
    "date": "2026-08-07T10:00:00+02:00",
    "duration": "1h",
    "participants": 2,
    "review_status": "needs_review",
    "calendar_context": {
      "attendees": ["alice@example.com", "bob@example.com"],
      "location": "Conference Room A",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "description": "Review quarterly goals"
    }
  }
}
```

**Errors:** `409` — event already imported (by this user or any user on a
shared calendar) or calendar not connected; `401` — token expired (re-authorize);
`404` — event not found / upstream error (generic, never echoes raw Google
error text).

### 5.5 GET /status

**Request:**

```bash
curl http://127.0.0.1:8000/api/v1/integrations/google-calendar/status \
  -H "Authorization: Bearer <JWT>"
```

**Response 200 (connected):**

```json
{
  "connected": true,
  "calendar_id": "primary",
  "connected_at": "2026-08-06T12:00:00+00:00",
  "token_expires_at": "2026-08-06T13:00:00+00:00",
  "needs_reauth": false
}
```

**Response 200 (not connected):**

```json
{
  "connected": false,
  "calendar_id": "primary",
  "connected_at": null,
  "token_expires_at": null,
  "needs_reauth": false
}
```

`needs_reauth` is `true` when the stored token is past its expiry.

### 5.6 DELETE /disconnect

Soft-deletes the user's tokens (`is_active=false`, `disconnected_at` set).
Idempotent — returns 204 whether or not a connection existed.

**Request:**

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/integrations/google-calendar/disconnect \
  -H "Authorization: Bearer <JWT>"
```

**Response:** `204 No Content`.

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `400 "Invalid or expired OAuth state"` on callback | State token expired (>10 min), already used, or `GOOGLE_CALENDAR_REDIRECT_URI` doesn't match the registered redirect | Re-run the connect flow; confirm the redirect URI matches exactly (scheme, host, port, path) in both `.env` and the Google Cloud Console |
| `400 "Failed to exchange authorization code"` | Wrong/mismatched client secret, or code already exchanged | Check `GOOGLE_CALENDAR_CLIENT_SECRET`; restart the flow to get a fresh code |
| `401 "Google token expired. Please re-authorize."` | Refresh token revoked (user revoked app access) or invalid | Reconnect via the Integrations Center — the frontend surfaces this as a re-authorization prompt |
| `502 "Google Calendar is temporarily unavailable"` | Upstream Calendar API error | Retry later; check Google Workspace status; verify the Calendar API is enabled for the project |
| `409 "This event has already been imported"` | Duplicate import — same event imported by this user or any user on a shared calendar | Pick a different event; import is globally once per event by design |
| `409 "Google Calendar not connected"` on `/events` / `/import` | User has no active token record | Run the connect flow first |
| `ValueError: TokenEncryptor requires STORAGE_ENCRYPTION_KEY or HIPAA_MASTER_KEY` | Encryption key missing at startup | Set `STORAGE_ENCRYPTION_KEY` (or `HIPAA_MASTER_KEY`) in the environment |
| Consent screen shows "unverified app" warning | OAuth consent screen in testing mode / app not verified | Expected during development; add your Google account as a test user. For production, complete app verification or use a verified publishing status |
| Imported meeting has no transcript/decisions | Calendar imports create an empty shell meeting (`needs_review`) by design | Attach audio or edit the record through the normal review workflow |
