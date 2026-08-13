# Implementation Plan

## Executive Summary

This pass is the final **integration, enforcement, and user-experience completion** pass for the research-backed trusted-record strategy. The repository now contains a corrective schema, persistent trusted/governance endpoints, tested domain rules, and a functional Compliance Center, but the latest development report truthfully identifies three remaining product gaps: selected policies are not enforced across every legacy workflow, artifact lineage is not populated by every derivative-producing path, and the Review/Transcript/Activity/Data experience is not complete or browser-verified.

Two features are selected:

1. **Trusted Record UX Completion** (`US-001`, `US-002`, `US-003`): connect the existing trusted API to a complete meeting-detail experience, enforce immutable publication at legacy sharing boundaries, and make speaker correction, conflict recovery, activity, and snapshot sharing work end to end.
2. **Governance Enforcement Completion** (`US-007`, `US-008`, `US-009`): register every planned derivative, enforce provider policy before outbound work, move deletion execution behind a durable worker boundary, finish Data/Audit/Policy screens, and provide browser, accessibility, and screenshot evidence.

A third workstream, **regression stabilization**, is a release gate rather than a product feature. The 23 repeatable failures documented in two consecutive development reports must be fixed without weakening tests. No new market feature is admitted until the full suite is green.

## Current-State Validation

Verified current state:

- `routes/trusted_records.py` exposes record, claim update, speaker mapping, decision, publish, and activity routes.
- `routes/governance.py` exposes lineage, deletion, receipt, audit export, and policy routes.
- Migration 0007 completes the missing schema; ORM includes review, snapshot, policy, artifact, deletion, and audit entities.
- The pure evidence/review/governance rule modules have 23 green BDD-derived tests and 99% measured coverage.
- New schema/contract tests bring the selected suite to 29 green tests.
- Compliance Center uses real audit-export and policy-loading endpoints, but administrators manually enter a team ID, policy editing is read-only, and audit jobs are synchronous downloads.
- `ReviewWorkspace.tsx` still uses the older workspace review endpoint and does not consume `trustedRecords.ts`.
- No complete Meeting Activity or Meeting Data component exists.
- Legacy share creation does not require an eligible snapshot.
- Storage, export, webhook, and PM integration paths do not comprehensively register artifact metadata.
- Provider policy is not invoked before every transcription/extraction/storage outbound action.
- Deletion is executed synchronously in the HTTP request.
- Full regression remains at 23 failures in the same groups across two phases; Playwright, axe, and screenshots remain absent.

The research recommendations continue to match these gaps. Completing trust, lineage, and policy enforcement produces more value and lower risk than starting desktop capture or another integration.

## Research Priorities

| Priority | Research recommendation | Current maturity | Decision |
|---|---|---|---|
| P0 | Evidence-grounded review and approval | API foundation present, UX/integration partial | Complete now. |
| P0 | Speaker correction and quality queue | Rule/API present, UX absent | Complete now. |
| P0 | Artifact lineage and verifiable deletion | API present, hooks/job architecture partial | Complete now. |
| P1 | Audit export and policy control | Basic APIs/UI present | Complete editable, asynchronous, verified flow. |
| P1 | Accessibility/browser E2E | Not implemented | Mandatory in this pass. |
| P0 release gate | Regression stability | 23 repeatable failures | Mandatory before done. |
| Deferred | Bot-free desktop capture | Not started | Next independent phase. |

## Selected Scope for This Pass

### Feature 1: Trusted Record UX Completion

Use the existing trusted endpoints as the source of truth for meeting review. Deliver claim-level evidence review, atomic speaker mapping, optimistic-edit conflict recovery, activity history, immutable publication, and snapshot-gated sharing in the existing React workspace. Preserve non-strict compatibility only for historical meetings under compatibility policy.

### Feature 2: Governance Enforcement Completion

Add artifact registration at every planned derivative boundary, durable deletion/export jobs, signed receipt verification, outbound provider preflight, editable policy UI, Meeting Data lineage/deletion UI, and complete Audit Export UI. Add browser automation, accessibility checks, and screen captures.

## Deferred Scope and Rationale

