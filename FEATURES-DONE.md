# Features Done

## Features Done (this pass)
- Evidence-grounding rules: validates same-meeting timestamp spans and blocks unsupported claims.
- Versioned speaker mapping: applies bounded atomic corrections and rejects stale revisions.
- Review policy evaluation: fails closed for unsupported, rejected, stale, or under-approved claims.
- Artifact lineage rules: returns tenant-scoped acyclic graphs with idempotent registration.
- Deletion outcome classification: distinguishes internal deletion from external remediation.
- Tamper-evident audit exports: validates canonical hash chains and creates HMAC-signed ZIP manifests.
- Data-provider policy: blocks unapproved providers and pauses unavailable providers without fallback.
- Compliance UI navigation: responsive Overview, Audit exports, and Data policies sections.

## Sources
- research-findings.md items addressed: evidence-grounded review; speaker correction; artifact lineage; deletion receipts; tamper-evident audit; provider boundaries
- implementation-plan.md requirements addressed: PR-A1, review-policy core of PR-A2, PR-B1 service rules, deletion classification in PR-B2, audit/provider policy core of PR-B3
- user stories covered: US-001, US-002, US-003, US-007, US-008, US-009
- CHANGELOG.md section this maps to: 1.4.0
