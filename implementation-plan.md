# Implementation Plan

## Executive Summary

This is a **completion and integration pass**, not a new-feature pass. The previous development phase delivered tested domain rules for evidence validation, speaker mapping, approval evaluation, artifact graphs, deletion outcome classification, audit-chain export, and provider policy, but it explicitly left the sellable user journeys partial. This plan closes those gaps through two bounded features:

1. **Trusted Review Completion** (`US-001`, `US-002`, `US-003`): persistent transcript segments, claims, evidence, speaker revisions, review decisions, immutable snapshots, exact API contracts, share gating, and the complete Review/Transcript/Activity UI.
2. **Governance Workflow Completion** (`US-007`, `US-008`, `US-009`): full additive schema, artifact registration hooks, lineage APIs and Meeting Data UI, idempotent deletion jobs and signed receipts, audit export APIs/UI, policy persistence/preflight, and provider fail-closed integration.

The scope reuses the existing FastAPI, async SQLAlchemy/Alembic, React/TypeScript/Vite, storage, sharing, workflow, and rule modules. It intentionally does not revisit already-green pure rule behavior except where persistence integration exposes a defect. It also includes a **baseline-stabilization gate** for the 23 existing regression failures reported in `development-report.md`: the developer must separate environmental dependency failures from deterministic project defects, fix all deterministic failures affected by global state/import order, and cannot declare completion until the full suite is green or each remaining failure is proven pre-existing and formally blocked with reproducible evidence.

## Current-State Validation

The research remains aligned with the product: trustworthy, source-linked review and governance are still the strongest differentiation. The actual repository now contains partial v1.4.0 foundations:

- Complete pure-domain rules in `services/evidence.py`, `services/review.py`, and `services/governance/*` with 23 selected-scope tests and 99% measured scoped coverage.
- ORM classes for transcript segments, claims, evidence, policy versions, artifacts, edges, deletion jobs, and audit events in `db/models.py`.
- Migration `20260813_0006_trusted_records.py`, but it creates only transcript, claim, and evidence tables and therefore does not match the ORM or approved design.
- No `routes/trusted_records.py` or `routes/governance.py`; no persistent service orchestration; no share-route policy integration; no provider preflight hook; no artifact registration hooks.
- Existing `ReviewWorkspace.tsx` offers summary review and evidence presentation, but not claim-level persisted evidence, conflict resolution, speaker mapping, immutable publish snapshots, Activity, or Data screens.
- `ComplianceCenter.tsx` contains presentational Audit exports and Data policies tabs, but their controls are not connected to real endpoints.
- The prior report records 1,390 collected tests, 23 selected tests passing, 99% scoped coverage, frontend build/typecheck passing, startup passing, and 23 full-regression failures.

The new plan replaces the earlier broad `implementation-plan.md` with a narrower recovery contract. It does not treat partially implemented capabilities as finished and does not duplicate already completed rule tests unless needed for integration.

## Research Priorities

| Priority | Research item | Current state | Planning decision |
|---|---|---|---|
| P0 | Evidence-grounded review | Rule core complete, persistence and UI partial | Complete end to end. |
| P0 | Speaker correction and quality queue | Atomic rule complete, no persistent API/UI | Complete end to end. |
| P0 | Artifact lineage and verifiable deletion | Graph/outcome rules complete, orchestration absent | Complete end to end. |
| P1 | Tamper-evident audit export | ZIP rule complete, no persistence/API/UI | Complete operational flow. |
| P0 | Storage/provider boundaries | Rule complete, no processing hook | Complete policy persistence and preflight. |
| P0 | Regression confidence | 23 full-suite failures reported | Stabilize and require objective disposition. |
| Deferred | Bot-free desktop capture | Not started | Keep deferred to a dedicated desktop phase. |

## Selected Scope for This Pass

### Feature 1: Trusted Review Completion

Persist and expose the already-designed trusted record. Users can open a meeting, navigate canonical transcript evidence, correct speakers atomically, edit/ground claims under optimistic concurrency, approve or reject claim versions, publish an immutable snapshot, and share only a policy-compliant snapshot. Includes Review, Transcript, and Activity screens. Stories: `US-001`–`US-003`.

