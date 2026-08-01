# Migration notes for v0.6.0

Development databases created with `init_db()` receive the new columns and tables automatically. Existing production databases require a migration before starting v0.6.0.

## Schema changes

1. Add `users.tier`, non-null, default `free`.
2. Create `api_keys` with tenant-user ownership, hashed credential storage, prefix display, tier, activity state, optional name, last-used time, and timestamps.

## PostgreSQL reference migration

```sql
ALTER TABLE users
ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'free';

CREATE TABLE api_keys (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    key_prefix VARCHAR(12) NOT NULL,
    hashed_key VARCHAR(64) NOT NULL UNIQUE,
    tier VARCHAR(20) NOT NULL DEFAULT 'free',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    name VARCHAR(100),
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_api_keys_user_id ON api_keys(user_id);
CREATE INDEX ix_api_keys_key_prefix ON api_keys(key_prefix);
```

## Required production secrets

- `JWT_SECRET`: long random JWT signing secret.
- `ADMIN_API_TOKEN`: bootstrap token for tier administration. Replace this mechanism with identity-provider administrator claims in mature deployments.
- `OPENAI_API_KEY`: transcription and extraction provider credential.
- `HIPAA_MASTER_KEY`: HIPAA encryption key seed for the existing encryption service.

## Rate-limit deployment note

The bundled token bucket is thread-safe but process-local. Use a shared atomic backend before horizontally scaling the API. Health checks are excluded by default in standalone middleware use. The main application applies headers to health checks to preserve its documented API contract.
