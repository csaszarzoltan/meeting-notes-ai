# Features Done

## Features Done (this pass)
- Persistent trusted-record API: canonical record retrieval, optimistic claim editing, speaker mapping, review decisions, immutable publishing, and activity.
- Governance API: tenant-scoped artifact lineage, idempotent deletion jobs, signed receipts, audit exports, and versioned policies.
- Complete governance schema: corrective Alembic migration and ORM models for review, snapshot, policy, artifact, deletion, and audit records.
- Functional compliance UI: real audit-export download and active-policy loading with loading, validation, error, and success states.

## Sources
- research-findings.md items addressed: evidence-grounded review; speaker correction; verifiable deletion; audit integrity; provider and storage boundaries
- implementation-plan.md requirements addressed: PR-1, PR-2, PR-3, PR-4, PR-5; PR-6 remains blocked by documented pre-existing regression failures
- user stories covered: US-001, US-002, US-003, US-007, US-008, US-009
- CHANGELOG.md section this maps to: 1.4.1