### Feature 2: Governance Workflow Completion

Persist complete policy/artifact/deletion/audit models; register every selected derivative; enforce provider policy before outbound work; show lineage; execute idempotent internal deletion with honest external remediation; generate signed receipts; validate/export audit chains; and provide functional Compliance/Audit/Policy/Data UI. Stories: `US-007`–`US-009`.

## Deferred Scope and Rationale

1. Bot-free Windows/macOS desktop capture, local-only summarization, managed-device deployment: separate OS/signing/model pass.
2. New CRM or PM adapters: existing four adapters are adequate for lineage integration.
3. Integration outbox/reconciliation beyond artifact registration: future reliability pass after trusted-record IDs stabilize.
4. Broad WER/DER benchmark: future model-quality pass; this pass measures grounding and review behavior only.
5. Billing and pricing: future paid-pilot phase.
6. Native mobile apps: responsive web remains supported.
7. Public-key audit signatures: HMAC is retained for compatibility; asymmetric verification is a future security enhancement.
8. Compliance certification: requires legal, contractual, and organizational work outside engineering.

## User Stories (BDD)

```json
[
  {
    "id": "US-001",
    "epic": "Trusted Review Completion",
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
    "epic": "Trusted Review Completion",
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
    "epic": "Trusted Review Completion",
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
    "epic": "Governance Workflow Completion",
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
    "epic": "Governance Workflow Completion",
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
    "epic": "Governance Workflow Completion",
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

### PR-1 Persistent trusted record (`US-001`, `US-002`)

- On transcription finalization, persist one revision of ordered `TranscriptSegment` rows. Each row has stable UUID, meeting ownership, ordinal, millisecond boundaries, raw speaker label, canonical speaker mapping, text, confidence, and revision.
- On extraction finalization, persist summary, decision, key-point, and action claims. Every claim stores status and integer version.
- Persist evidence spans only after calling existing `validate_spans`; reject empty evidence for strict publication, cross-meeting segments, out-of-bound times, and non-positive ranges with HTTP 422 and stable error codes.
- Historical meetings without persisted rows are lazily projected once from existing transcript/evidence fields when first opened. Projection is idempotent and marks unsupported claims `legacy_unverified`; it never fabricates timestamps.
- Speaker mapping persists `SpeakerMapping` and new segment revision in one transaction. Maximum 500 segment IDs. Unknown IDs, cross-meeting IDs, blank names, stale version, or ambiguous user display name fail without mutation.
- Approved impacted claims become `needs_reapproval`; draft attribution may be recalculated. Original raw labels remain immutable.
- Claims use `If-Match` integer version. Missing header returns 428; stale returns 409 with current representation and ETag; successful update increments exactly once.

Acceptance: all selected story criteria pass through service, route, database, and browser tests; a newly published strict record has 100% grounded claims; seek delta is at most 1,000 ms; stale edits and mappings produce zero partial writes.

Non-goals: biometric speaker recognition, changing STT provider, automatically grounding unsupported legacy content, or claiming a citation proves factual truth.

### PR-2 Review, approval, snapshot, and share gating (`US-001`, `US-003`)

- Add complete policy versions by meeting mode: `strict_grounding`, `required_approvals` 0–2, and reviewer roles. Existing teams receive compatibility version 1 that preserves current sharing; new teams default healthcare/legal to strict plus one approval and general to non-strict/zero.
- Review decisions target a claim ID and claim version, record actor, decision, optional rejection reason, timestamp, and policy version.
- Approval roles are checked server-side. Duplicate approval from the same actor counts once.
- Publish evaluates policy in one transaction and returns deterministic blockers: `UNSUPPORTED`, `REJECTED`, `NEEDS_REAPPROVAL`, `APPROVALS_REQUIRED`, `STALE_TRANSCRIPT`.
- Successful publish creates immutable canonical JSON snapshot with SHA-256, monotonically increasing per-meeting version, creator, policy version, and approver IDs.
- Existing share endpoints remain. New shares select the latest eligible snapshot. Strict meetings without one return 409 `POLICY_NOT_SATISFIED`; policy-service errors fail closed. Existing non-strict meetings preserve old shape and gain nullable snapshot/review fields.
- Shared snapshots never change after later transcript or claim edits.

Acceptance: strict share cannot bypass publish; snapshot bytes/hash remain stable; permissions and policy versions are auditable; all old endpoint paths remain covered.

### PR-3 Artifact registry and integration hooks (`US-007`, `US-009`)

- Complete persistence for artifacts and edges with team/meeting ownership, kind, location class, encrypted opaque reference, stable source key, content hash when available, retention state, policy version, and timestamps.
- Register raw audio, transcript revision, claim set, snapshot, export, share, webhook delivery payload, and PM task reference.
- Registration occurs in the same transaction for database derivatives; external side effects use a compensating registration step and fail visibly if metadata cannot be recorded.
- Stable source key uniqueness is `(team_id, source_key)`, not global. Replays return the existing artifact.
- Edges support planned relation types and reject self-edge, cross-team edge, cross-meeting edge unless explicitly workspace-level, duplicate edge, and cycles.
- The API returns no decrypted location references. Admin detail returns a redacted destination label only.

Acceptance: every newly created selected derivative has a row and parent edge; retries create no duplicates; cross-tenant graph access is 404; all registration-hook regressions pass.

### PR-4 Deletion workflow and receipt (`US-007`)

- Exact-title confirmation and owner/admin authorization are mandatory.
- Create at most one active deletion job per meeting; repeated requests return the existing job. Quarantine immediately hides the meeting from normal list/search/share and blocks new derivatives.
- A deterministic worker claims a job using database locking, processes leaves before parents, revokes shares, deletes internal database/object artifacts via existing services, and classifies absent data idempotently.
- External PM/webhook copies are never claimed deleted without confirmed provider delete behavior; otherwise result is `external_remediation_required` with destination label and instructions.
- Internal failure keeps quarantine, records safe error code, and permits retry of failed artifacts only.
- Complete job creates a signed JSON receipt artifact containing no transcript/claim text. It includes requestor, policy version, per-artifact result, terminal audit hash, generated timestamp, and HMAC signature.

Acceptance: internal data is inaccessible within 60 seconds of successful worker completion; retry does not repeat successful deletion; unauthorized calls cause no state change; receipt verifies with configured key.

### PR-5 Audit export and policy preflight (`US-008`, `US-009`)

- Complete database-backed hash chain with per-team serialization. Event hash includes event ID, team, actor, type, payload hash, previous hash, and timestamp in canonical JSON.
- Validation reports first invalid event and does not mutate. Export range maximum 366 days.
- Export job writes ZIP with `events.jsonl`, `manifest.json`, optional `events.csv`; manifest hashes all members and is HMAC-signed with minimum 32-byte `AUDIT_EXPORT_SIGNING_KEY`.
- Missing/short key fails readiness in production and disables export with 503, without exposing secret details.
- Complete versioned data policy: allowed providers, configured storage backend and region, prohibit-fallback boolean, approval rules. Save is optimistic by expected version.
- Every transcription/extraction/storage operation calls policy preflight before network or persistence. Blocked provider makes zero outbound calls. Unavailable approved provider pauses/fails retryably; no silent provider fallback.
- Existing teams receive compatibility policy derived from current settings.

Acceptance: one-byte mutation is detected; empty export is valid; policy conflict is 409; blocked provider yields zero mocked HTTP calls; decision record captures policy version and outcome.

### PR-6 Regression stabilization

- Reproduce baseline from a clean `uv sync --frozen` with no ad-hoc installs. If lockfile lacks declared dependencies, update lockfile intentionally.
- Address deterministic failures identified in prior report, especially session-factory global state leakage, local-transcription import isolation, diarization boundary behavior, and route fixture contamination.
- Do not relax assertions, mark failures xfail, or remove tests merely to achieve green.
- If a failure requires unavailable external credentials/service, convert it to a deterministic hermetic test with mocked network and real local persistence where appropriate.

Acceptance: `uv run pytest -q -n 0` exits 0; 0 failed, 0 errors; expected xfails are documented and unchanged or reduced.

## UI and UX Specification

### Personas and primary journeys

Reviewer: Meetings → Review → evidence → correction → approve → publish → share. Admin: Meeting Data → lineage → delete preview → job → receipt. Security admin: Compliance → Audit exports or Data policies → validate/save → visible success.

### Navigation and design system

Reuse the existing application shell and CSS tokens. No library rewrite. Meeting detail uses tabs `Review`, `Transcript`, `Activity`, `Data`. Compliance uses functional tabs `Overview`, `Audit exports`, `Data policies`. Extend existing primitives rather than introducing a component library. Add Playwright and `@axe-core/playwright` only as dev dependencies.

Tokens: spacing 4/8/12/16/24/32/48 px; radii 6/10/16 px; minimum touch 44×44 px; 2 px visible focus plus 2 px offset; body 16/24; small 14/20; heading 20/28 and 28/36. All status uses icon plus text. WCAG 2.2 AA contrast. Reduced motion disables transform and limits opacity transition under 100 ms.

### Shared states

Every screen has skeleton, actionable empty state, disabled explanation, inline validation, error with `Retry`, success announcement, and recovery behavior. Route loads focus `h1`; dialogs trap/restore focus. Mutations preserve input and disable only their own controls. Polling stops when tab hidden and resumes safely.

## Screen Inventory and User Flows

### Screen 1: Meeting Review

Header: breadcrumb, meeting title/mode, review badge, `Publish reviewed notes` primary CTA, `More`. Body desktop 58/42 transcript-evidence and claim list; mobile claims first and evidence bottom drawer. Claim card: type, text, evidence chips, status, approval count, `Edit`, `Approve`, `Reject`. Evidence click seeks player and highlights exact segment. Conflict dialog offers `Keep current`, `Use mine as new revision`, `Cancel`. Empty legacy state says no evidence and offers `Add evidence`; it never implies verification.

Success flow: open → select claim → citation seeks → edit/approve → blockers count reaches zero → publish → immutable snapshot banner → `Share snapshot`. Failure: stale save → 409 dialog → reload/current or create revision → no input loss.

### Screen 2: Transcript and Speaker Mapping

Sticky player; transcript search/filter; semantic paginated segment list; speaker label buttons. Dialog contains member/guest search, unique email for members, scope radio buttons, affected count, impacted claims, `Apply mapping`. Loading and rollback states are explicit. Approved impacted claims visibly become `Reapproval required`. Keyboard J/K moves segment, Enter opens mapping, Space controls audio only outside input.

### Screen 3: Meeting Activity

Filter row for actor/type/date. Chronological list with actor, event, timestamp, claim/snapshot/policy version. Expand reveals safe metadata, never transcript text. Empty state `No trusted-record activity yet`. Errors retain filters.

### Screen 4: Meeting Data

Summary cards; accessible nested lineage tree as primary representation; optional CSS graph on wide screens; detail drawer; destructive footer. Node details show kind, internal/external, hash availability, policy and retention. `Delete meeting data` opens grouped impact preview; exact title enables `Delete permanently`. Job progress shows completed/failed/remediation counts. Partial failure offers `Retry failed deletions`. Success offers `Download deletion receipt`.

### Screen 5: Audit Exports

Functional filter form, chain-health card, recent jobs. `Validate and export` starts real job; progress shows validation/build/sign. Invalid chain identifies event ID and blocks download. Empty result explicitly says zero events and still provides valid ZIP. Download button names file with UTC range.

### Screen 6: Data Policies

Active policy/version, server-provided provider capabilities, storage backend/region, `Prohibit fallback`, approval matrix by mode, impact summary, history. `Review changes` opens diff; `Activate policy` requires confirmed diff. Version conflict shows current version and `Reload policy`. Warning states existing meetings retain recorded policy version.

### Screen 7: Trusted-record onboarding task

Dashboard card for admins only, with `Review compatibility policy` and `Enable strict review` steps. Existing teams are never silently tightened. New team flow uses documented defaults and a read-only sample record.

### Responsive and verification

Test 320, 768, 1024, 1440 CSS px. No horizontal page scroll at 320; tables become cards; lineage uses tree; evidence drawer fills viewport. Playwright captures Review success, Review conflict, Transcript mapping, Data lineage, deletion partial/success, Audit empty/success/error, Policy validation/conflict at desktop and mobile. Axe: zero serious/critical; manual keyboard, focus, 200% zoom, reduced motion, screen-reader names.

## Architecture and Technical Design

- Extend `services/evidence.py` with async persistence orchestration without weakening pure validators.
- Extend `services/review.py` with repository-backed revisions, decisions, snapshots, blockers.
- Add `services/governance/repository.py`, `jobs.py`, `receipts.py`; extend artifacts/deletion/policies/audit modules.
- Add `routes/trusted_records.py` and `routes/governance.py`, wire in `main.py`.
- Use async SQLAlchemy transactions and current session dependency. Avoid module-global mutable state.
- Job execution: database job state plus deterministic claim/run functions. In-process background dispatch is allowed for development startup, but state makes restart safe; tests call worker directly.
- Frontend API modules `trustedRecords.ts` and `governance.ts`; route state remains local React state. Poll 2 s, back off to 10 s after 30 s.
- Registration hooks added to storage, extraction, export, sharing, webhooks, and PM integration workflows.
- Structured logs contain operation/job/artifact IDs, counts, status and correlation ID only.

Alternatives rejected: new event bus, Redux/query library, component library, destructive rewrite, and completing desktop capture in this pass.

## Data, API, and Compatibility Changes

### Schema and migration

Replace incomplete migration `20260813_0006_trusted_records.py` only if it has not shipped; because this archive is development-only and report says partial, create a corrective `20260813_0007_complete_trusted_records.py` rather than rewriting history. It adds missing `speaker_mappings`, `review_decisions`, `published_snapshots`, `policy_versions`, `policy_decisions`, `artifacts`, `artifact_edges`, `deletion_jobs`, `deletion_results`, `audit_chain_events`, and `audit_exports`, plus required constraints/indexes. Align ORM exactly. Add unique/index constraints planned previously, including `(team_id, source_key)`, `(meeting_id, version)` snapshots/policies as applicable, and one-active-deletion enforced by transaction/query for SQLite compatibility.

### APIs

- `GET /api/v1/trusted/meetings/{meeting_id}/record`
- `PUT /api/v1/trusted/meetings/{meeting_id}/claims/{claim_id}` + `If-Match`
- `POST /api/v1/trusted/meetings/{meeting_id}/speaker-mappings`
- `POST /api/v1/trusted/meetings/{meeting_id}/claims/{claim_id}/decisions`
- `POST /api/v1/trusted/meetings/{meeting_id}/publish`
- `GET /api/v1/trusted/meetings/{meeting_id}/activity`
- `GET /api/v1/governance/meetings/{meeting_id}/lineage`
- `POST /api/v1/governance/meetings/{meeting_id}/deletions`
- `POST /api/v1/governance/deletions/{job_id}/retry`
- `GET /api/v1/governance/deletions/{job_id}`
- `GET /api/v1/governance/deletions/{job_id}/receipt`
- `POST /api/v1/governance/audit/validate`
- `POST /api/v1/governance/audit/exports`
- `GET /api/v1/governance/audit/exports/{export_id}` and `/download`
- `GET /api/v1/governance/policies/current`, `GET /policies`, `POST /policies`

Responses use existing error envelope conventions. 400 malformed confirmation/filter; 403 authorization; 404 tenant-safe absence; 409 version/policy/job state; 422 evidence/validation; 428 missing If-Match; 503 missing signing key/policy dependency.

Existing share routes and workspace review route remain and delegate. Add nullable fields only. No old URL is removed.

### Dependencies

Backend runtime: none. Dev: add `pytest-cov` if absent from locked dev group. Frontend dev: Playwright and axe. Regenerate both lockfiles. Do not rely on ad-hoc `uv pip install`.

## Security and Privacy Considerations

Tenant ownership is included in every lookup and graph traversal. Cross-tenant resource IDs return 404. Audit/artifact metadata never stores transcript text, PHI, access tokens, or raw external URLs. Encrypt opaque references with current token encryption. Canonical hashing includes timestamp/event ID to prevent substitution. Use `hmac.compare_digest`. Production readiness requires 32-byte key. Strict policy and provider preflight fail closed. Deletion receipts state external remediation honestly. Maximums: 500 speaker segments, 100 evidence spans per claim, 366-day audit export, one active deletion. Rate-limit deletion/export endpoints. CSRF model remains bearer-token API; never put tokens in query strings. Logs redact content and secrets.

## Test Strategy (TDD)

### RED order

1. Baseline clean-install and full-suite reproduction test; fix deterministic baseline defects before feature integration.
2. Migration fresh/upgrade/downgrade and ORM parity tests.
3. `test_us_001_trusted_routes.py`: same-meeting evidence, seek timestamps, unsupported, 422, 428/409, lazy legacy projection.
4. `test_us_002_speaker_persistence.py`: mapping transaction, ambiguity, stale rollback, reapproval.
5. `test_us_003_publish_share.py`: approvals, immutable snapshot/hash, blockers, share fail-closed, compatibility mode.
6. `test_us_007_artifact_hooks.py`: real SQLite plus temp filesystem, idempotent hooks, tenant isolation, graph.
7. `test_us_007_deletion_job.py`: quarantine, leaf-first, absent, partial retry, external remediation, signed receipt.
8. `test_us_008_audit_routes.py`: persisted chain, mutation, empty/signed ZIP, missing key, range.
9. `test_us_009_policy_preflight.py`: versions, conflict, zero outbound call, unavailable pause, compatibility policy.
10. Playwright/axe specs for all screens and recovery states.

Every criterion is marked `US-xxx-AC-n` in test name/docstring. Existing 23 pure-rule tests remain green.

### Commands

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/test_us_001* tests/test_us_002* tests/test_us_003* -q -n 0
uv run pytest tests/test_us_007* tests/test_us_008* tests/test_us_009* -q -n 0
uv run pytest -q -n 0
uv run pytest --cov=meeting_notes_ai.services.evidence --cov=meeting_notes_ai.services.review --cov=meeting_notes_ai.services.governance --cov=meeting_notes_ai.routes.trusted_records --cov=meeting_notes_ai.routes.governance --cov-report=term-missing -q -n 0
cd frontend && npm ci
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npx playwright install --with-deps chromium
cd frontend && npm run test:e2e
cd frontend && npm run test:a11y
```

