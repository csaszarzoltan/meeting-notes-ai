# MeetingNotesAI v0.5.0 Product and UX Requirements Report

**Assessment basis:** `ZipPrompt.md`, treated as a flattened ZIP archive containing the application source, tests, documentation, examples, deployment files, and historical planning materials.  
**Assessment type:** Product analysis, UX review, workflow analysis, and next-version software requirements.  
**Important evidence note:** The repository contains a FastAPI product with one minimal HTML compliance dashboard, but not a complete end-user web application. Therefore, findings about API behavior and the dashboard are observed facts. Findings about future screens, navigation, and user habits are explicitly labelled as inferences.

## Executive summary

MeetingNotesAI is an API-first micro-SaaS that converts audio into transcripts and structured meeting notes. It supports general meetings, healthcare SOAP notes, and legal/deposition summaries, plus batch processing, teams, public sharing, exports, webhooks, and a HIPAA-oriented compliance suite.

The product has broad backend capability, but the user experience is fragmented. The primary meeting workflow and the HIPAA transcription workflow are separate, users must choose technical endpoints rather than complete a coherent task, and most operational capabilities have no product UI. The compliance dashboard is especially risky because several metrics are static, incomplete, process-local, or semantically misleading. Documentation also conflicts with code and changelog details in places, which makes adoption harder and can create false confidence.

The next version should not begin by adding more isolated endpoints. It should first create a unified, safe, observable workflow: upload or record, choose context, confirm privacy settings, process, review, correct, approve, save, share, and export. In parallel, production blockers such as secret handling, persistent encrypted storage, reliable authorization, truthful compliance metrics, automated audit retention, and end-to-end PHI protection must be resolved.

---

# 1. Product understanding

## What the application appears to do

### Observed

MeetingNotesAI is a FastAPI-based micro-SaaS for:

1. Uploading audio files.
2. Transcribing audio through OpenAI Whisper.
3. Extracting summaries, action items, decisions, and key points through an LLM.
4. Applying a mode:
   - **General:** standard meeting notes.
   - **Healthcare:** SOAP-style notes, consent state, HIPAA markers, and optional PHI redaction through a separate transcription route.
   - **Legal:** deposition summaries, testimony points, objections, and case metadata.
5. Exporting content as JSON, Markdown, PDF, or batch ZIP.
6. Organizing work in teams with admin, member, and viewer roles.
7. Processing up to ten audio files in a batch.
8. Sharing meeting summaries through public links with expiration and revocation.
9. Sending signed webhooks after batch completion.
10. Providing HIPAA-related controls: regex PHI detection, audit logs, envelope encryption, BAA generation, and a compliance dashboard.

The architecture is modular, with routers, service objects, Pydantic models, async SQLAlchemy, JWT authentication, and an extensive test suite. However, source excerpts and repository materials also show incomplete functions, historical RED-phase tests, pre-existing failures, documentation drift, and partially implemented or contradictory claims. The actual deployability of every documented route cannot be assumed without running the full repository.

## Likely users

### Primary segments

1. **Knowledge workers and team leads**
   - Want quick transcripts, decisions, and assigned actions.
   - Care about speed, editability, sharing, and export.

2. **Healthcare practitioners and practice operations staff**
   - Want SOAP notes and reduced documentation burden.
   - Care about consent, PHI handling, auditability, access control, and defensible compliance evidence.

3. **Legal professionals**
   - Want deposition or interview summaries, testimony extraction, objections, and case context.
   - Care about exact source traceability, timestamps, confidentiality, and edit history.

4. **Workspace administrators and compliance officers**
   - Manage members, roles, retention, encryption, BAAs, audit review, webhook integrations, and policy configuration.

5. **Developers and integration partners**
   - Consume the REST API, configure webhooks, and use the Python library.

### Inference

The breadth of modes suggests the product is trying to serve both self-service end users and technical integrators. Today, the implementation is much stronger for developers than for nontechnical users. This creates a positioning problem: the product advertises workflow outcomes, but often delivers low-level API operations.

## Main workflows and usage scenarios

### A. Single meeting workflow

**Observed flow:** upload audio to `/api/v1/meetings` → transcribe → extract structured content → apply general, healthcare, or legal processing → return response.

**Inferred user goal:** get trustworthy, editable notes with minimal setup and then distribute or act on them.

**Gap:** the user cannot complete an integrated review, correction, approval, save, share, or export journey in one coherent interface.

### B. HIPAA transcription workflow

**Observed flow:** upload to `/api/v1/transcribe` → optionally set `phi_redaction=true` → receive redacted transcript and match count → write an audit entry.

**Inferred user goal:** safely create a healthcare note without accidentally exposing PHI.

**Gap:** healthcare note generation and PHI-safe transcription are separate routes. The primary `/meetings` path does not automatically redact PHI. A user can choose healthcare mode and still return or process unredacted content.

### C. Batch workflow

**Observed flow:** submit up to ten files → process sequentially → poll batch status → inspect partial failures → export results.

**Inferred user goal:** upload a set of recordings and return later when they are ready.

**Gap:** polling is technical, progress visibility is limited, processing is sequential, retry behavior is unclear, and there is no evidence of a user-facing queue, notification center, or per-file recovery action.

### D. Team and sharing workflow

**Observed flow:** create team → add existing user by email → assign role → process meetings → create public share links → select expiry → revoke if needed.

**Inferred user goal:** collaborate safely without manually distributing files.

**Gap:** invitation state, pending users, ownership transfer, link audience, passcodes, download permissions, and access analytics are absent or unclear. Public links can expose sensitive summaries if users choose unsafe defaults.

### E. Compliance administration workflow

**Observed flow:** review a Chart.js dashboard → query/export audit logs → generate BAAs → rotate encryption keys.

**Inferred user goal:** understand risk quickly, investigate incidents, and produce evidence for audits.

**Gap:** dashboard metrics are partly reserved, process-local, or static; score semantics are weak; audit queries historically focus on the active file; the HTML shell is public while its data requests require a manually loaded token; key rotation exposes a highly sensitive secret in a request body.