1. Desktop microphone/system-audio companion and local-only summarization: separate OS signing/model qualification pass.
2. Managed-device deployment: depends on desktop client.
3. New PM/CRM adapters: current adapters are sufficient for governance-hook coverage.
4. Broad WER/DER benchmark: independent model-quality pass.
5. Billing/pricing: requires paid pilots after trusted workflows are complete.
6. Native mobile apps: responsive web is sufficient for this pass.
7. Public-key audit signatures: HMAC retained; asymmetric verification is a future security pass.
8. Compliance certification: outside engineering scope.

## User Stories (BDD)

```json
[
  {
    "id": "US-001",
    "epic": "Trusted Record UX Completion",
    "role": "reviewer",
    "action": "open every generated claim at its supporting transcript span",
    "benefit": "I can verify notes before approval",
    "story": "As a reviewer, I want to open every generated claim at its supporting transcript span, so that I can verify notes before approval.",
    "gui_flow": [
      "User opens Review workspace → sees draft notes and transcript",
      "User selects a decision → cited transcript spans highlight",
      "User clicks a citation → audio seeks to the cited start time",
      "User compares the claim with evidence → approve, edit, or reject controls appear",
      "User approves the claim → reviewer and timestamp are recorded",
      "User publishes the meeting → only approved claims appear"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a claim has one or more spans",
        "when": "the reviewer opens it",
        "then": "speaker, exact text, start time, end time and source segment ID are shown"
      },
      {
        "type": "given",
        "text": "a claim has no span",
        "when": "the reviewer opens it",
        "then": "it is labeled unsupported and strict mode blocks publication"
      },
      {
        "type": "given",
        "text": "the evidence endpoint fails",
        "when": "the reviewer opens it",
        "then": "approval is disabled and a retryable error with correlation ID appears"
      }
    ]
  },
  {
    "id": "US-002",
    "epic": "Trusted Record UX Completion",
    "role": "team member",
    "action": "correct a speaker once across selected transcript segments",
    "benefit": "actions and decisions are attributed correctly",
    "story": "As a team member, I want to correct a speaker once across selected transcript segments, so that actions and decisions are attributed correctly.",
    "gui_flow": [
      "User opens a meeting transcript → diarized speaker labels appear",
      "User clicks a speaker label → mapping dialog opens",
      "User chooses a workspace member or guest → affected segment count appears",
      "User previews replacements → linked actions display proposed assignees",
      "User confirms → transcript and draft notes update",
      "User opens history → mapping revision is listed"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a unique member is selected",
        "when": "the user confirms",
        "then": "all selected segments change and linked draft items are recomputed"
      },
      {
        "type": "given",
        "text": "two members share a display name",
        "when": "the user searches",
        "then": "the UI requires selection by unique email and does not guess"
      },
      {
        "type": "given",
        "text": "recomputation fails",
        "when": "the user confirms",
        "then": "the original mapping remains active and no partial note update is published"
      }
    ]
  },
  {
    "id": "US-003",
    "epic": "Trusted Record UX Completion",
    "role": "workspace admin",
    "action": "require human approval for sensitive meeting modes",
    "benefit": "unreviewed AI output cannot be shared as an official record",
    "story": "As a workspace admin, I want to require human approval for sensitive meeting modes, so that unreviewed AI output cannot be shared as an official record.",
    "gui_flow": [
      "Admin opens Workspace settings → approval policy is visible",
      "Admin selects healthcare and legal modes → reviewer-role options appear",
      "Admin requires one reviewer → policy preview updates",
      "Admin saves → versioned policy becomes active",
      "Member opens an unapproved meeting → Share is disabled",
      "Reviewer approves all required findings → Share becomes enabled"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a sensitive meeting satisfies the configured approvals",
        "when": "a user shares it",
        "then": "the share is created and records policy version plus approvers"
      },
      {
        "type": "given",
        "text": "one required finding is rejected",
        "when": "a user tries to share",
        "then": "sharing is blocked and the unresolved finding count is shown"
      },
      {
        "type": "given",
        "text": "policy evaluation is unavailable",
        "when": "a user tries to share",
        "then": "the system fails closed and creates no share token"
      }
    ]
  },
  {
    "id": "US-007",
    "epic": "Governance Enforcement Completion",
    "role": "workspace admin",
    "action": "see one lineage graph for each meeting artifact",
    "benefit": "I know where sensitive content was copied",
    "story": "As a workspace admin, I want to see one lineage graph for each meeting artifact, so that I know where sensitive content was copied.",
    "gui_flow": [
      "Admin opens Compliance center → meetings and risk filters appear",
      "Admin selects a meeting → artifact lineage graph opens",
      "Admin expands transcript → summaries, exports, shares and integrations appear",
      "Admin selects an artifact → owner, location and retention state show",
      "Admin clicks Delete meeting → impact preview lists all derivatives",
      "Admin confirms → deletion progress and receipt appear"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "all derivatives are known",
        "when": "deletion completes",
        "then": "every artifact becomes inaccessible within 60 seconds and the receipt lists each result"
      },
      {
        "type": "given",
        "text": "an integration copy cannot be deleted by API",
        "when": "deletion runs",
        "then": "the receipt marks external remediation required and provides exact destination metadata"
      },
      {
        "type": "given",
        "text": "one internal deletion fails",
        "when": "deletion runs",
        "then": "the meeting is quarantined, failure is visible and retry is idempotent"
      }
    ]
  },
  {
    "id": "US-008",
    "epic": "Governance Enforcement Completion",
    "role": "security administrator",
    "action": "export tamper-evident audit evidence",
    "benefit": "I can support an incident or compliance review",
    "story": "As a security administrator, I want to export tamper-evident audit evidence, so that I can support an incident or compliance review.",
    "gui_flow": [
      "Admin opens Compliance center → audit coverage status appears",
      "Admin selects date range and teams → event count updates",
      "Admin clicks Validate chain → verification runs",
      "Admin chooses JSON or CSV plus manifest → export preview appears",
      "Admin downloads export → SHA-256 checksum is displayed",
      "Admin verifies checksum → result and instructions appear"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "the append-only chain is intact",
        "when": "validation runs",
        "then": "all events verify and the signed manifest includes range, count and terminal hash"
      },
      {
        "type": "given",
        "text": "the range contains no events",
        "when": "the admin exports",
        "then": "a valid empty manifest is produced with zero count"
      },
      {
        "type": "given",
        "text": "a hash link is broken",
        "when": "validation runs",
        "then": "the export is marked failed and identifies the first invalid event without rewriting history"
      }
    ]
  },
  {
    "id": "US-009",
    "epic": "Governance Enforcement Completion",
    "role": "workspace owner",
    "action": "enforce regional storage and provider rules",
    "benefit": "new meetings stay within approved data boundaries",
    "story": "As a workspace owner, I want to enforce regional storage and provider rules, so that new meetings stay within approved data boundaries.",
    "gui_flow": [
      "Owner opens Data residency → current region and providers appear",
      "Owner selects an allowed storage region → migration implications display",
      "Owner disables unapproved AI providers → affected features show",
      "Owner saves as a new policy version → readiness checks run",
      "User creates a meeting → policy decision appears before processing",
      "Owner reviews policy report → compliant and blocked jobs are listed"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "approved regional services are healthy",
        "when": "a meeting is processed",
        "then": "all persisted artifacts and configured AI calls use allowed regions/providers and record policy version"
      },
      {
        "type": "given",
        "text": "an imported calendar event belongs to another region",
        "when": "processing is requested",
        "then": "the system blocks or routes it according to policy without silent fallback"
      },
      {
        "type": "given",
        "text": "the approved provider is unavailable",
        "when": "processing starts",
        "then": "the job pauses and no unapproved provider is used"
      }
    ]
  }
]
```