Startup against disposable DB: set `DATABASE_URL=sqlite+aiosqlite:////tmp/meeting-notes-plan.db`, run Alembic upgrade head, start Uvicorn, require `/healthz` and readiness 200, then delete DB. Changed/new backend modules ≥90% statement coverage. Full suite 0 failures/errors. UI build/typecheck zero errors; all E2E green; axe zero serious/critical.

## Documentation Deliverables

- README: complete trusted review and governance flows, config, migration, endpoints, screenshots/limitations, troubleshooting.
- CHANGELOG: next version 1.4.1, accurately list completed persistence/API/UI/regression fixes.
- `docs/TRUSTED_RECORDS.md`: schemas, concurrency, blockers, snapshots, examples.
- `docs/DATA_GOVERNANCE.md`: artifacts, policies, deletion, receipts, audit verification.
- `docs/GUI_SPECIFICATION.md`: routes, layouts, states, responsive/accessibility evidence.
- `FEATURES-DONE.md`: list only fully integrated completed items.
- `development-report.md`: exact RED/GREEN commands, full counts, coverage, screenshots, gates, migration/startup, git hashes, blockers.

## Expected File Changes

Add corrective migration, persistent repositories/job/receipt modules, trusted/governance routes, frontend API clients, Meeting Activity/Data components, Playwright config/specs, screenshots as intentional report assets, and route/integration tests. Modify ORM, main router wiring, storage/extraction/export/sharing/webhook/PM hooks, Review/Compliance/Settings/Dashboard UI, styles, lockfiles, CI, README, CHANGELOG, docs, FEATURES-DONE, development report. Do not modify research findings.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Verify every claim | Accuracy distrust | US-001 | Persistent claims/evidence/review UI | All strict published claims grounded; seek ≤1 s | evidence/review services/routes, Review | US-001 route + E2E | P0 |
| Correct attribution | Speaker misassignment | US-002 | Transactional versioned mapping | Atomic; stale/ambiguous fails; reapproval | review service, Transcript | US-002 DB + E2E | P0 |
| Prevent unsafe sharing | Sensitive record risk | US-003 | Policy, decisions, snapshots, share hook | Strict share cannot bypass publish | review/trusted routes/sharing | US-003 integration + E2E | P0 |
| See derivative copies | Data spread | US-007 | Registry hooks and lineage UI | Every derivative registered once, tenant-safe | governance repository/hooks, Data | US-007 integration | P0 |
| Delete verifiably | Retention/privacy | US-007 | Quarantine worker and receipt | Internal inaccessible ≤60 s; honest external state | deletion/jobs/receipts | US-007 job + E2E | P0 |
| Prove audit integrity | Security procurement | US-008 | DB chain/export API/UI | Mutation detected; signed empty/nonempty ZIP | audit service/routes, Audit | US-008 real ZIP + E2E | P1 |
| Enforce boundaries | Provider/data sovereignty | US-009 | Policy persistence/preflight/UI | Blocked provider yields zero calls/no fallback | policies/hooks, Policy | US-009 mocked-network integration | P0 |