### F. Integration workflow

**Observed flow:** create webhook → save one-time secret → receive HMAC-signed batch completion callbacks → retry failed delivery three times.

**Inferred user goal:** trigger downstream automations reliably.

**Gap:** no test delivery, delivery log, replay, disable policy, endpoint verification, or UI guidance is evident.

---

# 2. UI/UX analysis

## Strengths

1. **Clear domain modes.** General, healthcare, and legal modes map to recognizable user jobs.
2. **Useful output structure.** Action items, decisions, key points, SOAP sections, testimony, and objections are more actionable than raw transcripts.
3. **Partial-failure tolerance in batches.** One failed file does not necessarily fail the whole job.
4. **Multiple export formats.** JSON, Markdown, PDF, and ZIP support different downstream habits.
5. **Role concepts are understandable.** Admin, member, and viewer are familiar mental models.
6. **Share expiration and revocation exist.** Users have more control than with permanent links only.
7. **Compliance components are modular.** Redaction, audit, encryption, BAAs, and dashboard functions can evolve independently.
8. **Extensive tests and examples lower integration friction.** The repository is unusually well documented at the library and endpoint level.

## Weaknesses

1. **No cohesive product shell.** Except for the compliance dashboard, most interactions require direct API use.
2. **The same user job is split across endpoints.** `/meetings` provides structured notes while `/transcribe` provides optional PHI redaction.
3. **No review and correction stage.** AI output appears to move directly from processing to response, with no visible confidence, source citation, approval state, or edit history.
4. **No meeting library experience.** There is no observed home screen, searchable meeting list, filters, recent work, favorites, or status overview.
5. **Poor progress feedback.** Long-running audio and batch operations need queued, uploading, transcribing, extracting, redacting, reviewing, completed, and failed states.
6. **Technical error language.** HTTP status codes and generic failures such as “Transcription failed” do not help users recover.
7. **Compliance dashboard can mislead.** Static `healthy` values, reserved zero fields, process-local counters, and an overly generous score undermine trust.
8. **Sensitive actions lack safe UX.** Key rotation and BAA generation need warnings, authorization, approval, and audit context.
9. **Documentation drift.** Versions, test counts, persistence descriptions, and implemented paths vary across documents.
10. **Accessibility and responsive behavior are not evidenced.** The minimal dashboard template does not demonstrate a design system, keyboard support, screen-reader semantics, or mobile behavior.

## Confusing elements

1. **“Healthcare mode” versus “HIPAA transcription.”** Users will reasonably assume healthcare mode includes safe PHI handling, but it does not automatically do so.
2. **HIPAA markers versus PHI redaction.** Marking a field as risky is not the same as detecting or removing PHI.
3. **“De-identified” based on absent patient ID.** A transcript can contain names, dates, addresses, or identifiers even when `patient_id` is omitted.
4. **Compliance score.** A nearly empty system can score relatively highly, and one BAA plus one audit entry can apparently produce 1.0.
5. **Dashboard token flow.** An unauthenticated HTML page that asks the user to load a bearer token is not a normal or safe sign-in experience.
6. **Configuration behavior.** `HIPAAConfig.load()` is described as configuration loading, but environment overrides are not implemented.
7. **Persistence statements.** Some documentation says key and BAA stores are in memory; later changelog notes mention file persistence. This needs one authoritative statement and automated verification.
8. **Export implementation.** Documentation references both WeasyPrint and fpdf2, while the application export service appears to use WeasyPrint in a potentially incorrect manner.

## Friction points

1. Re-entering mode-specific metadata with every upload.
2. Manually choosing PHI redaction rather than applying a workspace policy.
3. Polling batch endpoints instead of receiving in-product updates.
4. Copying bearer tokens into a dashboard.
5. Using API calls to invite users, manage sharing, inspect audit logs, and generate BAAs.
6. Re-uploading a whole file after a recoverable processing failure.
7. Receiving generic errors without diagnostics or next steps.
8. Exporting before reviewing accuracy or redaction quality.
9. Manually correlating audit entries, meetings, users, and incidents.
10. Manual rotation and fragmented audit history.

## Navigation and workflow observations

### Inference: recommended information architecture

A user-facing product should organize around user jobs rather than routers:

- **Home:** recent meetings, pending reviews, failed jobs, assigned actions.
- **Meetings:** library, search, filters, single meeting review.
- **New meeting:** upload or record, mode, language, privacy policy, metadata.
- **Batches:** queue, progress, per-file retry, exports.
- **Team:** members, roles, invitations, workspace settings.
- **Sharing:** active links, expiry, recipients, access history.
- **Compliance:** posture, issues, PHI events, audit explorer, BAAs, retention.
- **Integrations:** webhooks, API keys, delivery history.
- **Settings:** defaults, templates, terminology, data region, security.

The current endpoint-centric structure should remain available for developers, but it should not dictate the end-user navigation.

---

# 3. User behavior analysis

## Likely user habits

1. **Repeated use of the same mode.** A clinic, law office, or team will usually select the same mode and defaults repeatedly.
2. **Uploading soon after a meeting.** Users expect drag-and-drop, recent files, and remembered language/settings.
3. **Scanning before reading deeply.** Users first inspect the summary, action items, decisions, and warnings, then open the transcript for validation.
4. **Correcting names and assignments.** Speech recognition and LLM extraction commonly require edits to participant names, owners, deadlines, and terminology.
5. **Sharing immediately after review.** Users often copy a link, export, or send to a team within minutes of completing review.
6. **Returning to unfinished work.** Long recordings and batches create interruption and return behavior.
7. **Using search rather than folders alone.** Frequent users will search by participant, date, keyword, patient/case reference, action owner, or status.
8. **Handling exceptions, not only happy paths.** Compliance staff focus on failed redactions, denied access, anomalous downloads, expired BAAs, and delivery failures.

## Repeated actions that should be optimized