## Product Requirements

### PR-1 Trusted meeting-detail integration (`US-001`)

- `ReviewWorkspace` loads `GET /api/v1/trusted/meetings/{id}/record`; the old workspace detail is used only as a migration fallback when the trusted route returns a documented legacy-projection response.
- Render each claim independently with type, text, status, version, approvals, and evidence chips.
- Evidence chip selects the canonical segment, seeks audio to `start_ms` with observed player position within 1,000 ms, and focuses/highlights the cited text.
- Claim editing sends `If-Match` with the current version and the edited evidence list. Successful save updates ETag/version once. A 409 opens conflict recovery without discarding local text.
- Conflict choices are exact: `Keep current`, `Use mine as new revision`, `Cancel`. “Use mine” reloads current state, reapplies local text/evidence, and submits with the new version.
- Unsupported legacy claims show `Evidence required`; strict publish remains disabled. Users can select one or more transcript segments and attach bounded evidence.
- Publish displays blocker codes next to affected claims. Successful publish displays snapshot version, SHA-256 abbreviation, creator, and `Share snapshot` CTA.

Measurable acceptance: every newly published strict claim has one or more persisted same-meeting spans; no edit is lost on 409 or retryable network error; published snapshot bytes/hash remain stable after later edits.

### PR-2 Speaker correction and activity (`US-002`)

