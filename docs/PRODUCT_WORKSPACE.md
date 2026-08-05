# Product Workspace API and UI Contract

The canonical UI is `GET /app`. `GET /app/live` returns a 307 redirect to `/app` so existing bookmarks remain valid. Hashed production assets are served from `/app/assets/{path}` with path-traversal checks.

The upload UI calls the existing `POST /api/v1/meetings` multipart endpoint with `file`, `mode`, `consent_confirmed`, and `phi_redaction`. The response is rendered directly in the review workspace. No new data API was invented for static demo content.

Live recording continues to use:

- `POST /api/v1/auth/login`
- `POST /api/v1/meetings/live/start`
- `WS /api/v1/meetings/live`

The UI is optimized for progressive enhancement: the route returns a minimal root shell before the frontend build exists, and a production bundle after `npm run build`.
