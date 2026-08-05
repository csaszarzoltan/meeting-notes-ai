## Features Done (this pass)
- Authenticated workspace boundary: every private workspace route now requires the existing JWT dependency
- Tenant-isolated workspace persistence: meetings, reviews, actions, settings, integrations, compliance, batches, audits, and shares are scoped by authenticated user ID
- Canonical meeting save: upload processing results are persisted before the review workspace opens
- Review and approval provenance: autosave, approval, rejection, reviewer identity, immutable versions, and audit events persist through the authenticated API
- Secure public sharing: approved meetings receive expiring random tokens with active-state checks, access auditing, and immediate revocation
- Honest connector execution: configured adapters receive queued work without fabricated remote IDs or false synced status
- Evidence-backed compliance: controls derive from current authenticated approval and retention settings
- Real workspace search: Cmd/Ctrl+K queries private meeting title, summary, transcript, tags, and decisions and supports Arrow/Enter keyboard operation
- Real review playback controls: desktop and mobile controls use the audio element and evidence navigation seeks to source timestamps
- Authenticated product shell: AuthGate is mounted and the workspace client and upload processing requests send the session JWT
- Honest capture availability: calendar and in-person preview modes are disabled until implemented
- Review remediation tests: security, tenant isolation, full create-review-share-revoke integration, UI wiring, and real filesystem persistence are covered
## Sources
- research-findings.md items addressed: unified product workflow, source-linked review, review-before-share, tenant isolation, safe sharing, action execution, truthful compliance, global search
- CHANGELOG.md section this maps to: [1.1.2] - 2026-08-05
