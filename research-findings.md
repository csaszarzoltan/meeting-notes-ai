# Research Findings

## Executive Summary

MeetingNotesAI is now a broad v1.x meeting-intelligence platform rather than the earlier API demo. The repository contains a React/TypeScript workspace, FastAPI backend, live transcription, uploads and batches, Google Calendar import, Jira/Linear/Asana/Todoist adapters, sharing, encrypted storage, retention, audit logging, healthcare controls, local transcription, and extensive tests. This breadth changes the strategic problem: the next pass should not add another shallow center or integration. It should prove that the product is trustworthy, operationally coherent, and differentiated from both mature cloud suites and rapidly growing local-first alternatives.

Current 2026 comparisons describe transcription as table stakes and emphasize governance, automation, bot versus bot-free capture, cross-platform support, and workflow fit as differentiators. Pricing has standardized around free acquisition tiers, roughly $8 to $25 per user/month for individual productivity, and roughly $19 to $39 for team/business plans; native Microsoft/Zoom capabilities and generous free products increase price pressure. citeturn2search60turn2search63turn2search65turn2search67

The recommended positioning is **evidence-grounded, privacy-controllable meeting intelligence for professional and regulated teams**. The top development priorities are: (1) source-linked human review and quality measurement, (2) a production-grade bot-free local desktop capture path, and (3) unified governance and artifact lineage. These exploit existing backend investments while addressing consent risk, buyer discomfort with bots, accuracy distrust, and local-first competition. Privacy and consent vary by jurisdiction, while derivative summaries, integrations, and searchable archives enlarge the data surface beyond the original recording. citeturn2search71turn2search72turn2search75turn2search76

## Project Understanding

### Verified product behavior

- **Application shell and GUI:** React 18/TypeScript/Vite workspace with dashboard, meeting library, upload, setup, batch center, action center, integrations, compliance, sharing, settings, command palette, mobile navigation, lifecycle and processing components (`frontend/src/App.tsx`, `frontend/src/workspace/*`).
- **Capture and processing:** uploaded audio, live WebSocket sessions, diarization, OpenAI and local transcription paths, extraction, general/healthcare/legal modes (`routes/meetings.py`, `routes/live_transcription.py`, `services/transcription.py`, `services/local_transcription.py`, `services/diarization.py`).
- **Workflow:** Google Calendar, meeting lifecycle, workspace APIs, action integrations for Jira, Linear, Asana and Todoist (`routes/google_calendar.py`, `services/google_calendar.py`, `services/integrations/*`, `services/workflow.py`).
- **Trust infrastructure:** encrypted local/S3 storage, retention, sharing, API keys, rate limiting, middleware, HIPAA-oriented PHI redaction, BAA templates, audit logger and compliance dashboard (`storage/*`, `routes/storage.py`, `routes/sharing.py`, `hipaa/*`).
- **Stack:** Python 3.11+, FastAPI, Pydantic, async SQLAlchemy/Alembic, JWT/API-key auth, React 18, TypeScript and Vite. Version identifiers are inconsistent: `pyproject.toml`, frontend package and package `__version__` say 1.2.0, README says 1.1.2, while CHANGELOG includes 1.3.0.
- **Maturity:** 212 files, 70 source files, 58 test files and 30 frontend source files. The current environment could not independently run pytest because SQLAlchemy is not installed, so repository test-result documents are historical evidence rather than a reproduced pass.

### Target users and jobs

The product is best aligned to consultants, product/research teams, operations teams, developers, and compliance-sensitive healthcare/legal organizations that need to capture meetings, retrieve evidence, approve outputs, route actions and control retention. The core job is: “Turn a consequential conversation into a verifiable record and completed follow-up without losing control of sensitive data.”

### Principal user flow

The implemented workspace supports dashboard → create/import/upload/live meeting → processing → review → share/action/integration → compliance/settings. The flow is substantially more complete than the prior report describes, so that earlier `research-findings.md` is replaced rather than extended.

## Current-State Gap Analysis

