# Features Done

## Features Done (this pass)
- Complete claim review interaction: edit text, select transcript evidence, add/remove evidence, approve, reject, and publish.
- Review conflict recovery: Keep current, Use mine as new revision, and Cancel without losing the local draft.
- Speaker mapping interaction: map transcript speakers and surface Reapproval required state.
- Snapshot publication and sharing: immutable snapshot metadata and direct Share snapshot action.
- Snapshot/share lineage hooks: team snapshot and strict snapshot-backed share artifacts are registered idempotently.

## Sources
- research-findings.md items addressed: evidence-grounded review, speaker correction, safe sharing, artifact lineage
- implementation-plan.md requirements addressed: PR-1, PR-2 interaction core, PR-3 persistent path, PR-4 snapshot/share hooks
- user stories covered: US-001, US-002, US-003, US-007
- CHANGELOG.md section this maps to: 1.6.0
