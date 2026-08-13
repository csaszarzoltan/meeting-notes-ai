# Data Governance

The governance API is rooted at `/api/v1/governance`. It exposes tenant-scoped lineage, idempotent deletion jobs, retry/status/receipt operations, audit validation/export, and versioned policies. Internal artifacts become deleted or already absent; external artifacts are always reported as `external_remediation_required` unless independently verified. Receipts and audit ZIP manifests use HMAC-SHA256 and require `AUDIT_EXPORT_SIGNING_KEY` of at least 32 bytes. Policy writes use `expected_version` and return 409 on conflict.