- Selecting mode, language, team, privacy level, and export format.
- Entering healthcare consent or legal case metadata.
- Reviewing action items and assigning owners.
- Correcting recurring names and vocabulary.
- Sharing with the same people or team.
- Applying the same retention and redaction policy.
- Filtering audit logs by date, actor, meeting, or risk.
- Retrying failed files.

## Likely pain points

1. **Trust:** users cannot see which transcript passages support generated notes.
2. **Control:** users cannot visibly edit and approve content before distribution.
3. **Safety:** healthcare users may assume PHI is protected when it is not automatically redacted.
4. **Waiting:** no clear processing timeline, notification, or background-job resume behavior.
5. **Recovery:** generic failures do not say whether to retry, change format, reduce size, or contact an administrator.
6. **Context switching:** endpoints, curl commands, and tokens require technical skills unrelated to the meeting task.
7. **Compliance interpretation:** numeric scores without evidence can create false assurance.
8. **Operational overhead:** administrators must manually rotate logs, inspect deliveries, and reconcile persistence.

## Usage bottlenecks

- Large audio uploads and sequential batch processing.
- Multiple LLM passes in healthcare mode, including duplicated extraction.
- Missing asynchronous job abstraction for the primary workflow.
- Process-local counters and singleton state that do not scale across workers.
- File-backed audit and agreement stores that complicate multi-instance deployment.
- No searchable, durable canonical record tying source audio, transcript, structured output, edits, shares, and audit events together.

## Expected but missing interactions

1. Drag-and-drop upload with validation before transfer.
2. Background upload and processing with resumable status.
3. Review screen with audio playback synchronized to transcript timestamps.
4. Inline editing with undo, autosave, and version history.
5. Approve/reject controls for extracted items and PHI findings.
6. Confidence and source evidence for generated content.
7. One-click retry for a failed stage, not the whole workflow.
8. Search, filters, saved views, and bulk actions.
9. Safe share dialog with expiry, permissions, warning, and preview.
10. In-app notifications and optional email/webhook completion notices.
11. Compliance issue drill-down and remediation tasks.
12. Vocabulary and templates learned at workspace level.

---

# 4. What should be improved

## Critical improvements

1. **Unify meeting processing and PHI-safe processing.** One workflow must handle transcription, structured notes, healthcare/legal processing, redaction policy, audit, persistence, and exports.
2. **Make PHI protection policy-driven and safe by default.** Healthcare workspaces should not depend on a user remembering a boolean field.
3. **Implement durable, tenant-aware storage.** Keys, BAAs, meetings, edits, audit indexes, and settings must survive restarts and multi-worker deployment.
4. **Fix authentication and authorization foundations.** Remove the hardcoded JWT secret, use strong password policy and modern hashing configuration, add tenant and role checks to sensitive routes, and apply least privilege.
5. **Replace misleading compliance metrics.** Every metric and score must come from traceable evidence, with freshness, coverage, and known limitations.
6. **Create a review-before-share workflow.** AI-generated and redacted content must be editable and explicitly approved.
7. **Establish a canonical meeting record and state machine.** Track upload, processing stages, versions, errors, approvals, and distribution.
8. **Resolve repository truth.** Make code, OpenAPI, README, changelog, examples, version, deployment files, and tests agree.
9. **Close known regression failures.** A release should not normalize dozens of pre-existing failures.
10. **Harden sensitive operations.** Key rotation, BAA lifecycle, public sharing, audit export, and PHI access require explicit permissions, step-up authentication, confirmation, and complete auditing.

## Medium-priority improvements

1. User-facing meeting library and review experience.
2. Batch queue with notifications and per-file retry.
3. Search and filters across meetings, actions, audit events, and BAAs.
4. Real invitation lifecycle and ownership management.
5. Webhook test, delivery log, replay, and automatic suspension.
6. Workspace defaults for mode, language, vocabulary, retention, and exports.
7. Source-linked extraction with timestamps and confidence.
8. BAA status lifecycle, expiry reminders, and countersignature support.
9. Audit archive indexing and scheduled retention enforcement.
10. Internationalization, timezone handling, accessibility, and responsive design.

## Nice-to-have improvements

1. Live or direct recording.
2. Calendar and conferencing integrations.
3. Personal shortcuts and saved views.
4. Branded exports and reusable note templates.
5. Action synchronization with task systems.
6. Offline draft capture where appropriate.
7. Mobile-friendly review and approval.

---

# 5. Requirements

## Prioritization method

- **Must have:** required for a coherent, safe, production-ready next version.
- **Should have:** high-value improvement that materially reduces repeated friction.
- **Could have:** differentiated value after core workflows are reliable.
- **Won’t have for now:** explicitly deferred to avoid overexpansion.

## Business requirements

### BR-01: Unified product workflow
- **Type:** Business
- **Description:** The product shall offer one coherent workflow from audio intake through processing, review, approval, storage, sharing, and export across general, healthcare, and legal modes.
- **User value:** Users complete their job without knowing which backend route performs each stage.
- **Priority:** Must have
- **Rationale:** The current split between `/meetings` and `/transcribe` creates confusion and safety risk.
- **Acceptance criteria:**
  - A user can start all supported modes from one entry point.
  - Mode-specific options appear only when relevant.
  - The workflow records one canonical meeting ID across all stages.
  - API compatibility is retained through a documented versioning or migration plan.

### BR-02: Defensible healthcare safety posture
- **Type:** Business
- **Description:** Healthcare mode shall enforce workspace-approved privacy, consent, retention, redaction, and audit policies by default.
- **User value:** Healthcare organizations can use the product without relying on individual memory for safety controls.
- **Priority:** Must have
- **Rationale:** Optional redaction on a separate route is incompatible with repeated real-world healthcare use.
- **Acceptance criteria:**
  - Healthcare workspaces cannot process content until required policy settings exist.
  - Every healthcare processing event records consent state, applied policy version, actor, outcome, and PHI handling result.
  - Unsafe overrides require permission, reason, and audit entry.