- Transcript screen lists canonical segments in ordinal order and uses buttons for speaker labels.
- Mapping dialog requires either a uniquely selected workspace user with email or a nonblank guest name. It supports `This segment`, `Selected segments`, and `All <raw label>` scopes, maximum 500.
- Preview shows affected segment count and approved claims that will require reapproval.
- Apply invokes persistent mapping endpoint once and updates all impacted segments transactionally. Server error or stale version leaves UI and database unchanged.
- Activity screen consumes trusted activity endpoint and displays actor, decision, timestamp, claim version, policy version when available, and safe expandable metadata. It never displays transcript text in collapsed or expanded audit metadata.
- Keyboard: J/K moves segments, Enter opens speaker dialog, Escape closes/restores focus, Space controls playback only outside form fields.

Measurable acceptance: mapped segments share the returned revision; ambiguous display names cannot be submitted without an email selection; failed mapping produces zero partial updates; approved impacted claims immediately display `Reapproval required`.

### PR-3 Snapshot-gated legacy sharing (`US-003`)

- Both existing share endpoints call one common `assert_share_allowed(meeting_id, user/team, db)` service before token creation.
- Strict meetings require latest eligible published snapshot under active policy. If absent/stale, return 409 with `POLICY_NOT_SATISFIED` and blocker array.
- Compatibility-policy historical meetings preserve existing share behavior. Every newly configured strict policy fails closed on evaluator/service error.
- New share rows store nullable `snapshot_id` and `policy_version_id`; migration adds both columns without changing existing rows.
- Public share response renders the immutable snapshot payload when linked, never the current draft.
- Revocation behavior remains unchanged.

Measurable acceptance: no strict token is created on failure; shared content hash equals snapshot hash; later draft edits do not alter existing public response; all existing sharing regression tests stay green.

### PR-4 Artifact registration and lineage (`US-007`)

- Introduce `ArtifactRegistry` async service using `(team_id, source_key)` idempotency and encrypted opaque location references.
- Register: audio upload/storage, transcript revision, claim set, snapshot, export, share, webhook payload delivery, and PM task reference.
- Database derivatives register inside the same transaction. For external calls, reserve a pending artifact before the call, then mark active with provider reference or failed with safe code. A failed registration prevents silent success.
- Every artifact has a required parent edge except source audio. Reject self, duplicate, cross-team, invalid cross-meeting, and cycle-forming edges.
- Lineage response includes node counts and remediation summary but never decrypted references.
- Historical meetings with no registry remain readable and display a warning; no fake lineage is generated.

Measurable acceptance: one artifact and required edge per successful derivative; exact replay creates no duplicate; cross-tenant query is 404; graph is acyclic; failed external call remains observable and contains no token/URL.

### PR-5 Durable deletion and receipts (`US-007`)

- HTTP request only validates, quarantines, and creates/returns one active job. It must not execute deletion inline.
- Add database worker claim using transaction/state transition `pending → processing`; expose deterministic `run_deletion_job(job_id)` for tests and worker command.
- Worker processes leaves before parents, revokes shares, deletes internal files/rows, preserves receipt/audit metadata, and marks external copies `external_remediation_required` unless verified delete is supported.
- Partial failures become `completed_partial`; retry resets only failed internal results to pending. Successful results never repeat.
- Quarantined meetings disappear from normal list/search/share and block new exports/integrations immediately.
- Receipt is canonical signed JSON with job, requestor, policy version, terminal audit hash, per-artifact outcome, generated timestamp; no content fields. Add verification endpoint or documented standalone verification command using the same canonicalization.

