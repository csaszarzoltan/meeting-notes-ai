# Implementation Plan

## Executive Summary

This pass delivers one coherent **Trusted Meeting Record** capability through two integrated features:

1. **Evidence-Grounded Review and Approval** (`US-001`–`US-003`): canonical transcript segments, source citations for every generated claim, speaker correction, claim-level review, versioned approval policy, and publish/share gating.
2. **Governance and Data Lifecycle** (`US-007`–`US-009`): an artifact registry and lineage view, idempotent whole-meeting deletion with receipts, tamper-evident audit export, and versioned storage/provider policies enforced before processing.

The scope deliberately reuses the existing FastAPI, async SQLAlchemy/Alembic, React/TypeScript/Vite workspace, storage, sharing, audit, retention, and integration modules. It does not introduce a frontend rewrite. Bot-free desktop capture is deferred because code signing, OS audio capture, updates, crash recovery, and local-model qualification form a separate development pass. The selected scope is valuable without it and can be completed with backend, database, browser, accessibility, migration, and regression evidence in one pass.

## Current-State Validation

The research matches the repository’s current direction. Verified components include a React workspace (`frontend/src/workspace/*`), meeting review endpoint (`PATCH /api/v1/workspace/meetings/{{meeting_id}}/review`), sharing routes, encrypted local/S3 storage, retention, an append-oriented HIPAA audit logger, and PM integration adapters. The repository has no canonical claim-to-segment evidence model, review revisions, versioned approval policy, complete derivative-artifact registry, deletion receipt, or buyer-facing audit-chain export.

Key validation findings:

- Product metadata is inconsistent: package and frontend report 1.2.0, README reports 1.1.2, and CHANGELOG contains 1.3.0. Development must normalize all release-facing versions to the new version chosen by the developer, `1.4.0`.
- Existing behavior must remain available. Current meeting creation, list/detail, actions, share links, batches, storage APIs, integrations and live transcription cannot be removed or renamed.
- Existing `meeting_notes.db` is a version-controlled project asset in the baseline and must not be used as the migration test database.
- The planning environment could not execute pytest because dependencies were unavailable. The development phase must use the repository-supported `uv sync --frozen` flow and reproduce all gates.
- The research contains nine complete BDD stories. This plan selects six stories unchanged in intent and tightens their implementation contract below.

## Research Priorities

| Rank | Research priority | Planning decision |
|---|---|---|
| P0 | Evidence-grounded review and approval | Selected in full; it becomes the primary meeting-detail workflow. |
| P0 | Artifact lineage, retention, and verifiable deletion | Selected in full; integrated with review, sharing, exports, and PM delivery. |
| P0 | Bot-free desktop capture | Deferred to a dedicated desktop pass because it is not safely achievable alongside the selected data-model and review changes. |
| P1 | Quality benchmark and observability | Partially selected: grounding coverage and review metrics are required; broad WER/DER corpus remains deferred. |
| P1 | Integration reliability | Only artifact registration and deletion/remediation visibility are selected; outbox/reconciliation is deferred. |
| P1 | Accessibility and browser E2E | Selected as quality gates for every new screen. |
| P2 | Pricing experiments | Deferred until paid pilots validate the trusted-record workflow. |

## Selected Scope for This Pass

### Feature A: Evidence-Grounded Review and Approval

Provides a canonical transcript segment model, claim model, evidence links, speaker mappings, immutable revisions, claim decisions, approval-policy evaluation, and fail-closed sharing. It satisfies `US-001`, `US-002`, and `US-003`.

### Feature B: Governance and Data Lifecycle

Provides an artifact registry with directed lineage, data-policy versions, pre-processing policy decisions, meeting-level deletion jobs and receipts, external-remediation state, hash-chained audit events, chain validation, and signed export manifests. It satisfies `US-007`, `US-008`, and `US-009`.

The integration point is deliberate: claims and transcript revisions are registered artifacts; approval and share events are audited; deletion traverses all registered derivatives; policy version is attached to processing, review, publish, share, and deletion records.

## Deferred Scope and Rationale

1. **Bot-free Windows/macOS desktop companion:** deferred to phase 1.5; prerequisites are capture-spike results, signing accounts, supported OS matrix, updater design, recovery format, and local-model benchmarks.
2. **Local-only summarization and managed-device rollout:** deferred with the desktop companion; depends on model packaging, zero-egress testing, hardware profiles, and device policy transport.
3. **Broad WER/DER benchmark:** deferred to phase 1.5; this pass records evidence/review metrics but does not claim global transcription quality.
4. **New PM/CRM integrations:** deferred to phase 1.6; current adapters are sufficient to validate artifact lineage.
5. **Reliable integration outbox and reconciliation:** deferred to phase 1.6 after lineage identifiers are stable.
6. **Pricing and billing:** deferred to phase 1.7 after three paid design-partner pilots.
7. **Native mobile clients:** deferred; responsive web remains the supported mobile experience.
8. **Compliance certification or blanket legal claims:** permanently outside engineering scope; require organizational controls, counsel, contracts, and audits.