## Risks and Mitigations

Migration mismatch: add corrective migration and ORM parity test. Existing test failures: clean frozen install, isolate globals/import order, no xfail masking. Legacy data: lazy idempotent projection and explicit unverified label. External deletion: remediation state only. Job restart: persisted state and idempotent worker. Concurrency: ETag/version, unique keys and transactions. UI scope: extend existing screens, no rewrite. Key loss: readiness and documented rotation limitations. Git/gates absent: attempt and report exact blocker; never fabricate.

## Definition of Done

- [ ] Both selected features work end to end with no facade or placeholder controls.
- [ ] Six stories and every AC have named test evidence.
- [ ] Persistent Review → evidence → mapping → approval → publish → share passes E2E.
- [ ] Persistent lineage → delete → retry/remediation → signed receipt passes E2E.
- [ ] Audit and policy UI use real APIs and pass success/error/empty flows.
- [ ] Complete corrective migration fresh/upgrade/downgrade and ORM parity pass.
- [ ] `uv sync --frozen` succeeds without ad-hoc packages.
- [ ] Full `uv run pytest -q -n 0` has 0 failures/errors.
- [ ] Changed/new backend coverage ≥90%.
- [ ] Ruff format/check, frontend typecheck/build, Uvicorn startup, health/readiness pass.
- [ ] Playwright Chromium and axe pass; screenshots inspected for desktop/mobile main, empty, error, success states.
- [ ] Tenant isolation, secret scanning, content-redaction, policy zero-call tests pass.
- [ ] README, CHANGELOG, trusted/governance/API/GUI docs, FEATURES-DONE, development-report match reality.
- [ ] Lab gates `tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh`, `ui-gate.sh` pass when supplied; absent scripts explicitly blocked.
- [ ] No secrets, caches, temporary DBs, node_modules, dist or coverage artifacts committed.
- [ ] Git add/commit/pull-rebase/push attempted; clean tree; `git-push-verify.sh` passes with valid remote, otherwise exact blocker documented.
- [ ] Complete project ZIP preserves top-level layout and passes integrity/list/extract/required-file verification.