| Area | Verified strength | Remaining weakness | Planning constraint |
|---|---|---|---|
| Product surface | Broad workspace and API coverage | Feature breadth risks fragmented depth and placeholder behavior | Finish one end-to-end trust loop before adding modules |
| Accuracy | Transcription, diarization and extraction services | No visible benchmark corpus, WER/DER, extraction precision, source citations or confidence calibration | Model outputs must remain drafts until measurable review |
| Capture | Upload and live paths; local transcription service | No clearly packaged cross-platform desktop system-audio client | Do not promise universal bot-free capture from browser-only UX |
| Governance | Encryption, audit, retention, PHI and BAA modules | No single artifact-lineage/deletion proof across exports, shares and integrations | Every derivative needs ownership, policy version and lifecycle state |
| Compliance | Strong HIPAA-shaped functions | Technical controls alone do not establish legal compliance | Avoid blanket HIPAA/GDPR claims; require legal and operational validation |
| UX | Modern component inventory and responsive navigation | Accessibility, browser E2E, failure recovery and real-world task completion need proof | Target WCAG 2.2 AA and measurable workflow tests |
| Operations | Docker, Railway, Alembic and CI assets | Version drift, bundled `meeting_notes.db`, and unexecuted tests weaken release confidence | Reproduce clean install, migrations and full tests before release |
| Distribution | Integrations and self-serve workspace | No verified billing, activation telemetry, customer proof or support loop | Validate paid pilot before complex pricing implementation |

## Target Users and Jobs to Be Done

1. **Professional-services teams:** produce client-ready, source-verifiable notes and follow-up without introducing an awkward bot.
2. **Product and research teams:** search interviews, correct speakers, cite evidence and move findings into action systems.
3. **Healthcare/legal/compliance teams:** enforce consent, provider, retention, approval and deletion policy across all derivatives.
4. **IT/security teams:** deploy approved capture modes, audit events, restrict providers and prove data boundaries.
5. **Developers/operations teams:** automate batches and actions with idempotent APIs, reliable webhooks and observable failures.

## Target-Market Pain Points

| User problem | Segment | Recurrence | Evidence | Confidence | Implication |
|---|---|---|---|---|---|
| Visible bots cause discomfort and alter meeting behavior | Client-facing and sensitive teams | Repeated across 2026 comparisons and consent commentary | Bot-free/local products are repeatedly positioned around this problem. citeturn2search60turn2search63turn2search74turn2search75 | HIGH | Ship a consent-explicit local capture option |
| Accuracy, speakers and summaries still require verification | Knowledge workers and regulated users | Buying criteria across independent comparisons | Reviews evaluate transcription, speaker ID, action extraction and privacy, indicating these remain differentiators rather than solved commodities. citeturn2search62turn2search64turn2search69 | MEDIUM-HIGH | Evidence links, revisions and quality metrics are P0 |
| Actions do not reliably become completed work | Sales, PM and operations | Repeated in pricing/workflow comparisons | Current comparisons emphasize CRM field mapping, task automation and post-call follow-through. citeturn2search61turn2search65turn2search70 | HIGH | Improve idempotency, mapping and delivery observability rather than adding more adapters |
| Consent and privacy rules are hard across jurisdictions | Legal, HR, healthcare and remote teams | Multiple independent 2026 legal/privacy guides | Sources agree disclosure and jurisdiction-aware consent matter, though state counts differ, demonstrating legal complexity. citeturn2search71turn2search72turn2search75turn2search76 | HIGH | Policy must fail closed and avoid legal automation claims |
| Cloud processing and derivative copies create data-sovereignty concerns | Regulated and enterprise buyers | Strong open-source/local growth plus privacy analysis | Local-first repositories and comparisons are growing, while privacy guidance highlights copies in CRMs, search indexes and summaries. citeturn2search73turn2search76turn2search78turn2search80 | HIGH | Artifact lineage and local-only mode are differentiators |
| Per-seat subscriptions and hidden limits create price sensitivity | Individuals and small teams | Consistent pricing comparison theme | Free tiers are universal and annual individual pricing clusters around $8–$25, with team tiers around $19–$39. citeturn2search61turn2search66turn2search67turn2search69 | HIGH | Use free evaluation plus transparent workspace/usage packaging |

## Competitor Weaknesses

