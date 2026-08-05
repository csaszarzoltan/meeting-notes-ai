# Authenticated Workspace API v1.1.2

Every `/api/v1/workspace/*` route requires `Authorization: Bearer <JWT>` and scopes data by the authenticated user ID.

- GET `/api/v1/workspace/dashboard`
- GET `/api/v1/workspace/meetings?q=<query>`
- POST `/api/v1/workspace/meetings`
- GET `/api/v1/workspace/meetings/{meeting_id}`
- PATCH `/api/v1/workspace/meetings/{meeting_id}/review`
- POST `/api/v1/workspace/meetings/{meeting_id}/share`
- DELETE `/api/v1/workspace/shares/{share_id}`
- GET `/api/v1/workspace/actions`
- PATCH `/api/v1/workspace/actions/{action_id}`
- POST `/api/v1/workspace/actions/{action_id}/queue`
- GET `/api/v1/workspace/settings`
- PUT `/api/v1/workspace/settings`
- GET `/api/v1/workspace/integrations`
- POST `/api/v1/workspace/integrations/{name}/connect`
- POST `/api/v1/workspace/insights/query`
- GET `/api/v1/workspace/compliance`
- GET `/api/v1/workspace/batches`
- POST `/api/v1/workspace/batches/{batch_id}/retry`

The only anonymous workspace route is GET `/public/workspace-shares/{token}`. It validates existence, active state, and expiry and records each access. Connector queueing never claims vendor completion; deployments provide actual OAuth/provider adapters.