### BR-03: Trustworthy compliance evidence
- **Type:** Business
- **Description:** Compliance views shall display only metrics derived from durable, queryable evidence and shall label scope, freshness, and limitations.
- **User value:** Compliance staff can rely on the product during reviews and audits.
- **Priority:** Must have
- **Rationale:** Static health labels and simplistic scoring can mislead users.
- **Acceptance criteria:**
  - No production metric is hardcoded or based on process-local counters.
  - Each score component links to underlying evidence.
  - Stale, unavailable, or incomplete evidence produces an explicit unknown or degraded state, not a healthy state.

### BR-04: Multi-tenant production readiness
- **Type:** Business
- **Description:** All user, meeting, key, BAA, audit, policy, and integration data shall be isolated and durable per tenant.
- **User value:** Organizations can use the service reliably at scale without cross-tenant leakage or restart loss.
- **Priority:** Must have
- **Rationale:** In-memory and local-file state is unsafe for a horizontally scaled SaaS.
- **Acceptance criteria:**
  - Restart and multi-worker tests prove state continuity.
  - Tenant isolation tests cover all repository entities and routes.
  - Backup, restore, retention, and deletion procedures are documented and tested.

### BR-05: Product truth and release quality
- **Type:** Business
- **Description:** The release process shall prevent contradictions among code, OpenAPI, documentation, examples, version metadata, and automated tests.
- **User value:** Buyers, administrators, and developers understand what the product actually supports.
- **Priority:** Must have
- **Rationale:** Repository materials contain conflicting implementation and status statements.
- **Acceptance criteria:**
  - CI runs unit, integration, security, migration, documentation link, and OpenAPI contract tests.
  - The release has no accepted unexplained failing tests.
  - Documentation is generated or validated from authoritative contracts where feasible.

## User requirements

### UR-01: Fast repeat upload
- **Type:** User
- **Description:** As a frequent user, I want remembered workspace defaults and drag-and-drop upload so that I can start processing in seconds.
- **User value:** Reduces repetitive setup.
- **Priority:** Should have
- **Rationale:** Mode, language, team, redaction, and export choices repeat within a workspace.
- **Acceptance criteria:**
  - Defaults can be saved at workspace and personal levels.
  - The upload form validates type and size before processing.
  - Users can change defaults for one job without altering the workspace policy.

### UR-02: Review and approve output
- **Type:** User
- **Description:** As a note owner, I want to edit generated content and approve it before others can access it.
- **User value:** Increases accuracy and trust.
- **Priority:** Must have
- **Rationale:** AI output and PHI redaction both require human review in high-stakes use.
- **Acceptance criteria:**
  - A meeting enters `needs_review` after processing unless policy permits auto-approval.
  - Users can edit transcript, summary, structured sections, and redaction decisions.
  - Sharing and final export are blocked until approval when required by policy.
  - Changes are versioned with actor, time, and reason.

### UR-03: Understand and recover from failure
- **Type:** User
- **Description:** As a user, I want errors to explain what failed, what remains safe, and what I can do next.
- **User value:** Avoids repeated uploads and support tickets.
- **Priority:** Must have
- **Rationale:** Current generic HTTP errors do not support recovery.
- **Acceptance criteria:**
  - Errors identify the failed stage and preserve completed stages.
  - Recoverable failures include a retry action.
  - Validation failures explain supported formats, limits, and corrective action.
  - Correlation IDs are visible for support without exposing secrets or PHI.

### UR-04: Find prior work quickly
- **Type:** User
- **Description:** As a returning user, I want searchable, filterable meeting history so that I can find prior notes and unresolved actions.
- **User value:** Makes the product useful beyond the moment of upload.
- **Priority:** Should have
- **Rationale:** Repeated use creates a library, not isolated API responses.
- **Acceptance criteria:**
  - Search supports title, date, participant, keyword, mode, status, owner, patient/case reference where permitted.
  - Filters can be combined and bookmarked.
  - Search respects tenant, team, role, legal hold, and PHI permissions.

### UR-05: Safe sharing
- **Type:** User
- **Description:** As a meeting owner, I want to preview and control shared content so that I do not expose more than intended.
- **User value:** Reduces accidental disclosure.
- **Priority:** Must have
- **Rationale:** Public links are high-risk for healthcare and legal content.
- **Acceptance criteria:**
  - The share dialog shows exactly what recipients will see.
  - Healthcare and legal content defaults to authenticated, expiring, view-only access.
  - Users can restrict transcript, downloads, and specific sections.
  - All accesses and revocations are audited.

### UR-06: Action-oriented notes
- **Type:** User
- **Description:** As a team member, I want to confirm, assign, and track action items directly from the review screen.
- **User value:** Turns notes into completed work.
- **Priority:** Should have
- **Rationale:** Action items are a core extracted object but are currently passive output.
- **Acceptance criteria:**
  - Users can edit description, assignee, due date, and status.
  - Unresolved assignees are highlighted.
  - Users can filter meetings by open actions assigned to them.

## Functional requirements

### FR-01: Canonical meeting state machine
- **Type:** Functional
- **Description:** The system shall represent meeting processing as a durable state machine.
- **User value:** Provides predictable progress and reliable recovery.
- **Priority:** Must have
- **Rationale:** Current synchronous and batch flows do not expose a unified lifecycle.
- **Acceptance criteria:**
  - Supported states include draft, uploading, queued, transcribing, extracting, redacting, needs_review, approved, failed, archived, and deleted.
  - Every transition is timestamped and audited.
  - Invalid transitions are rejected.
  - Retrying a stage is idempotent and does not duplicate records.

### FR-02: Single secure processing API
- **Type:** Functional
- **Description:** The system shall provide a versioned API that accepts source audio, mode, language, team, and policy context, then creates an asynchronous job.
- **User value:** Consistent integration and UI behavior.
- **Priority:** Must have
- **Rationale:** Eliminates endpoint-dependent safety behavior.
- **Acceptance criteria:**
  - The API returns a meeting/job ID immediately.
  - Legacy routes map to the same orchestration service or return documented deprecation headers.
  - Healthcare mode uses the tenant’s active PHI policy automatically.