- **Otter:** strong live transcription and mobile familiarity, but free/import limits, bot-based workflow, and weaker privacy/local differentiation leave room for controlled professional workflows. citeturn2search66turn2search67turn2search69
- **Fireflies:** broad CRM automation and language coverage, but storage/AI-credit complexity and bot/privacy concerns can make procurement and total cost harder to understand. citeturn2search61turn2search67turn2search69
- **Fathom:** excellent free value and easy summaries, but advanced AI and team controls are tiered, and its capture model does not create a complete governance moat. citeturn2search63turn2search66turn2search69
- **tl;dv:** strong clips, CRM and multi-meeting insights, but sales orientation, higher advanced tiers and bot-centered capture create an opening for regulated, evidence-review workflows. citeturn2search64turn2search66turn2search67
- **Meetily/local open source:** compelling local processing, bot-free system audio and open-source economics; collaborative governance, shared workflows and enterprise polish are the exploitable gaps. citeturn2search63turn2search78turn2search80turn2search82

## Competitor Comparison

| Competitor | Audience/position | Current pricing signal | Core UX | Repeated strength | Opening for MeetingNotesAI |
|---|---|---|---|---|---|
| Otter | Transcript-first individuals and teams | Free; paid starts about $8.33 annual; Business about $19.99 annual | Bot/mobile/live transcript → summary/search | Real-time usability and brand | Evidence approval, local capture, cross-artifact governance |
| Fireflies | Sales and automation teams | Free; Pro about $10 annual; Business about $19 annual | Bot/extension → searchable memory → CRM workflows | Integrations and language breadth | Simpler pricing, consent-first capture, stronger lineage |
| Fathom | Individuals and teams wanting simple notes | Generous free; paid individual/team tiers | Capture → immediate notes/highlights → CRM | Free value and clean first use | Regulated governance and uploaded/batch evidence workflows |
| tl;dv | Sales, research and multi-meeting intelligence | Free plus Pro/Business | Capture → clips/templates → CRM/reporting | Cross-meeting insight | Professional-record approval and local/private modes |
| Meetily | Privacy-first local/offline users | Free community; Pro from roughly $10 annual in comparisons | Desktop system audio → local STT → local/Ollama summary | No bot, no cloud requirement, open source | Hosted team collaboration, audit and policy control |

Pricing is time-sensitive. The ranges above are triangulated from April–June 2026 comparisons that report checking official pages; official plan pages must be rechecked immediately before billing implementation. citeturn2search61turn2search63turn2search66turn2search67

## Validated Demand Signals

1. **The category is commercially validated but commoditized at basic transcription.** Current comparisons cover many mature products and describe governance, automation and capture model as differentiators. citeturn2search60turn2search62turn2search65
2. **Free acquisition is table stakes.** All five products in one April 2026 comparison offered free plans, while paid individual plans clustered below many enterprise productivity add-ons. citeturn2search61turn2search63turn2search67
3. **Local-first demand is material.** Meetily’s repository reports about 29,000 stars, and independent 2026 coverage focuses on local audio, Whisper/Parakeet and optional Ollama summarization. citeturn2search78turn2search80
4. **Governance is moving into the product core.** Enterprise-oriented comparisons emphasize audit, security, integrations and avoiding a meeting-data silo. citeturn2search65turn2search70turn2search76
5. **Action follow-through is a monetizable layer.** Pricing and sales-tool comparisons explicitly distinguish transcript products from tools that map fields, create tasks and automate follow-up. citeturn2search61turn2search67turn2search70

## Market and Pricing Evidence

No single market-size figure is used as a planning input because category definitions and sponsored forecasts vary widely. The more reliable evidence is observable vendor density, converging feature sets, persistent free tiers, enterprise packaging and active open-source adoption. Current comparisons place annual individual/pro products around $8–$25 per user/month and business products around $19–$39, with enterprise governance and compliance often priced higher or custom. citeturn2search61turn2search63turn2search67turn2search69

Recommended pricing hypothesis: free evaluation with limited cloud processing; a $15–$25/month professional workspace including a usage allowance; team pricing that avoids punishing occasional collaborators; and a premium governance/local-deployment tier. This is a hypothesis, not verified willingness-to-pay. Validate it through at least 10 buyer interviews and three paid design-partner pilots. Search-interest data could not be verified from a primary trends dataset in this phase, so no numeric search-interest claim is made.