Acceptance: request latency does not depend on artifact count; successful internal artifacts become inaccessible within 60 seconds of worker completion; retry is idempotent; receipt signature detects one-byte modification.

### PR-6 Audit export jobs and editable policies (`US-008`, `US-009`)

- Audit export creation returns 202 job ID. Worker validates chain before writing ZIP to configured storage; status/download endpoints return progress and terminal state.
- Manifest hashes every member and includes filter range, count, first/last event IDs, terminal hash, generated time, signature.
- Missing/short key fails production readiness and returns 503 without leaking configuration.
- Policy UI loads current policy from selected workspace context, not a manually entered team ID. Admin can edit allowed providers, storage backend/region, prohibit fallback, and approval mode matrix.
- Save uses `expected_version`, shows a field-by-field diff, and activates only after `Activate policy` confirmation. 409 presents current server version and `Reload policy`.
- Processing hooks call policy preflight before OpenAI/local transcription selection, extraction provider calls, and storage choice. Blocked provider generates a persisted policy decision and zero outbound calls. No fallback when prohibited.

Acceptance: audit empty and nonempty jobs download valid ZIPs; mutation blocks export; policy version increments exactly once; blocked-provider network mock observes zero calls; provider outage pauses/fails retryably without fallback.

### PR-7 Regression stabilization release gate

Fix the 23 repeatable failures without changing expected behavior or adding xfail/skip markers:

- API-key auth/fixture isolation.
- `_session_factory` reset and per-test database lifecycle.
- batch transcription mode threading.
- diarization maximum-overlap and boundary-touch behavior.
- Google Calendar connected status hermetic state.
- healthcare mode/review-status finalization persistence.
- local transcription import isolation from OpenAI.

Use `uv sync --frozen`; no ad-hoc package installs. If lockfile is stale, update it and prove a clean sync. Full test command must exit 0.

## UI and UX Specification

### Personas and journeys

Reviewer: Meetings → Review claim → inspect evidence → correct speaker → approve → publish → share snapshot. Workspace admin: Meeting Data → inspect lineage → delete → monitor → download receipt. Security admin: Compliance → Audit exports/Data policies → validate/edit → activate/download.

### Information architecture

Reuse existing shell. Meeting detail gains first-class tabs `Review`, `Transcript`, `Activity`, `Data`. Compliance retains `Overview`, `Audit exports`, `Data policies`; remove team-ID input and infer current workspace. Dashboard admin onboarding card links to Policy and a read-only sample trusted record.

### Design system

Reuse existing CSS and components. Add shared primitives only: `Tabs`, `Dialog`, `Drawer`, `InlineAlert`, `Skeleton`, `StatusBadge`, `EmptyState`, `JobProgress`. No UI library. Tokens: 4/8/12/16/24/32/48 spacing; 6/10/16 radii; 44px targets; 2px visible focus with 2px offset; body 16/24; small 14/20; headings 20/28 and 28/36. WCAG 2.2 AA. Status always icon plus text. Reduced motion disables transforms and caps opacity transitions at 100 ms.

### Shared states

Every screen must implement skeleton/loading, empty, disabled with reason, inline validation, recoverable error with `Retry`, success announcement, and permission-denied absence. Mutations retain input. `role=status` for success/progress; `role=alert` for destructive failures. Route changes focus H1. Dialogs trap focus and restore opener.

## Screen Inventory and User Flows

### 1. Review

Header: breadcrumb, title/mode/status, `Publish reviewed notes`, overflow. Desktop body 58% transcript/evidence and 42% claim list; mobile claim page with full-height evidence drawer. Claim card contains type, text, evidence, approvals, edit/approve/reject. Blocker summary is placed below primary CTA and links to each blocked card.

Empty: “No generated claims yet” with `Run extraction`. Legacy: “Evidence is unavailable for this older meeting” with `Add evidence`. Loading uses stable skeleton dimensions. Publish success shows snapshot version/hash and `Share snapshot`. Conflict dialog follows PR-1 exact labels.

### 2. Transcript

Sticky player; search/filter; paginated semantic segment list; selectable rows; speaker buttons. Mapping dialog block order: current raw label, member/guest combobox, scope, affected count, impacted claims, warning, `Apply mapping`. On success announce revised segment count; on rollback show original labels.