### FR-03: End-to-end PHI handling
- **Type:** Functional
- **Description:** PHI detection and redaction shall apply consistently to transcript, segments, structured notes, exports, shares, logs, and downstream payloads according to policy.
- **User value:** Prevents leakage through secondary outputs.
- **Priority:** Must have
- **Rationale:** Redacting only returned transcript text is insufficient.
- **Acceptance criteria:**
  - The system uses one normalized redaction map to update dependent artifacts.
  - Audit details and error logs reject plaintext PHI.
  - Exports and webhooks apply audience-specific redaction policy.
  - Regression tests include PHI in every output channel.

### FR-04: Human redaction review
- **Type:** Functional
- **Description:** Authorized reviewers shall be able to confirm, reject, add, or restore PHI findings with a recorded reason.
- **User value:** Handles false positives and false negatives safely.
- **Priority:** Must have
- **Rationale:** Regex-only detection and the current LLM stub cannot provide adequate contextual accuracy.
- **Acceptance criteria:**
  - Each finding includes category, risk, source location, detector, confidence, and status.
  - Changes update all derived artifacts after explicit confirmation.
  - Original sensitive content is visible only to permitted reviewers and never embedded in URLs or client logs.

### FR-05: Context-aware PHI validation
- **Type:** Functional
- **Description:** The system shall implement a real, configurable contextual PHI validation stage with graceful fallback.
- **User value:** Improves detection while preserving availability.
- **Priority:** Should have
- **Rationale:** `LLMValidator` is currently a stub.
- **Acceptance criteria:**
  - The validator returns confirmed, rejected, and new findings with confidence.
  - Timeouts or provider errors fall back to deterministic detection and mark review required.
  - No unredacted PHI is sent to a provider unless contract and workspace policy allow it.

### FR-06: Durable audit explorer
- **Type:** Functional
- **Description:** Authorized users shall be able to query all active and archived audit events with filters, pagination, export, and integrity status.
- **User value:** Supports investigation and evidence collection.
- **Priority:** Must have
- **Rationale:** Active-file-only reads and manual archive handling do not match real audit behavior.
- **Acceptance criteria:**
  - Filters include date, actor, action, resource, outcome, IP/device, risk, and tenant.
  - Results span rotated archives.
  - Hash-chain verification status and broken-chain alerts are visible.
  - Exports are themselves audited and access-controlled.

### FR-07: Accurate compliance posture
- **Type:** Functional
- **Description:** The dashboard shall compute posture from versioned controls and evidence rather than a simplistic synthetic score.
- **User value:** Highlights specific work instead of providing false reassurance.
- **Priority:** Must have
- **Rationale:** Current placeholders and static health values are not decision-grade.
- **Acceptance criteria:**
  - Controls show pass, fail, warning, unknown, and not applicable.
  - Every result includes last checked time and evidence link.
  - Overall posture cannot be “healthy” when critical evidence is unavailable.
  - Users can create or assign remediation tasks from failed controls.

### FR-08: Batch queue and per-file recovery
- **Type:** Functional
- **Description:** Batch processing shall run as durable background jobs with per-file progress, cancellation, and retry.
- **User value:** Reduces waiting and avoids reprocessing successful files.
- **Priority:** Should have
- **Rationale:** Sequential processing and polling create poor high-volume UX.
- **Acceptance criteria:**
  - Each file displays stage, percentage or qualitative progress, elapsed time, and failure reason.
  - Users can retry only failed files or failed stages.
  - Completion triggers in-app notification and configured external notifications.

### FR-09: Invitation and team lifecycle
- **Type:** Functional
- **Description:** Team membership shall support invitations, acceptance, expiry, resend, cancellation, role change, removal, and ownership transfer.
- **User value:** Makes team administration understandable and safe.
- **Priority:** Should have
- **Rationale:** Adding only existing users by email is not a complete invitation flow.
- **Acceptance criteria:**
  - Pending invitations are distinct from active members.
  - The last admin cannot remove or demote themselves without transferring responsibility.
  - All role and membership changes are audited.

### FR-10: Webhook operations
- **Type:** Functional
- **Description:** Administrators shall be able to test, inspect, replay, rotate secrets for, pause, and delete webhooks.
- **User value:** Makes integrations supportable.
- **Priority:** Should have
- **Rationale:** Registration and blind retries are insufficient for production integrations.
- **Acceptance criteria:**
  - Each delivery shows status, attempt count, latency, response code, and redacted error.
  - A test event can be sent before activation.
  - Failed events can be replayed idempotently.
  - Repeated failures cause a visible warning and configurable pause.

### FR-11: BAA lifecycle management
- **Type:** Functional
- **Description:** The system shall support draft, review, signature, active, expiring, expired, terminated, and superseded BAA states.
- **User value:** Reflects actual agreement management.
- **Priority:** Should have
- **Rationale:** Immutable generation alone does not cover the lifecycle.
- **Acceptance criteria:**
  - Signed content is immutable and versioned.
  - Expiry reminders are configurable.
  - Countersignature evidence and signer identity are stored.
  - Legal disclaimer requires organizational review of templates.

### FR-12: Sharing access controls
- **Type:** Functional
- **Description:** Sharing shall support authenticated recipients, passcodes, expiry, view/download permissions, revocation, and access history.
- **User value:** Matches differing sensitivity levels.
- **Priority:** Must have
- **Rationale:** A public token alone is too coarse for sensitive meetings.
- **Acceptance criteria:**
  - Tenant policy can prohibit public anonymous links.
  - Link contents and permissions are previewed before creation.
  - Revocation invalidates access immediately across all instances.
  - Brute-force and enumeration protections are tested.