## Modern UX Expectations

A current baseline is a coherent shell with dashboard, global search, meeting library, unified capture/import, live state, review, actions, integrations, sharing, compliance, workspace and billing. Meeting detail should synchronize audio, timestamped transcript, speaker identity, notes and evidence. Processing needs stage-level progress and retry; sharing needs recipient preview, expiration, download and redaction controls; integrations need mapping, idempotency and delivery history. Bot-free products also set an expectation for responsive desktop capture, clear audio-device health and local-processing status. citeturn2search60turn2search64turn2search65turn2search77turn2search78

The project now meets much of the screen/navigation baseline through `frontend/src/workspace/*`. Missing proof includes real browser E2E behavior, synchronized evidence for every claim, desktop system-audio packaging, complete empty/loading/error/disabled/success states, accessibility conformance, and lifecycle visibility across every derivative.

Measurable UX requirements: WCAG 2.2 AA automated and manual checks; full keyboard operation; visible focus; no color-only status; 44×44 CSS-pixel touch targets; screen-reader job-state announcements; modal focus trapping; mobile layouts at 320 CSS pixels; p95 interaction response under 200 ms for local UI actions; and no loss of user edits during retryable failures.

## Open-Source and Automation Opportunities

- Evaluate Whisper/Parakeet local STT and pyannote-style diarization behind existing provider interfaces, but record model license, hardware, language, WER, DER and latency for each supported profile. Meetily demonstrates active demand for this architecture. citeturn2search78turn2search80turn2search81
- Build a signed Tauri or similar desktop capture companion rather than attempting universal system-audio capture in a web page. MeetingBro and Meetily show cross-platform local capture patterns. citeturn2search77turn2search78
- Standardize transcript export on WebVTT/SRT plus stable JSON segment IDs, and use CloudEvents-like webhooks with idempotency keys.
- Extend existing PM adapters with replay-safe outbox delivery, mapping previews, dead-letter handling and reconciliation rather than adding more vendors.
- Create a quality-evaluation harness using consented/no-PHI fixtures covering accents, jargon, overlap, noise, speaker count and domain templates.

## Differentiation Opportunities