## User Stories (BDD)

```json
[
  {
    "id": "US-001",
    "epic": "Evidence-Grounded Review",
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
    "epic": "Evidence-Grounded Review",
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
    "epic": "Evidence-Grounded Review",
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
    "epic": "Governance and Data Lifecycle",
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
    "epic": "Governance and Data Lifecycle",
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
    "epic": "Governance and Data Lifecycle",
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

### PR-A1 Canonical transcript and evidence model

**Evidence addressed:** users do not trust opaque summaries and speaker attribution remains error-prone. **Stories:** `US-001`, `US-002`.

- On completion of transcription, persist ordered immutable source segments with stable UUIDs, `start_ms`, `end_ms`, raw speaker label, canonical speaker ID, text, confidence when supplied, and source revision number.
- Persist each generated summary, decision, key point, and action as a `Claim` with type, text, status (`draft`, `approved`, `rejected`), version, and one or more ordered evidence spans.
- An evidence span references one transcript segment and may narrow its start/end boundaries. The API rejects evidence outside the segment or meeting.
- A publishable claim must have at least one valid span. Existing historical meetings without spans remain readable and display `legacy_unverified`; they cannot enter strict-mode publication until reviewed and linked.
- Speaker correction creates a revision and updates selected segments atomically. It never mutates the original raw label. A recalculation job updates draft claim attribution, but approved claims are not silently changed and instead become `needs_reapproval`.
- Optimistic concurrency uses integer `version` and HTTP `If-Match`; stale writes return `409` with current version and server representation.

**Acceptance:** 100% of newly published claims have valid same-meeting evidence spans; audio navigation lands within 1 second; cross-meeting span references return `422`; stale edits never overwrite newer revisions; batch speaker mapping is atomic.

**Non-goals:** changing transcription providers, automatic voice biometrics, claiming evidence proves factual truth, and retroactively auto-grounding all historical data.

### PR-A2 Human review, policy, and share gating

**Evidence addressed:** sensitive outputs need explicit approval and reconstructable decisions. **Stories:** `US-001`, `US-003`.

- Team admins configure a versioned approval policy by meeting mode with `strict_grounding`, required approval count (0–2), and allowed reviewer roles (`admin`, `member`). Healthcare and legal default to strict grounding and one approval for new teams; existing teams receive a non-breaking policy with zero required approvals until an admin opts in.
- Review decisions apply to a claim version and record actor, timestamp, reason for rejection, and policy version.
- Publish evaluates all claims and approvals in one transaction. It returns a deterministic blocker list rather than a generic failure.
- Existing share endpoints remain, but create-share calls invoke the same policy evaluator. If evaluation is unavailable or fails, strict-policy meetings fail closed with `409 POLICY_NOT_SATISFIED`; non-strict legacy meetings preserve prior behavior.
- Published snapshots are immutable. Later transcript/speaker changes create a new draft revision and do not alter prior shares.

**Acceptance:** strict meetings cannot publish/share with unsupported, rejected, stale, or insufficiently approved claims; policy evaluation completes and returns blockers; every successful share records snapshot ID, policy version and approver IDs; no prior endpoint path is removed.

**Non-goals:** legal-signature workflows, multi-organization approvals, email approval, and automated clinical/legal validation.

### PR-B1 Artifact registry and lineage

**Evidence addressed:** sensitive content is copied into exports, shares, integrations, and derived records. **Stories:** `US-007`, `US-009`.

- Register artifacts for raw audio, transcript revision, claim set, published snapshot, export, share, webhook delivery payload, and PM integration task reference.
- Each artifact stores team/meeting ownership, kind, location class (`database`, `object_storage`, `external`), opaque location reference, content hash when internally retrievable, retention state, created/deleted timestamps, and governing policy version.
- Directed lineage edges use relation types `derived_from`, `published_as`, `shared_as`, `exported_as`, `delivered_as`, and `synced_as`.
- The registry is metadata only. It must not duplicate PHI or store access tokens; external references are encrypted using the existing token-encryption boundary.
- Existing flows register artifacts idempotently using stable source keys. Registration failure prevents creation of new share/export/integration artifacts and surfaces a retryable error.

**Acceptance:** every newly created selected artifact has one registry row and required parent edge; repeated registration does not duplicate rows; tenant queries cannot reveal another team’s graph; lineage endpoint returns the complete acyclic graph for the meeting.

### PR-B2 Whole-meeting deletion and receipts

**Evidence addressed:** users need verifiable lifecycle control over all derivatives. **Stories:** `US-007`.

- Admin or meeting owner requests deletion after entering the exact meeting title. API creates one idempotent deletion job and immediately changes meeting visibility to `quarantined`.
- Worker processes graph leaves before parents. Internal artifacts are deleted using current storage/database services. Shares are revoked. External PM/webhook copies are marked `external_remediation_required` unless an adapter exposes a verified delete operation.
- A failed internal deletion leaves the meeting quarantined and retryable. Successful internal deletion must be inaccessible within 60 seconds.
- A final signed receipt lists job ID, requestor, policy version, artifact ID/kind, outcome, timestamp, external remediation details, and terminal audit hash. Receipts contain no transcript or claim text.
- Repeating the request returns the existing job/receipt and does not recreate work.

**Acceptance:** all internal artifacts have `deleted` or `already_absent`; failures are explicit; retry is idempotent; external copies never falsely report deletion; unauthorized requests return `403` without changing visibility.

### PR-B3 Audit chain export and provider/region policy

**Evidence addressed:** security teams need defensible audit evidence and policy enforcement before data leaves an approved boundary. **Stories:** `US-008`, `US-009`.

- Replace neither the current audit API nor historical log. Add database-backed audit-chain records for selected events, with previous hash, event hash, canonical JSON payload hash, team, actor, event type and timestamp. Import is not required for historical file logs.
- Validation identifies the first invalid or missing link and never rewrites events.
- Export produces a ZIP containing `events.jsonl`, `manifest.json`, and optional `events.csv`; manifest includes filters, count, first/last IDs, terminal hash, SHA-256 hashes of members, generated time, and HMAC-SHA256 signature from `AUDIT_EXPORT_SIGNING_KEY`.
- Data policy versions define allowed processing providers (`openai`, `local`), storage backends/regions, and failover prohibition. Before meeting processing, policy evaluation creates a decision record. No silent fallback is allowed.
- Existing teams receive a compatibility policy reflecting their current configured providers and storage. Admin edits create a new version; old records retain old version IDs.

**Acceptance:** one-byte mutation causes validation failure at the changed event; empty export is valid with count 0; missing signing key disables export with readiness failure; blocked provider creates no outbound provider call; provider outage pauses the job without fallback.

## UI and UX Specification

### Personas and journey

- **Reviewer:** verifies claims against evidence, corrects speakers, approves and publishes.
- **Workspace admin:** configures approval/data policy, examines lineage, deletes meetings, and exports audit evidence.
- **Member:** views meeting records and shares only when policy permits.

Primary journey: sign in → Meeting library → Meeting detail/Review → inspect claim evidence → correct speaker if needed → approve claims → publish → share. Governance journey: Compliance → meeting lineage → delete preview or audit export → monitor job → download receipt.

### Information architecture

Keep the existing application shell and navigation. Add no new top-level center. Use:

- **Meetings** → Meeting detail with tabs `Review`, `Transcript`, `Activity`, `Data`.
- **Compliance** → tabs `Overview`, `Audit exports`, `Data policies`.
- **Settings** → `Approval policy` card linked from Compliance.

Desktop navigation remains left rail. Tablet uses collapsed rail. Mobile uses existing bottom navigation and an overflow menu for Compliance. Routes:

- `/app/meetings/:meetingId/review`
- `/app/meetings/:meetingId/transcript`
- `/app/meetings/:meetingId/activity`
- `/app/meetings/:meetingId/data`
- `/app/compliance/audit`
- `/app/compliance/policies`

### Design system

Reuse the existing CSS and React component conventions. Add shared primitives under `frontend/src/workspace/components/`: `StatusBadge`, `InlineAlert`, `Skeleton`, `ConfirmDialog`, `Tabs`, `Drawer`, `Timeline`, and `EmptyState`. Do not add a component-library dependency. Extend CSS custom properties in `frontend/src/styles.css`:

- spacing: 4, 8, 12, 16, 24, 32, 48 px;
- radii: 6, 10, 16 px;
- type: 12/16 caption, 14/20 body-small, 16/24 body, 20/28 heading-3, 28/36 heading-2;
- focus ring: 2 px solid `--focus`, 2 px offset;
- elevations: border-only, low shadow, modal shadow;
- status colors with paired icon and text, never color alone.

All text/background pairs meet WCAG 2.2 AA. `prefers-reduced-motion: reduce` disables transforms and limits transitions to opacity under 100 ms. Touch targets are at least 44×44 CSS pixels.

### Global states

Every API region has skeleton, empty, error with exact `Retry` control, and success announcement. Mutations disable only the affected control, retain user input, show progress text, and are idempotent. Toasts use `role="status"`; destructive failures use inline `role="alert"`. Route changes focus the page `h1`; dialogs trap focus and restore it to the opener.

## Screen Inventory and User Flows

### 1. Meeting Review

**Layout:** existing product header; breadcrumb `Meetings / {{title}}`; title row with mode, review status, `Publish` primary button and `More` menu; tab row; two-column desktop body. Left 58% is transcript/audio evidence, right 42% is claim review. On tablet the panes are 50/50; below 768 px claims occupy the page and evidence opens as a bottom drawer.

**Claim card:** type, draft text, grounding badge, approval count, evidence chips, `Approve`, `Edit`, `Reject`. Selecting a chip highlights source text and seeks audio. Exact primary CTA is `Publish reviewed notes`; disabled label remains and blocker count appears below.

**States:** skeleton cards; empty “No generated claims yet” with `Run extraction`; legacy banner “Evidence not available for this older meeting” with `Add evidence`; unavailable audio keeps text evidence usable; 409 conflict opens a side-by-side `Resolve conflict` dialog; publish success shows immutable snapshot version and `Share` CTA.

**Failure recovery flow:** save edit → API 409 → dialog shows “Your version” and “Current version” → choose `Keep current`, `Use mine as new revision`, or `Cancel` → resubmission creates a new revision → focus returns to updated card.

### 2. Transcript and Speaker Mapping

**Layout:** header and tabs; sticky audio player; filter/search bar; virtualized-looking but dependency-free segmented list using normal semantic list markup and incremental pagination; speaker labels as buttons.

Click path: speaker button → `Map speaker` dialog → searchable member/guest control → segment scope (`This segment`, `Selected segments`, `All Speaker N segments`) → preview count and impacted draft claims → `Apply mapping` → progress → success summary. Approved impacted claims show “Reapproval required.”

**States:** no segments, low-confidence badge, ambiguous member names resolved by email, stale-version conflict, recalculation failure with original mapping intact. Keyboard: `J/K` moves segments, Enter opens selected segment, Space controls audio only when focus is not inside an input.

### 3. Meeting Activity

**Layout:** filters for actor/type/date; chronological semantic list; each event shows actor, exact action, timestamp, policy/snapshot version, and expandable metadata. No PHI appears in collapsed event text. Empty state says “No review activity recorded.” Export is not offered here.

### 4. Meeting Data and Lineage

**Layout:** summary cards for artifact count, internal, external, deletion state; main lineage presented as an accessible nested tree plus optional CSS-connected visual layout; right detail drawer; sticky destructive footer.

Click path: select node → drawer shows kind, location class, hash availability, parent/child edges, retention and policy version. `Delete meeting data` opens impact preview grouped into Internal deletions, Revocations, and External remediation. User types exact title; `Delete permanently` enables; job view replaces graph during execution; final state provides `Download deletion receipt`.

**States:** graph skeleton, no registered artifacts with historical-data explanation, partial graph warning, deletion in progress with polling, partial failure with `Retry failed deletions`, success receipt, unauthorized controls absent rather than disabled.

### 5. Compliance Audit Exports

**Layout:** page title and explanation; filter panel (team fixed to current workspace, start/end timestamps, event types, format); chain health card; recent exports table. Primary CTA `Validate and export`.

Click path: choose filters → count preview → `Validate and export` → progress steps `Validating chain`, `Building files`, `Signing manifest` → success row → `Download ZIP`. Invalid chain displays first invalid event ID and disables export. Empty range allows export and explicitly states zero events.

### 6. Data Policies

**Layout:** active-version summary; provider checkboxes; storage backend and region selectors populated from server capabilities; `Prohibit fallback` default checked; approval policy by mode; impact summary; version history table. Primary CTA `Review changes`, then confirmation CTA `Activate policy`.

**States:** loading capabilities, no configurable alternative, invalid combination inline error, readiness failure, conflict if another admin saved first, success with new version number. Exact warning: “Existing meetings keep their recorded policy version. This policy applies to new processing and new derivative artifacts.”

### Onboarding and first run

Existing teams see a non-blocking dashboard task `Configure trusted records` with two steps: review compatibility policy and enable strict approval modes. New teams complete these steps after workspace creation. The flow never silently turns on strict sharing for existing teams. A sample read-only meeting demonstrates evidence chips without creating billable processing.

### Responsive and accessibility verification

Test at 320, 768, 1024, and 1440 CSS pixels. At 320 px, no horizontal page scrolling; tables become labeled cards; lineage defaults to tree; evidence uses full-height drawer. All functionality is keyboard accessible. Use semantic `main`, `nav`, `h1`–`h3`, `ul`, `button`, `dialog`, `form`, and labeled inputs. Automated axe checks require zero serious or critical violations; manual checks cover focus order, screen-reader labels, zoom to 200%, reduced motion, and color-independent status.

## Architecture and Technical Design

### Boundaries

- `services/evidence.py`: transcript segment/claim/evidence validation and projection.
- `services/review.py`: revision, claim decision, publish snapshot, blocker evaluation.
- `services/governance/artifacts.py`: idempotent registry and lineage queries.
- `services/governance/deletion.py`: deletion orchestration and receipts.
- `services/governance/policies.py`: policy versioning and preflight decisions.
- `services/governance/audit_chain.py`: canonical event hashing, verification and export.
- `routes/trusted_records.py`: review/evidence/snapshot endpoints.
- `routes/governance.py`: lineage/deletion/audit/policy endpoints.
- React API clients `frontend/src/api/trustedRecords.ts` and `governance.ts`; UI screens remain within workspace conventions.

No event-bus dependency is added. Existing route/service code calls registry/audit services in the same database transaction for metadata records. External and object-storage deletion runs through a database-backed job claimed with row locking; development may expose a deterministic `run_deletion_job` service called by a background task, while tests call it directly. Do not rely solely on in-process background tasks for production reliability.

### Data flow

Transcription completion → segments → extraction claims and evidence → artifact registration → review decisions → policy evaluator → immutable snapshot → share/export/integration artifact edges. Deletion walks the artifact graph in reverse topological order → adapters/storage deletion → audit events → signed receipt artifact.

Frontend uses existing React local state and API functions. Server state is fetched per route; no Redux or query-library dependency is introduced. Poll deletion/export jobs at 2 seconds while visible, with backoff to 10 seconds after 30 seconds and stop on terminal status.

## Data, API, and Compatibility Changes

### Migration

Add Alembic migration `migrations/versions/20260813_0006_trusted_records.py`. New tables:

- `transcript_segments(id, meeting_id, ordinal, start_ms, end_ms, raw_speaker_label, speaker_id, text, confidence, revision, created_at)`; unique `(meeting_id, revision, ordinal)`.
- `claims(id, meeting_id, claim_type, text, status, version, created_at, updated_at)`.
- `claim_evidence(id, claim_id, segment_id, start_ms, end_ms, ordinal)`.
- `speaker_mappings(id, meeting_id, raw_label, canonical_name, user_id nullable, version, created_by, created_at)`.
- `review_decisions(id, claim_id, claim_version, decision, reason nullable, actor_id, policy_version_id, created_at)`.
- `published_snapshots(id, meeting_id, version, policy_version_id, payload_json, payload_sha256, created_by, created_at)`.
- `policy_versions(id, team_id, version, approval_json, provider_json, storage_json, created_by, created_at, activated_at)`.
- `policy_decisions(id, meeting_id, policy_version_id, operation, outcome, reasons_json, created_at)`.
- `artifacts(id, team_id, meeting_id, kind, location_class, location_ref_encrypted, source_key, content_sha256, retention_state, policy_version_id, created_at, deleted_at)`; unique `(team_id, source_key)`.
- `artifact_edges(parent_id, child_id, relation_type, created_at)`; unique tuple.
- `deletion_jobs(id, meeting_id, status, requested_by, policy_version_id, requested_at, completed_at, error_summary)`.
- `deletion_results(id, job_id, artifact_id, outcome, detail_code, completed_at)`.
- `audit_chain_events(id, team_id, actor_id, event_type, payload_sha256, previous_hash, event_hash, created_at)`.
- `audit_exports(id, team_id, filters_json, status, terminal_hash, manifest_sha256, requested_by, created_at, completed_at)`.

Use UUID strings consistent with existing models; JSON stored as Text where project portability requires SQLite/Postgres parity. Foreign keys use restrictive deletion except artifact/deletion histories, which retain non-content identifiers.

### Endpoints

All endpoints require current auth and team/meeting authorization.

- `GET /api/v1/trusted/meetings/{{id}}/record` → `{meeting, transcript_version, segments, claims, blockers, snapshot}`.
- `PUT /api/v1/trusted/meetings/{{id}}/claims/{{claim_id}}` with `If-Match` and `{text, evidence:[{segment_id,start_ms,end_ms}]}` → updated claim/version; `409` conflict; `422` evidence error.
- `POST /api/v1/trusted/meetings/{{id}}/speaker-mappings` with `{raw_label, canonical_name, user_id, segment_ids, expected_transcript_version}` → `{mapping, transcript_version, impacted_claim_ids}`.
- `POST /api/v1/trusted/meetings/{{id}}/claims/{{claim_id}}/decisions` with `{decision:"approve"|"reject", reason}` → decision and blockers.
- `POST /api/v1/trusted/meetings/{{id}}/publish` with `{expected_transcript_version}` → `201 {snapshot_id, version, sha256}` or `409 {code, blockers[]}`.
- `GET /api/v1/governance/meetings/{{id}}/lineage` → normalized `{nodes, edges, warnings}`.
- `POST /api/v1/governance/meetings/{{id}}/deletions` with `{confirmation_title}` → `202 {job_id,status}`; repeated call returns same active/terminal job.
- `GET /api/v1/governance/deletions/{{job_id}}` → status/results/receipt availability.
- `GET /api/v1/governance/deletions/{{job_id}}/receipt` → signed JSON download.
- `POST /api/v1/governance/audit/validate` with filters → `{valid,count,terminal_hash,first_invalid_event_id}`.
- `POST /api/v1/governance/audit/exports` with `{start,end,event_types,include_csv}` → `202`.
- `GET /api/v1/governance/audit/exports/{{id}}` and `/download`.
- `GET /api/v1/governance/policies/current`; `GET /policies`; `POST /policies` with complete approval/provider/storage configuration and expected current version.

Extend existing `POST .../share` internally; response shape remains backward compatible. Add optional `snapshot_id`, `policy_version`, and `review_status` fields only. Existing workspace review endpoint remains and delegates compatible operations to review service.

### Dependency changes

Backend: no runtime dependency required. Use standard `hashlib`, `hmac`, `json`, `zipfile`, and existing cryptography/token encryption. Frontend: add Playwright and `@axe-core/playwright` as dev dependencies because the repository has no browser E2E runner and this plan requires UI verification. Add scripts `test:e2e` and `test:a11y`. Lockfile must be regenerated intentionally.

## Security and Privacy Considerations

- Enforce tenant ownership in every query, including edge traversal and receipt download. Add cross-tenant negative tests.
- Never store transcript text in audit payloads, lineage location references, job errors, or logs.
- Encrypt external location references and redact them in normal API responses.
- Canonicalize audit payloads with sorted UTF-8 JSON and fixed separators; compare signatures with `hmac.compare_digest`.
- Require `AUDIT_EXPORT_SIGNING_KEY` of at least 32 bytes in production readiness; never return it.
- Validate graph ownership and prevent cycles at service level.
- Fail closed for strict policy, unavailable policy evaluator, blocked provider, invalid audit chain, and incomplete authorization.
- Deletion receipts prove attempted/result state, not deletion by an external vendor. Use `external_remediation_required` accurately.
- Apply request limits to evidence arrays, maximum 500 segment IDs per speaker operation, audit export range maximum 366 days, and one active deletion per meeting.
- Do not include PHI in browser telemetry. Log operation IDs, counts, statuses and correlation IDs only.

## Test Strategy (TDD)

### RED sequence and acceptance mapping

1. Write model/migration tests for all new tables, constraints and SQLite/Postgres-compatible metadata.
2. `test_evidence_service.py`: valid spans, outside-span, cross-meeting, unsupported claims, same-meeting ownership (`US-001` ACs).
3. `test_speaker_mapping.py`: atomic all/selected mapping, ambiguity handling, approved-claim reapproval, rollback on recalculation failure (`US-002`).
4. `test_review_policy.py`: strict blockers, approval counts, stale claim version, fail-closed evaluator, successful snapshot/share (`US-003`).
5. `test_artifact_lineage.py`: idempotent registration, relation graph, cycle rejection, tenant isolation, historical-empty warning (`US-007`).
6. `test_deletion_workflow.py`: leaf-first internal deletion, already-absent, external remediation, partial failure/retry, 60-second accessibility assertion using controlled clock (`US-007`).
7. `test_audit_chain.py`: stable canonical hash, mutation detection, missing link, empty range, signed manifest and missing-key readiness (`US-008`).
8. `test_data_policy.py`: version conflict, allowed provider, blocked provider with mocked no-call assertion, no fallback, compatibility defaults (`US-009`).
9. Route integration tests exercise real SQLite sessions and temporary local storage, not only mocks.
10. Browser tests cover review-to-publish, conflict recovery, lineage-to-deletion receipt, audit empty export, policy validation, mobile drawer and keyboard-only flow.

Each Given/When/Then criterion in the six embedded stories must appear in test docstrings or parametrization IDs as `US-xxx-AC-n`. A traceability test parses `implementation-plan.md` story IDs and fails if no matching test marker exists.

### Commands

Supported existing commands:

```bash
uv sync --frozen
uv run ruff check .
uv run pytest tests/test_evidence_service.py tests/test_speaker_mapping.py tests/test_review_policy.py -q -n 0
uv run pytest tests/test_artifact_lineage.py tests/test_deletion_workflow.py tests/test_audit_chain.py tests/test_data_policy.py -q -n 0
uv run pytest -q -n 0
cd frontend && npm ci
cd frontend && npm run typecheck
cd frontend && npm run build
```

Planned commands after adding browser tooling:

```bash
cd frontend && npx playwright install --with-deps chromium
cd frontend && npm run test:e2e
cd frontend && npm run test:a11y
uv run pytest --cov=meeting_notes_ai.services.evidence --cov=meeting_notes_ai.services.review --cov=meeting_notes_ai.services.governance --cov-report=term-missing -q -n 0
uv run uvicorn meeting_notes_ai.main:app --host 127.0.0.1 --port 8000
```

Coverage is at least 90% statement coverage on every new/changed backend service module. Frontend critical behavior is covered by Playwright; typecheck and build must have zero errors. Accessibility gate has zero serious/critical axe findings and passes the manual checklist. Startup passes when `/healthz` and readiness endpoint return success against a fresh migrated temporary database.

### Lab gates

If gate scripts are supplied by the lab environment, run from project root in this order:

```bash
bash tdd-gate-v3.sh
bash bdd-gate.sh
bash security-gate.sh
bash doc-sync-check.sh
bash ui-gate.sh
bash git-push-verify.sh
```

Do not fabricate missing scripts inside the product repository unless the lab contract explicitly supplies their canonical implementation. If absent, record `BLOCKED: gate script not supplied` in `development-report.md`; all equivalent repository commands still must pass. Git push is complete only when `git-push-verify.sh` confirms local HEAD equals the configured remote branch HEAD. Never create a fake remote.

## Documentation Deliverables

- `README.md`: normalize version; add Trusted Meeting Record overview, review/publish workflow, governance flow, environment variables, migrations, startup, and supported limitations.
- `CHANGELOG.md`: add 1.4.0 Added/Changed/Security/Tests/Migrations sections with no unsupported claims.
- `docs/TRUSTED_RECORDS.md`: data model, review semantics, blockers, snapshots, APIs and examples.
- `docs/DATA_GOVERNANCE.md`: artifact kinds/relations, policy behavior, deletion outcomes, receipt semantics, audit export verification, external-remediation limitation.
- `docs/GUI_SPECIFICATION.md`: update implemented routes, states, responsive behavior and accessibility evidence.
- `FEATURES-DONE.md`: mark only test-proven features and link test evidence.
- `development-report.md`: requirement-to-files/tests summary, targeted/full test outputs, coverage, migrations, screenshots, accessibility checks, gate results, startup evidence, known limitations, commit hash and verified remote hash.

## Expected File Changes

**Add:** migration `20260813_0006_trusted_records.py`; backend models/services/routes listed above; frontend API clients, primitives, detailed screens or extensions to `ReviewWorkspace.tsx`, `ComplianceCenter.tsx`, and `WorkspaceSettings.tsx`; new backend tests; `frontend/e2e/*.spec.ts`; Playwright config; two new docs; `development-report.md`.

**Modify:** `db/models.py`, `main.py`, relevant transcription/extraction/workflow/sharing/export/storage services for registration hooks, workspace routing/UI, styles, package files, README, CHANGELOG, GUI spec, FEATURES-DONE, readiness configuration and lockfiles. Preserve all unrelated behavior and public paths.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Verify opaque AI claims | Accuracy and evidence are unmet buying needs | US-001 | Canonical claims and spans | Every published claim has same-meeting evidence; seek within 1 s | `services/evidence.py`, Review screen | `US-001-AC-1..3`, Playwright review | P0 |
| Correct attribution | Speaker identification remains unreliable | US-002 | Versioned atomic speaker mapping | No partial mapping; ambiguity requires email; approved claims need reapproval | `services/review.py`, Transcript screen | `US-002-AC-1..3` | P0 |
| Prevent unsafe sharing | Sensitive outputs need human approval | US-003 | Versioned policy and fail-closed share evaluator | Unsupported/rejected/stale claims block strict sharing | `services/review.py`, `routes/trusted_records.py`, sharing hook | `US-003-AC-1..3` | P0 |
| Know every derivative | Copies spread to exports, shares and integrations | US-007 | Artifact registry and lineage graph | Idempotent complete graph; cross-tenant queries denied | `governance/artifacts.py`, Data screen | `US-007-AC-1`, lineage integration/E2E | P0 |
| Delete verifiably | Internal and external copies need explicit outcomes | US-007 | Quarantine, leaf-first deletion and signed receipt | Internal inaccessible ≤60 s; external reported as remediation | `governance/deletion.py`, Data screen | `US-007-AC-2..3`, deletion E2E | P0 |
| Defensible audit evidence | Security reviewers need tamper detection | US-008 | Hash chain validation and signed ZIP export | Mutation identified; empty export valid; no secret exposure | `governance/audit_chain.py`, Audit screen | `US-008-AC-1..3` | P1 |
| Enforce data boundaries | Buyers need provider/region control | US-009 | Versioned persistence/provider policy preflight | Blocked provider gets zero calls; no silent fallback | `governance/policies.py`, Policies screen | `US-009-AC-1..3` | P0 |

## Risks and Mitigations

- **Migration breadth:** many new tables. Mitigate with one additive migration, downgrade test, fresh/upgrade database tests, and no destructive column changes.
- **Legacy meetings lack spans:** label `legacy_unverified`; allow prior read behavior; require explicit grounding only under strict publication.
- **Extraction providers may not return citations:** add deterministic segment retrieval/validation stage and prohibit fabricated spans; unsupported remains visible.
- **Deletion across external systems is unverifiable:** represent remediation honestly and never mark it deleted without provider evidence.
- **Audit HMAC is not a public-key signature:** document the trust model; HMAC is selected to avoid new dependencies. Public verification is deferred.
- **Frontend complexity:** extend the existing workspace and CSS instead of introducing a new design system or state framework.
- **Race conditions:** use optimistic versions, unique source keys, one active deletion constraint and transactional writes.
- **Policy outage can interrupt workflows:** strict operations fail closed with explicit retry; legacy compatibility mode preserves prior behavior.
- **Gate or git environment absent:** report blocked external gate accurately; do not fake scripts, commits or push verification.

## Definition of Done

- [ ] Both selected features are complete with no facade, placeholder, hard-coded success, or unpersisted critical state.
- [ ] All six embedded stories and every acceptance criterion have implementation and named test evidence.
- [ ] Review → evidence → correction → approval → publish → share works end to end.
- [ ] Lineage → deletion preview → quarantine → processing → receipt works end to end, including partial failure recovery.
- [ ] Audit validation/export and policy version/preflight work with real database and filesystem I/O.
- [ ] Additive migration upgrades a prior schema and downgrades in a disposable database.
- [ ] Existing API paths and non-strict legacy behavior remain covered by regression tests.
- [ ] Targeted tests pass, then `uv run pytest -q -n 0` passes.
- [ ] New/changed backend service modules achieve at least 90% statement coverage.
- [ ] Ruff, frontend typecheck, frontend production build and application startup pass.
- [ ] Playwright Chromium E2E and accessibility suites pass; zero serious/critical axe violations.
- [ ] Manual UI checks pass at 320, 768, 1024 and 1440 px, keyboard only, 200% zoom and reduced motion; screenshots are attached to the development report when tooling permits.
- [ ] README, CHANGELOG, API/governance docs, GUI spec, FEATURES-DONE and development-report match actual behavior.
- [ ] `tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh` and `ui-gate.sh` pass when supplied; absent external scripts are explicitly recorded as blocked, never fabricated.
- [ ] No credentials, tokens, temporary databases, caches, `node_modules`, coverage output, screenshots outside intentional report assets, or build directories are committed.
- [ ] Secret scanning and tenant-isolation tests pass.
- [ ] Git commit and push are completed; `git-push-verify.sh` confirms local and remote HEAD when a valid lab remote is supplied.
- [ ] `development-report.md` contains exact commands, results, coverage, gate evidence, commit hash, remote hash and known limitations.
- [ ] Complete project is packaged with its original top-level layout; ZIP integrity, content list, separate extraction and required-file checks pass.
