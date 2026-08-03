# Live Transcription — WebSocket Contract (v0.8.0)

Real-time streaming transcription for MeetingNotesAI. A browser or native
client opens a WebSocket to `/api/v1/meetings/live`, streams audio chunks as
binary frames, receives incremental transcript partials, and finalizes the
session to get the full transcript, summary, and action items.

The companion example clients live in `examples/`:

- `examples/live_transcription_client.py` — runnable WS client (Python,
  `websockets`). Demonstrates the full contract: auth → draft meeting → chunks
  → partials → finalize.
- `examples/live_demo_server.py` — a dev-only FastAPI server that swaps the
  external STT/LLM seam for deterministic fakes, so the UI can be exercised
  end-to-end **without** an `OPENAI_API_KEY`.

---

## 1. Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `WS` | `/api/v1/meetings/live?token=<JWT>&meeting_id=<id>[&team_id=<id>][&room_id=<id>]` | JWT query token | Stream live audio + partials + finalize |
| `POST` | `/api/v1/meetings/live/start` | Bearer JWT | Create a draft meeting the WS attaches to; returns `meeting_id` |
| `POST` | `/api/v1/meetings/live/upload` | Bearer JWT | REST fallback: transcribe a full audio file, same result shape |

The WebSocket authenticates via a `token` **query parameter** because
browsers cannot set headers on WebSocket handshakes. The token is the same
JWT returned by `POST /api/v1/auth/login` / `/signup`.

### Session scoping

- `meeting_id` must reference an existing meeting row; the server checks the
  caller owns it (or is a member of the meeting's team).
- `team_id` / `room_id` are optional and further scope the session.
- Sessions are persisted to the `live_sessions` table: a dropped socket can be
  resumed with the same session id, and finalize persists the transcript +
  summary onto the meeting row.

## 2. Client → server frames

| Direction | Frame type | Payload | Meaning |
|-----------|-----------|---------|---------|
| client → | **binary** | 16 kHz PCM (`WAV`-framed) or `WebM`/Opus chunk | One audio chunk; the server detects WebM by magic bytes `1A 45 DF A3` |
| client → | **text** | `{"type": "finalize"}` | Persist the session and return the final result |

## 3. Server → client frames (JSON text)

### Partial transcript

```json
{
  "type": "partial",
  "sequence": 3,
  "text": "…the latest incremental transcript…",
  "timestamp": "2026-08-03T16:00:00.123456+00:00"
}
```

`sequence` is monotonically increasing and strictly unique per session —
clients should render partials in `sequence` order and replace the previous
partial with the newest one.

### Finalized result

Sent once, after the client sends `{"type": "finalize"}`:

```json
{
  "type": "finalized",
  "session_id": "…",
  "meeting_id": "…",
  "transcript": "…full transcript…",
  "summary": "…extracted summary…",
  "action_items": [{"assignee": "Mike", "description": "Ship live transcription"}],
  "decisions": ["Deploy on Friday"],
  "key_points": ["Live transcription works"],
  "chunk_count": 42,
  "partial_count": 7,
  "duration_seconds": 12.5
}
```

### Error frame

```json
{"type": "error", "code": "rate_limited"}
```

The server closes the socket with an application close code on hard failures:
`4401` unauthorized, `4403` forbidden (not the meeting owner / team member),
`4404` meeting not found.

## 4. Minimal client flow

```
1. POST /api/v1/auth/login            → {access_token}
2. POST /api/v1/meetings/live/start   → {meeting_id}          (Bearer token)
3. WS  /api/v1/meetings/live?token=…&meeting_id=…
4. send binary WebM/Opus chunks       → receive `partial` frames
5. send {"type": "finalize"}          → receive `finalized` frame
```

See `examples/live_transcription_client.py` for the full, runnable
implementation of this sequence.

## 5. Browser UI

The product dashboard serves a component-based React view at
`GET /app/live` (built from `frontend/`, served by
`routes/product_app.py`). It implements this exact contract: connect button,
microphone wiring via `getUserMedia` + `MediaRecorder` (`audio/webm;codecs=opus`),
a streaming transcript panel with partial updates, a finalize action, and a
visible action-item list after finalization. The page's CSP allows
`connect-src ws: wss:` and its `Permissions-Policy` relaxes
`microphone=(self)`; every other page keeps the strict default.