### 3. Activity

Filter controls for actor/event/date; chronological semantic list. Each event shows actor, action, timestamp, claim/snapshot/policy version. Safe metadata expansion. Empty state and retry retain filters.

### 4. Data

Summary cards, accessible nested lineage tree, optional CSS graph on ≥1024 px, node drawer, deletion footer. Node drawer shows kind, location class, hash availability, retention, policy, relationships. Delete modal groups internal deletion, revocation, external remediation; exact title confirmation. Job page polls persisted state, shows counts, partial retry, signed receipt download/verify.

### 5. Audit Exports

Current workspace displayed read-only. Form: date range, event types, CSV toggle. Chain-health card and recent jobs table/cards. `Validate and export` creates job. Progress labels: `Queued`, `Validating chain`, `Building files`, `Signing manifest`, `Ready`. Invalid-chain state identifies first invalid ID and disables download. Empty valid result downloads count-zero ZIP.

### 6. Data Policies

Active version card; provider checkboxes; storage/region selects from server capabilities; prohibit-fallback toggle; approval matrix by General/Healthcare/Legal; version history. `Review changes` opens diff. `Activate policy` confirmation. Conflict state offers `Reload policy`; input is not silently overwritten.

### 7. Onboarding

Admin-only dashboard card `Configure trusted records`: review compatibility policy, enable strict modes, inspect sample. Existing teams remain compatibility mode until explicit activation. New teams receive documented defaults.

### Responsive and verification

Breakpoints: mobile ≤767, tablet 768–1023, desktop ≥1024. Validate 320, 768, 1024, 1440. No horizontal page scroll at 320. Tables become labeled cards; evidence and node details use drawers. Playwright screenshots: each screen success, empty, error at desktop; Review, Transcript, Data, Policy at mobile. Axe requires zero serious/critical. Manual keyboard, 200% zoom, focus order, reduced motion, screen-reader names checklist.

## Architecture and Technical Design

- `services/trusted_records.py`: repository/orchestrator for legacy projection, claim update, speaker mapping, decisions, snapshots.
- `services/share_policy.py`: single snapshot-gating service consumed by both share routes.
- `services/governance/repository.py`: artifact/edge persistence and safe projection.
- `services/governance/jobs.py`: deletion/audit-export claim/run/retry.
- `services/governance/receipts.py`: canonical receipt sign/verify.
- Existing rule modules remain pure.
- `routes/trusted_records.py` and `routes/governance.py` become thin validation/authorization adapters.
- Add CLI or scheduled worker entrypoint `python -m meeting_notes_ai.workers.governance` with bounded polling and graceful shutdown.
- Frontend API clients use current session token consistently; no manual team IDs.
- State remains local React state plus route fetch; no Redux/query dependency.
- Job polling: 2 seconds for 30 seconds, then 10 seconds; pause hidden tab; stop terminal.
- Structured logs contain IDs/counts/status/correlation only.

Alternatives rejected: synchronous deletion/export, event-bus dependency, frontend rewrite, Redux, and starting desktop capture.

## Data, API, and Compatibility Changes

### Migration

Add migration `20260813_0008_enforce_trusted_workflows.py`:

- `shared_links.snapshot_id`, `shared_links.policy_version_id` nullable FKs.
- artifact status/error fields required for pending/external workflows.
- deletion/audit job progress attempt fields and stored receipt/export artifact references.
- meeting quarantine fields (`quarantined_at`, `quarantine_job_id`) or equivalent explicit status columns.
- constraints/indexes for job lookup and safe replay.

Migration must upgrade from 0007 and downgrade in disposable SQLite; fresh head and upgraded pre-0008 database produce ORM parity.

### API changes

Retain all current trusted/governance URLs. Modify deletion create to return 202 pending without executing. Add:

- `POST /api/v1/governance/deletions/{job_id}/run` only in test/admin development mode, or invoke worker service directly; production route disabled.
- `POST /api/v1/governance/deletions/{job_id}/verify-receipt` with receipt body, or CLI verifier.
- `GET /api/v1/governance/audit/exports/{id}` and `/download`.
- `GET /api/v1/governance/policies/capabilities`.
- `GET /api/v1/trusted/meetings/{id}/activity` includes policy/snapshot versions.

