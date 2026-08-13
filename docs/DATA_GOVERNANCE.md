# Data Governance

The governance API is rooted at `/api/v1/governance`. It exposes tenant-scoped lineage, idempotent deletion jobs, retry/status/receipt operations, audit validation/export, and versioned policies. Internal artifacts become deleted or already absent; external artifacts are always reported as `external_remediation_required` unless independently verified. Receipts and audit ZIP manifests use HMAC-SHA256 and require `AUDIT_EXPORT_SIGNING_KEY` of at least 32 bytes. Policy writes use `expected_version` and return 409 on conflict.

## Quarantine and worker deletion
Deletion requests validate the exact meeting title, create one pending job, and immediately quarantine the meeting. `run_deletion_job` performs leaf-first idempotent processing, preserves external-remediation outcomes, revokes shares, and stores a canonical HMAC-signed receipt. Receipt verification fails after any body or signature modification.
