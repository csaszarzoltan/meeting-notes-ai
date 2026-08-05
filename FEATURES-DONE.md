## Features Done (this pass)
- Authenticated workspace boundary: every private workspace route requires JWT authentication
- Tenant isolation: meetings, actions, settings, integrations, compliance, batches, audits, and shares are scoped by authenticated user ID
- Frontend authentication gate: private React workspace requires login and keeps the JWT in sessionStorage
- Canonical processing flow: upload results are saved to the private meeting library before opening review
- Durable review workflow: edits, approval/rejection, reviewer identity, versions, and audit events persist under the authenticated tenant
- Policy-enforced public sharing: approved meetings create secure expiring tokens, public resolution checks active/expiry state, access is audited, and revocation returns 410
- Honest connector queue: actions require a configured adapter and are queued without fabricating vendor completion or external IDs
- Derived compliance controls: approval and retention status are calculated from authenticated workspace policy instead of seeded compliance claims
- Actionable UI controls: unavailable calendar/in-person modes are disabled, compliance remediation navigates to settings, and cited source buttons expose a target hash
- Deterministic CI: GitHub Actions installs locked dependencies, lints, typechecks, builds, and runs the full test suite
- Release hygiene: runtime SQLite/state artifacts are excluded and removed from the release tree
## Sources
- research-findings.md items addressed: secure application shell, canonical meeting record, source-linked review, Action Center, policy-driven sharing, cited intelligence, regulated workflow, governed vocabulary/templates
- review-findings.md blockers addressed: anonymous workspace access, broken upload-review-share flow, missing public share resolver, fake sync status, seeded compliance claims, inert controls, missing CI, and committed database artifact
- CHANGELOG.md section this maps to: [1.0.2] - 2026-08-05