Both share endpoints preserve paths/response fields and add nullable snapshot metadata. Error envelope uses stable code/detail/blockers.

### Dependencies

Backend: add `pytest-cov` to locked dev group only if absent. Frontend dev: `@playwright/test`, `@axe-core/playwright`; add `test:e2e`, `test:a11y`, `screenshots` scripts and lockfile. No new runtime dependency.

## Security and Privacy Considerations

Authorize every query by tenant/owner and return 404 for inaccessible IDs. Encrypt external references; never return raw URLs/tokens. Audit/artifact/job logs contain no transcript/PHI. Strict share and provider policy fail closed. Canonical signatures use `hmac.compare_digest`; keys ≥32 bytes in readiness. Rate limits: deletion creation, receipt verification, audit export. Limits: 500 mapped segments, 100 evidence spans, 366-day export, one active deletion. Worker uses idempotent transitions/attempt counts; no double processing. Public shares expose immutable snapshot only. Secret scan covers repository and screenshot metadata.

## Test Strategy (TDD)

### RED sequence

1. Reproduce and pin each of the 23 full-suite failures by group; write/fix isolation tests before product work.
2. Migration 0008 fresh/upgrade/downgrade/ORM parity.
3. `test_us_001_review_ui_api.py`: trusted load, evidence seek contract, If-Match, conflict recovery, unsupported blocker.
4. `test_us_002_speaker_ui_api.py`: scopes, ambiguity, stale rollback, reapproval activity.
5. `test_us_003_share_policy.py`: both share routes, strict failure, compatibility, immutable public snapshot.
6. `test_us_007_artifact_hooks.py`: all eight artifact kinds, replay, failure reservation, tenant isolation, cycles.
7. `test_us_007_deletion_worker.py`: request latency/state, quarantine, leaf order, partial retry, external remediation, receipt verify.
8. `test_us_008_audit_job.py`: empty/nonempty persisted jobs, mutation, key readiness, download.
9. `test_us_009_preflight_hooks.py`: transcription/extraction/storage zero-call blocked cases and no fallback.
10. Playwright specs tagged `US-xxx`; axe per screen; screenshots.

Map each story AC to `US-xxx-AC-n` in test IDs/docstrings. No `NotImplementedError` guard-only tests. Route integration uses real SQLite and temp local storage; network uses respx only to prove zero/expected calls.