### FR-13: Versioned editing and approval
- **Type:** Functional
- **Description:** The system shall store revisions to transcripts and notes, distinguish AI output from human edits, and record approvals.
- **User value:** Supports trust, accountability, and correction.
- **Priority:** Must have
- **Rationale:** High-stakes outputs need provenance.
- **Acceptance criteria:**
  - Users can compare revisions and restore a prior approved version.
  - Exports include approved version and generation time.
  - Editing permissions are role-based.

### FR-14: Notification center
- **Type:** Functional
- **Description:** The product shall notify users about completed processing, failures, pending review, share access, expiring BAAs, and compliance issues.
- **User value:** Users do not need to poll or remember administrative tasks.
- **Priority:** Should have
- **Rationale:** Current asynchronous behavior depends on API polling or webhooks.
- **Acceptance criteria:**
  - Notifications are available in-product with read/unread state.
  - Users can configure email and webhook preferences by event type.
  - Notifications contain no PHI unless explicitly permitted.

## Non-functional requirements

### NFR-01: Security and secret management
- **Type:** Non-functional
- **Description:** Secrets shall come from an approved secret manager or environment injection and never be hardcoded, logged, or returned.
- **User value:** Protects accounts and sensitive data.
- **Priority:** Must have
- **Rationale:** The JWT key is hardcoded in source, and key rotation accepts a secret in the request body.
- **Acceptance criteria:**
  - Startup fails in production when required secrets are default, missing, or weak.
  - Secret scanning runs in CI.
  - Key rotation uses a secret reference or managed KMS operation, not a plaintext web form.
  - Logs and traces are tested for secret leakage.

### NFR-02: Authorization and tenant isolation
- **Type:** Non-functional
- **Description:** Every protected resource shall enforce tenant and role authorization server-side.
- **User value:** Prevents unauthorized access.
- **Priority:** Must have
- **Rationale:** Authentication alone does not guarantee access to audit, BAA, encryption, or sharing data.
- **Acceptance criteria:**
  - Negative authorization tests cover cross-tenant and cross-role access for every endpoint.
  - Sensitive administrative actions require admin or compliance roles.
  - Public resources contain only explicitly approved fields.

### NFR-03: Availability and recoverability
- **Type:** Non-functional
- **Description:** Processing and durable state shall survive process restarts and partial dependency outages.
- **User value:** Prevents work loss.
- **Priority:** Must have
- **Rationale:** In-memory services and process-local singletons are fragile.
- **Acceptance criteria:**
  - Jobs resume or fail safely after worker restart.
  - Database and object-store backups have tested restoration objectives.
  - OpenAI or webhook outages do not corrupt meeting state.

### NFR-04: Performance
- **Type:** Non-functional
- **Description:** User interactions and background stages shall meet explicit service targets.
- **User value:** Predictable speed.
- **Priority:** Should have
- **Rationale:** A scanner budget exists, but full workflow performance targets are not defined.
- **Acceptance criteria:**
  - UI API reads achieve p95 under 500 ms under agreed load, excluding exports and AI processing.
  - Upload progress begins within 1 second.
  - Job state updates are visible within 5 seconds.
  - PHI scanning uses bounded execution and rejects pathological patterns safely.

### NFR-05: Observability
- **Type:** Non-functional
- **Description:** The system shall provide structured logs, metrics, traces, and alerting without leaking PHI.
- **User value:** Faster incident resolution and more reliable service.
- **Priority:** Must have
- **Rationale:** Generic errors and fragmented stores impede support.
- **Acceptance criteria:**
  - Every request and job has a correlation ID.
  - Metrics cover stage latency, failure rate, queue depth, redaction review rate, webhook delivery, and audit integrity.
  - PHI-safe logging tests are part of CI.

### NFR-06: Accessibility
- **Type:** Non-functional
- **Description:** The user-facing application shall meet WCAG 2.2 AA.
- **User value:** Inclusive and legally safer use.
- **Priority:** Must have
- **Rationale:** No accessibility evidence exists in the current minimal UI.
- **Acceptance criteria:**
  - All workflows are keyboard operable.
  - Status is not conveyed by color alone.
  - Charts have textual equivalents.
  - Automated and manual accessibility testing passes before release.

### NFR-07: Privacy and data lifecycle
- **Type:** Non-functional
- **Description:** Retention, deletion, legal hold, export, and residency policies shall be configurable and enforceable by tenant and data class.
- **User value:** Supports organizational privacy obligations.
- **Priority:** Must have
- **Rationale:** Six-year audit retention alone is not a complete lifecycle policy.
- **Acceptance criteria:**
  - Retention jobs produce auditable results.
  - Legal hold prevents deletion.
  - User-visible deletion states distinguish pending, completed, and blocked.
  - Audio, transcript, notes, shares, exports, and backups are included.

### NFR-08: Release quality
- **Type:** Non-functional
- **Description:** The release shall pass all supported automated tests with explicit quarantine and owner rules for any temporary exception.
- **User value:** Fewer regressions and more credible documentation.
- **Priority:** Must have
- **Rationale:** The repository normalizes substantial pre-existing failures.
- **Acceptance criteria:**
  - CI reports zero unexplained failures.
  - Contract, migration, concurrency, security, accessibility, and disaster-recovery tests are included.
  - Test counts in documentation are generated automatically.

## UX/UI requirements

### UX-01: Guided new-meeting flow
- **Type:** UX/UI
- **Description:** Provide a stepwise but lightweight flow for source, context, privacy, metadata, and processing.
- **User value:** Makes advanced settings understandable without slowing frequent users.
- **Priority:** Must have
- **Rationale:** Current parameters are endpoint fields with little guidance.
- **Acceptance criteria:**
  - The form progressively discloses healthcare and legal fields.
  - Saved defaults reduce repeat actions.
  - Before starting, users see estimated privacy policy, storage destination, and sharing state.

### UX-02: Transparent processing status
- **Type:** UX/UI
- **Description:** Show upload and processing stages, elapsed time, and actionable failure state.
- **User value:** Reduces uncertainty during long operations.
- **Priority:** Must have
- **Rationale:** Audio and batch processing are asynchronous user journeys.
- **Acceptance criteria:**
  - Status survives refresh and sign-in on another device.
  - Users can leave the screen without cancelling work.
  - Failed stages show retry and support details.

