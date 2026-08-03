# Live transcription frontend

Component-based UI for the MeetingNotesAI live-transcription view
(`GET /app/live`), built with **React 18 + TypeScript + Vite**.

## Build

```bash
cd frontend
npm install
npm run build
```

The production build lands in `frontend/dist/`. FastAPI serves the shell at
`/app/live` and the hashed bundle at `/app/live/assets/*`
(`src/meeting_notes_ai/routes/product_app.py`). `vite.config.ts` sets
`base: "/app/live/"` so the built asset URLs match the server mount.

The built `dist/` is committed so the deployed app serves the UI without a
Node build step; regenerate it whenever `src/` changes and commit the new
artifacts.

## Local development

```bash
cd frontend
npm run dev          # Vite dev server on :5173, proxies /api + /app to :8000
```

Point the proxy at a running backend (`uvicorn meeting_notes_ai.main:app`)
or at the demo server:

```bash
PYTHONPATH=src .venv/bin/python examples/live_demo_server.py
```

Then open http://localhost:5173/app/live/ and log in with
`demo@example.com` / `demo1234`.

## Components

- `src/App.tsx` — dashboard shell with nav to `/app` and `/app/live`
- `src/live/LiveTranscriptionView.tsx` — the view: connect button,
  microphone wiring, streaming transcript panel, finalize, action-item list
- `src/live/useLiveSession.ts` — session hook: login → draft meeting →
  getUserMedia → WebSocket chunks → partials → finalize
- `src/live/types.ts` — WS/REST contract types (mirrors
  `meeting_notes_ai/live_session.py`)