| Capability | Problem / target user | Evidence and competitor gap | Value | Complexity | Main risk | Priority | Success criterion |
|---|---|---|---|---|---|---|---|
| Evidence-grounded review | Professionals cannot trust opaque notes | Accuracy remains a buying criterion; current project lacks universal citations | Trustworthy records | HIGH | Incorrect evidence alignment | P0 | 100% of published claims have valid spans; pilot approval median <5 min |
| Speaker correction and quality queue | Misattribution breaks actions | Diarization remains difficult and local tools still evolve | Faster reliable review | HIGH | Accents/overlap variability | P0 | DER benchmark reported; <10% segments manually relabeled in pilot |
| Bot-free desktop capture | Clients dislike bots and platform lock-in | Local-first projects are growing | Cross-platform privacy wedge | HIGH | OS audio and signing complexity | P0 | p95 live latency <3 s on supported profiles; recovery passes 100 crash tests |
| Local-only processing policy | Sensitive audio cannot leave device | Local competitors lead this message | Premium privacy tier | HIGH | Hardware support and model quality | P1 | Automated egress test confirms zero AI endpoint calls in local-only mode |
| Artifact lineage and deletion receipts | Copies spread into shares, exports and PM tools | Privacy guidance highlights derivative risk | Governance and sales enablement | MEDIUM-HIGH | External systems may not support deletion | P0 | 100% internal derivatives mapped; deletion receipt produced for every test case |
| Tamper-evident audit export | Security teams need defensible evidence | Existing logger lacks complete buyer-facing proof | Enterprise readiness | MEDIUM | Key and chain management | P1 | Verification detects every injected mutation in test corpus |
| Transparent workspace-plus-usage pricing | Per-seat multiplication creates friction | Free/low-cost tools pressure generic SaaS | Easier adoption | LOW | Unit economics | P2 | Three paid pilots accept pricing with positive gross margin |

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
    "id": "US-004",
    "epic": "Bot-Free Local Capture",
    "role": "knowledge worker",
    "action": "record microphone and system audio without a meeting bot",
    "benefit": "client calls are captured across meeting platforms without adding a participant",
    "story": "As a knowledge worker, I want to record microphone and system audio without a meeting bot, so that client calls are captured across meeting platforms without adding a participant.",
    "gui_flow": [
      "User opens Capture → available input devices appear",
      "User selects microphone and system audio → level meters respond",
      "User clicks Start → consent reminder and recording indicator appear",
      "User joins any meeting platform → live transcript streams locally",
      "User clicks Stop → local recording finalizes",
      "User chooses Upload securely or Keep local → destination and deletion state appear"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "both audio sources are available",
        "when": "the user starts capture",
        "then": "audio frames from both sources are timestamped and transcript latency stays under 3 seconds at p95 on supported hardware"
      },
      {
        "type": "given",
        "text": "system audio is unavailable",
        "when": "the user starts capture",
        "then": "microphone-only mode is offered and the limitation is recorded"
      },
      {
        "type": "given",
        "text": "local transcription is running",
        "when": "it crashes",
        "then": "capture continues to an encrypted recovery file and restart offers recovery without duplicate segments"
      }
    ]
  },
  {
    "id": "US-005",
    "epic": "Bot-Free Local Capture",
    "role": "privacy-conscious user",
    "action": "process transcription and summarization locally",
    "benefit": "sensitive audio does not leave my device",
    "story": "As a privacy-conscious user, I want to process transcription and summarization locally, so that sensitive audio does not leave my device.",
    "gui_flow": [
      "User opens Capture privacy → processing choices appear",
      "User selects Local only → installed model and storage path show",
      "User runs readiness check → CPU, memory and disk results appear",
      "User starts recording → network-egress indicator remains zero",
      "User ends recording → local transcript and summary generate",
      "User opens Data details → all artifact locations and delete controls appear"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "local models are installed",
        "when": "the user completes a meeting",
        "then": "audio, transcript and summary are created locally with zero application requests to external AI endpoints"
      },
      {
        "type": "given",
        "text": "the summary model is missing",
        "when": "the user finishes transcription",
        "then": "the transcript is preserved and model installation is offered without uploading data"
      },
      {
        "type": "given",
        "text": "disk space drops below the configured reserve",
        "when": "capture runs",
        "then": "the user is warned, capture stops safely before exhaustion and the recovery file remains readable"
      }
    ]
  },
  {
    "id": "US-006",
    "epic": "Bot-Free Local Capture",
    "role": "IT administrator",
    "action": "deploy a signed desktop client with centrally managed policy",
    "benefit": "bot-free capture follows organizational rules",
    "story": "As a IT administrator, I want to deploy a signed desktop client with centrally managed policy, so that bot-free capture follows organizational rules.",
    "gui_flow": [
      "Admin opens Deployment → installer and policy options appear",
      "Admin downloads the signed package → checksum is displayed",
      "Admin configures allowed models and retention → policy validates",
      "Admin deploys through device management → clients enroll",
      "Admin opens Device health → versions and compliance states appear",
      "Admin revokes a device → cloud sync and new captures are blocked"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a supported managed device enrolls",
        "when": "the client starts",
        "then": "it applies policy and reports version without uploading meeting content"
      },
      {
        "type": "given",
        "text": "the device is offline",
        "when": "policy expires",
        "then": "local capture follows the configured grace period and displays the expiry"
      },
      {
        "type": "given",
        "text": "signature verification fails",
        "when": "installation or update runs",
        "then": "the client refuses the package and reports a security event"
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

## Priority-Ranked Development Recommendations

1. **P0: Evidence-grounded review and approval.** Make every claim traceable, editable, versioned and policy-gated.
2. **P0: Bot-free desktop capture and measurable local STT.** Package the existing local direction into a reliable user product.
3. **P0: Artifact lineage, retention and verifiable deletion.** Unify governance across storage, exports, shares and integrations.
4. **P1: Quality benchmark and observability.** Publish internal WER/DER/extraction metrics by supported profile.
5. **P1: Integration reliability.** Add outbox, idempotency, reconciliation and user-facing delivery logs.
6. **P1: Accessibility and browser E2E.** Validate the broad workspace against WCAG and real workflows.
7. **P2: Pricing experiments and paid pilots.** Measure activation, review time, successful action sync and retention before billing expansion.

## Recommended Scope for the Next Development Pass

Deliver one integrated “trusted meeting record” slice:

- Desktop companion for signed Windows/macOS capture of microphone plus system audio, with local-only and secure-upload modes.
- Canonical transcript segments with stable IDs, timestamps, speaker identity, confidence and revisions.
- Evidence references from every summary, decision and action to transcript segments and audio timecodes.
- Human review states, strict approval policies for selected modes, version history and safe sharing.
- Artifact registry covering audio, transcript, notes, exports, shares, webhook payloads and PM integration records.
- Idempotent deletion workflow with per-artifact outcome and signed receipt.
- Quality and operational test gates: WER/DER corpus, extraction grounding, crash recovery, zero-egress local mode, tenant isolation, browser E2E, accessibility, targeted tests and full regression suite.

Do not add new PM vendors, new dashboard centers, billing complexity, native mobile apps or broad “compliance certified” claims in this pass.

## Risks, Unknowns, and Assumptions

- The repository’s breadth may exceed its validated customer demand; no product telemetry or customer interviews were included.
- No reproducible accuracy benchmark proves transcription, diarization or extraction quality.
- Desktop capture introduces OS permissions, code signing, updates, recovery and hardware variability.
- Local processing can reduce data transit but does not remove consent obligations or guarantee regulatory compliance. citeturn2search71turn2search75turn2search76
- State-count details conflict across consent guides, so the product must support configurable policy and legal review rather than encode a universal legal conclusion. citeturn2search71turn2search72turn2search75
- The current environment could not run pytest due missing dependencies; release status must be independently reproduced from a clean lockfile install.
- Version drift among README, package metadata and CHANGELOG indicates release-process debt.
- Assumption to test: regulated and professional teams will pay more for evidence, local capture and governance than for another summary generator.

## Sources

Accessed 2026-08-13 unless noted.

1. Fastio, “10 Best AI Meeting Assistants in 2026.” citeturn2search60
2. AI Meeting Ops, “AI Meeting Assistant Pricing Comparison,” 2026-06-03. citeturn2search61
3. People Managing People, “10 Best AI Meeting Assistant Tools,” updated 2026-08-11. citeturn2search62
4. Meetily, “AI Meeting Assistant Comparison 2026,” updated 2026-06-12. citeturn2search63
5. AI Agents Guide, “Best AI Meeting Assistants 2026,” updated 2026-05. citeturn2search64
6. Fellow, “The 22 Best AI Meeting Assistants for 2026.” citeturn2search65
7. TrendSpotted Hub, competitor comparison, 2026-06-17. citeturn2search66
8. StackScored, pricing comparison, verified 2026-04-21. citeturn2search67
9. AI Tools Insight, comparison, 2026-05-30. citeturn2search69
10. Otter.ai, sales transcription comparison, 2026-06-17. citeturn2search70
11. Basil AI, consent laws guide, 2026-03-12. citeturn2search71
12. RecordingLaw, AI meeting recording laws, published 2026-04-03 and reviewed 2026-08-09. citeturn2search72
13. Juggle, privacy risks, 2026-07-11. citeturn2search73
14. LiveSuggest, GDPR consent guide, 2026-02-14. citeturn2search74
15. Canary, consent and legality guide, updated 2026-06-16. citeturn2search75
16. Sonomos, HIPAA/GDPR/privacy guide, 2026-05-14. citeturn2search76
17. MeetingBro GitHub repository. citeturn2search77
18. Meetily GitHub repository. citeturn2search78
19. Meetily open-source product page. citeturn2search79
20. explainx.ai, Meetily technical review, 2026-07-08. citeturn2search80
21. KnightLi, Meetily architecture review, 2026-07-06. citeturn2search81
22. OpenTechHub, Meetily maturity assessment. citeturn2search82
