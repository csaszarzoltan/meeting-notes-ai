# Workspace API v1.0.1

The React application uses these implemented routes:

- `GET /api/v1/workspace/dashboard`
- `GET /api/v1/workspace/meetings`
- `POST /api/v1/workspace/meetings`
- `GET /api/v1/workspace/meetings/{meeting_id}`
- `PATCH /api/v1/workspace/meetings/{meeting_id}/review`
- `POST /api/v1/workspace/meetings/{meeting_id}/share`
- `DELETE /api/v1/workspace/shares/{share_id}`
- `GET /api/v1/workspace/actions`
- `PATCH /api/v1/workspace/actions/{action_id}`
- `POST /api/v1/workspace/actions/{action_id}/queue`
- `GET /api/v1/workspace/settings`
- `PUT /api/v1/workspace/settings`
- `GET /api/v1/workspace/integrations`
- `POST /api/v1/workspace/integrations/{name}/connect`
- `POST /api/v1/workspace/insights/query`
- `GET /api/v1/workspace/compliance`
- `GET /api/v1/workspace/batches`
- `POST /api/v1/workspace/batches/{batch_id}/retry`

The default local implementation uses atomic JSON replacement at `data/workspace_state.json`. Deployments can replace this adapter with a database-backed repository while preserving the HTTP contract.

## Authentication and tenancy

All `/api/v1/workspace/*` endpoints require `Authorization: Bearer <JWT>` and scope data by the JWT user ID. The only anonymous route is `GET /public/workspace-shares/{token}`, which validates token existence, active state, and expiry and records each access. Connector queue endpoints never claim vendor completion; deployments provide the actual OAuth/provider adapter.

- `GET /public/workspace-shares/{token}`