### UX-03: Source-linked review workspace
- **Type:** UX/UI
- **Description:** Provide a review screen combining audio player, timestamped transcript, structured notes, PHI findings, and version controls.
- **User value:** Enables fast verification and correction.
- **Priority:** Must have
- **Rationale:** Trust and approval are the largest missing user interactions.
- **Acceptance criteria:**
  - Selecting a generated item jumps to supporting transcript and audio.
  - Users can edit inline and undo changes.
  - PHI findings are visually distinct and accessible.
  - Approval state and reviewer identity are prominent.

### UX-04: Safe share dialog
- **Type:** UX/UI
- **Description:** Sharing shall use plain-language audience, expiry, content, and permission controls.
- **User value:** Prevents accidental disclosure.
- **Priority:** Must have
- **Rationale:** Current share links expose too much decision burden through a single expiration field.
- **Acceptance criteria:**
  - High-sensitivity meetings show a warning and safe defaults.
  - Recipient preview is available.
  - Copy-link occurs only after successful creation.
  - Active shares can be reviewed and revoked from one screen.

### UX-05: Actionable compliance dashboard
- **Type:** UX/UI
- **Description:** Replace an abstract score-first dashboard with control status, evidence, trends, and remediation.
- **User value:** Helps administrators decide what to do next.
- **Priority:** Must have
- **Rationale:** Current metrics are not reliable enough for decision-making.
- **Acceptance criteria:**
  - Critical issues appear before aggregate charts.
  - Every card has definition, scope, last updated time, and drill-down.
  - Empty states explain setup steps rather than displaying misleading zeros.

### UX-06: Consistent design system and terminology
- **Type:** UX/UI
- **Description:** Use one visual and language system for statuses, risks, roles, errors, and actions.
- **User value:** Reduces cognitive load.
- **Priority:** Should have
- **Rationale:** Endpoint and document terminology is inconsistent.
- **Acceptance criteria:**
  - Content guidelines define “healthcare mode,” “PHI,” “redacted,” “de-identified,” “approved,” and “compliance posture.”
  - The same status names appear in UI, API, docs, and notifications.

## Data and integration requirements

### DIR-01: Canonical data model
- **Type:** Data/Integration
- **Description:** Use durable entities for tenant, workspace, meeting, source asset, transcript segment, note version, action item, PHI finding, policy version, approval, share, audit event, BAA, encryption key metadata, and job stage.
- **User value:** Enables consistent behavior, search, history, and compliance evidence.
- **Priority:** Must have
- **Rationale:** Current models and file stores do not form one complete product record.
- **Acceptance criteria:**
  - Entity relationships and ownership are documented.
  - Migrations are reversible or have tested forward-recovery plans.
  - All derived artifacts reference source version and policy version.

### DIR-02: Object storage for binary assets
- **Type:** Data/Integration
- **Description:** Audio and generated files shall be stored in encrypted tenant-scoped object storage with time-limited access.
- **User value:** Reliable, scalable file handling.
- **Priority:** Must have
- **Rationale:** Local filesystem storage is unsuitable for multi-instance SaaS.
- **Acceptance criteria:**
  - URLs are short-lived and scoped.
  - Storage lifecycle follows retention and legal-hold rules.
  - Malware and format validation occur before processing.

### DIR-03: Managed key service
- **Type:** Data/Integration
- **Description:** Production encryption shall integrate with a managed KMS or equivalent HSM-backed service.
- **User value:** Safer key custody and rotation.
- **Priority:** Must have
- **Rationale:** Environment-derived KEKs and request-body rotation are operationally risky.
- **Acceptance criteria:**
  - Plaintext master keys never enter application requests or persistent storage.
  - Rotation has dry-run, authorization, audit, rollback, and recovery procedures.
  - Per-tenant key separation is verifiable.

### DIR-04: Versioned external API and webhooks
- **Type:** Data/Integration
- **Description:** External API and webhook contracts shall be versioned, documented, idempotent where applicable, and covered by contract tests.
- **User value:** Stable integrations.
- **Priority:** Should have
- **Rationale:** The repository already contains canonical-path changes and historical endpoint drift.
- **Acceptance criteria:**
  - Deprecation policy and sunset headers are defined.
  - Webhook payloads include event ID, version, tenant ID, resource ID, and occurred time.
  - Consumers can replay or deduplicate events.

### DIR-05: Workspace terminology and vocabulary
- **Type:** Data/Integration
- **Description:** Workspaces shall maintain approved names, acronyms, clinical/legal terminology, and speaker mappings used during transcription and review.
- **User value:** Reduces recurring correction work.
- **Priority:** Could have
- **Rationale:** Frequent users repeatedly correct the same vocabulary.
- **Acceptance criteria:**
  - Entries are versioned and permission-controlled.
  - Users can accept a recurring correction into the workspace vocabulary.
  - Sensitive vocabulary follows tenant privacy rules.

## Won’t have for now

### WH-01: Autonomous clinical or legal decision-making
- **Type:** Scope exclusion
- **Description:** The next version will not diagnose, recommend treatment, provide legal advice, or make final compliance determinations.
- **User value:** Keeps the product focused on documentation and human-reviewed assistance.
- **Priority:** Won’t have for now
- **Rationale:** These capabilities would substantially increase safety, regulatory, and liability risk.
- **Acceptance criteria:**
  - Product copy clearly states the assistive role.
  - Human review remains required for high-stakes outputs.

### WH-02: Broad marketplace of integrations
- **Type:** Scope exclusion
- **Description:** The next version will not launch a large integration marketplace before core meeting review, safety, persistence, and authorization are reliable.
- **User value:** Prevents product sprawl and unstable integrations.
- **Priority:** Won’t have for now
- **Rationale:** Core workflow fragmentation is a higher-impact problem.
- **Acceptance criteria:**
  - Only a small set of validated integrations is considered after core release gates pass.