### Commands

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/test_api_keys.py tests/test_db_models.py tests/test_diarization.py tests/test_google_calendar.py tests/test_review_integration.py tests/test_whisper_stt.py tests/test_batch_transcription.py -q -n 0
uv run pytest tests/test_us_001* tests/test_us_002* tests/test_us_003* -q -n 0
uv run pytest tests/test_us_007* tests/test_us_008* tests/test_us_009* -q -n 0
uv run pytest -q -n 0
uv run pytest --cov=meeting_notes_ai.services.trusted_records --cov=meeting_notes_ai.services.share_policy --cov=meeting_notes_ai.services.governance --cov=meeting_notes_ai.routes.trusted_records --cov=meeting_notes_ai.routes.governance --cov-report=term-missing -q -n 0
cd frontend && npm ci
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npx playwright install --with-deps chromium
cd frontend && npm run test:e2e
cd frontend && npm run test:a11y
cd frontend && npm run screenshots
```

Fresh disposable database: Alembic upgrade head, worker one-shot, Uvicorn startup, `/healthz`, readiness, OpenAPI, actual authenticated happy path. Objective: 0 full-suite failures/errors, changed/new backend ≥90%, E2E 0 failures, axe zero serious/critical, screenshot manifest contains all required states.

## Documentation Deliverables

- README: trusted review/share and governance worker flows, config, migration, commands, troubleshooting.
- CHANGELOG next patch version: enforcement, UI, regression fixes, tests, docs.
- `docs/TRUSTED_RECORDS.md`: review UI, concurrency, snapshot sharing.
- `docs/DATA_GOVERNANCE.md`: registry hooks, worker, quarantine, receipts, exports, policies.
- `docs/GUI_SPECIFICATION.md`: exact screens/states/responsive/accessibility.
- `FEATURES-DONE.md`: only fully complete, test-backed items.
- `development-report.md`: exact RED/GREEN, full counts, coverage, gates, startup, screenshots/index, git hashes, blockers.

## Expected File Changes

Add migration 0008, trusted/share orchestration services, governance repository/jobs/receipts, worker package, MeetingActivity and MeetingData components, shared UI primitives, Playwright/axe config/specs, intentional screenshot assets, hook/worker/share/UI tests. Modify share/storage/export/webhook/PM/transcription/extraction services, models, trusted/governance routes, ReviewWorkspace, ComplianceCenter, Dashboard/Settings, styles, package locks, CI, docs, reports. Preserve research findings.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Verify claims | Accuracy distrust | US-001 | Real trusted Review UI | Grounded publish; seek ≤1 s; conflict no loss | trusted service/routes, Review | US-001 API/E2E | P0 |
| Correct speakers | Misattribution | US-002 | Mapping UI and activity | Atomic scopes; ambiguity/stale rollback | trusted service, Transcript/Activity | US-002 DB/E2E | P0 |
| Safe sharing | Sensitive records | US-003 | Shared policy gate + immutable snapshot | No strict token without eligible snapshot | share policy/routes/public | US-003 integration/E2E | P0 |
| See derivatives | Data spreads | US-007 | Hooks and lineage Data screen | All planned kinds once, tenant-safe, acyclic | registry/hooks/Data | US-007 integration/E2E | P0 |
| Delete verifiably | Retention/privacy | US-007 | Durable worker/quarantine/receipt | Request async; retry idempotent; verify signature | jobs/receipts/Data | US-007 worker/E2E | P0 |
| Audit evidence | Procurement/security | US-008 | Persisted export job/UI | Valid empty/nonempty ZIP; mutation blocked | audit jobs/routes/UI | US-008 I/O/E2E | P1 |
| Data boundaries | Privacy/local demand | US-009 | Editable policy + preflight hooks | Blocked provider zero calls/no fallback | policy hooks/UI | US-009 network/E2E | P0 |

## Risks and Mitigations

Regression breadth: fix by isolated groups first, no assertion weakening. Workflow coupling: central share/policy/registry services. Job reliability: persisted idempotent states and one-shot worker tests. Migration risk: upgrade/downgrade/ORM parity. Legacy meetings: explicit compatibility/unverified states. External deletion: remediation only. UI scope: reuse shell/primitives. Screenshot privacy: synthetic fixtures only. Missing lab/git environment: attempt and report, never fabricate.

## Definition of Done

- [ ] Two selected features complete end to end; no placeholder controls or synchronous fake jobs.
- [ ] Six stories and every AC mapped to named passing tests.
- [ ] Review → evidence → mapping → approve → publish → gated share passes authenticated E2E.
- [ ] Lineage → quarantine → worker → partial retry/remediation → signed receipt passes E2E.
- [ ] Audit jobs and editable policies use real APIs and pass empty/error/success flows.
- [ ] All eight artifact hooks and three provider preflight boundaries covered.
- [ ] Migration 0008 fresh/upgrade/downgrade/ORM parity passes.
- [ ] `uv sync --frozen` succeeds from clean environment.
- [ ] Full `uv run pytest -q -n 0` has 0 failures/errors.
- [ ] Changed/new backend modules ≥90% statement coverage.
- [ ] Ruff format/check, frontend typecheck/build, Uvicorn, worker, health/readiness/OpenAPI pass.
- [ ] Playwright and axe pass; screenshots inspected and indexed for required desktop/mobile states.
- [ ] Tenant isolation, secret scan, redaction, signature mutation, zero-call policy tests pass.
- [ ] README, CHANGELOG, API/governance/GUI docs, FEATURES-DONE, development-report match actual behavior.
- [ ] Lab gates `tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh`, `ui-gate.sh` pass when supplied; absence explicitly blocked.
- [ ] No secrets, caches, temp DBs, node_modules, dist, coverage or nonintentional generated files.
- [ ] Git add/commit/pull-rebase/push attempted; clean tree; `git-push-verify.sh` passes with valid remote or exact external blocker recorded.
- [ ] Complete project ZIP integrity/list/extract/required-file/top-level checks pass.
