# Data Governance

Artifact lineage is tenant-scoped and acyclic. Internal artifacts may be marked deleted or already absent; external artifacts are reported as `external_remediation_required` unless deletion is independently verified. Audit exports contain canonical JSONL and an HMAC-SHA256 signed manifest. A signing key must contain at least 32 bytes.