---

# 6. New opportunities

## 1. Evidence-linked notes

**Opportunity:** Link each summary sentence, action, decision, SOAP element, testimony point, or objection to timestamped transcript and audio evidence.

**Why users may want it:** Users need to validate AI output quickly, especially in healthcare and legal contexts.

**Evidence and reasoning:** The product already stores transcript segments and structured outputs, but it does not connect them. This is a direct response to the missing review workflow and trust gap.

## 2. Workspace vocabulary and recurring correction memory

**Opportunity:** Let authorized users promote corrected names, terms, abbreviations, and speaker labels into a workspace dictionary.

**Why users may want it:** Teams repeatedly discuss the same products, people, medications, procedures, and case terminology.

**Evidence and reasoning:** Repeated correction is a predictable behavior in transcription products, and the application already supports mode and tenant context.

## 3. Policy templates by workspace type

**Opportunity:** Provide configurable policy starters for general business, healthcare, and legal workspaces.

**Why users may want it:** Administrators need sensible defaults and cannot be expected to understand every low-level setting.

**Evidence and reasoning:** Current safety behavior depends on technical parameters and separate routes. Templates can reduce setup friction without claiming automatic compliance.

## 4. Review queues for specialists

**Opportunity:** Create queues such as “needs note approval,” “PHI review required,” “failed transcription,” and “expiring agreement.”

**Why users may want it:** In real organizations, uploaders, reviewers, and compliance staff are often different people.

**Evidence and reasoning:** The app already has team roles and compliance components but lacks operational handoffs.

## 5. Action-item synchronization

**Opportunity:** Send approved tasks to a limited set of task-management systems.

**Why users may want it:** Extracted action items have little value if they remain static text.

**Evidence and reasoning:** Action items are a central output in general mode. This opportunity follows the workflow rather than adding an unrelated feature.

## 6. Safe sharing profiles

**Opportunity:** Reusable sharing profiles such as “internal team,” “external client,” “redacted public summary,” and “legal restricted.”

**Why users may want it:** Sharing settings repeat and sensitivity varies by audience.

**Evidence and reasoning:** The current product already has share links and redaction, but they are not integrated into audience-aware policies.

## 7. Compliance evidence packages

**Opportunity:** Generate a dated evidence package containing control status, policy versions, verified audit ranges, BAA status, key metadata, and exceptions.

**Why users may want it:** Compliance teams need evidence, not only dashboard charts.

**Evidence and reasoning:** Audit export, BAA, key metadata, and compliance metrics already exist separately. Packaging them is a logical workflow completion.

## 8. Calendar and conferencing intake

**Opportunity:** Import recordings and meeting metadata from a small number of high-demand conferencing/calendar platforms.

**Why users may want it:** Manual upload is repetitive for frequent users.

**Evidence and reasoning:** The core behavior is repeated post-meeting upload. Integration should be considered only after the secure review and storage foundation is complete.

---

# 7. Final recommendation

## What should be built first

### Phase 0: Product truth and safety foundation

1. Remove hardcoded secrets and implement managed secret/key operations.
2. Close or explicitly remove failing contract areas; make tests and documentation authoritative.
3. Implement tenant-aware durable storage and a canonical meeting/job model.
4. Apply authorization consistently to every sensitive resource.
5. Replace static compliance values with evidence-backed states.
6. Define and test retention, deletion, backup, restore, and audit integrity.

These are release blockers because a polished interface on top of unreliable safety and state would increase adoption risk rather than reduce it.

### Phase 1: Unified core workflow

1. One upload/processing API and guided UI.
2. Durable background jobs and transparent stage status.
3. Policy-driven healthcare redaction and audit behavior.
4. Source-linked review, editing, PHI decisions, and approval.
5. Meeting library with search, filters, and recovery actions.
6. Safe sharing and approved exports.

This phase will produce the largest improvement in real user effectiveness, clarity, speed, and trust.

### Phase 2: Operational workflows

1. Batch queue and per-file retry.
2. Notification center.
3. Team invitation lifecycle.
4. Webhook test, delivery history, and replay.
5. BAA lifecycle and reminders.
6. Action tracking and selected integrations.

## UI and workflow improvements to prioritize immediately

1. **Unify healthcare mode and PHI-safe transcription.** This is the highest-risk inconsistency.
2. **Add a review-before-share workspace.** This is the highest-value missing user interaction.
3. **Show durable progress and recovery.** This addresses daily waiting and failure friction.
4. **Create a meeting library.** This turns isolated processing into a repeat-use product.
5. **Redesign compliance around evidence and issues.** This improves administrator trust and avoids misleading signals.
6. **Replace token-paste dashboard access with normal authenticated navigation.** This removes technical friction and reduces bearer-token exposure.

## Requirements with the greatest adoption and efficiency impact

- **BR-01 / FR-02:** one coherent processing workflow.
- **UR-02 / UX-03 / FR-13:** review, source evidence, editing, and approval.
- **FR-03 / BR-02:** policy-driven end-to-end PHI handling.
- **FR-01 / UX-02:** durable jobs, visible progress, and stage-level retry.
- **UR-04:** searchable meeting history.
- **UR-05 / UX-04 / FR-12:** safe, audience-aware sharing.
- **FR-07 / UX-05:** truthful, actionable compliance posture.
- **NFR-01 / NFR-02 / BR-04:** secrets, authorization, tenant isolation, and durable storage.

## Closing assessment

MeetingNotesAI has a broad and promising backend foundation, particularly in structured note extraction, domain modes, export, teams, sharing, and HIPAA-oriented components. Its next constraint is not feature count. It is workflow coherence, trust, production safety, and user-facing operability.

The strongest next version will make the existing capabilities feel like one product: fast to start, transparent while processing, easy to review, safe to approve, controlled when shared, and honest about compliance evidence. That direction is better supported by the observed application than adding more isolated APIs or additional domain modes.
