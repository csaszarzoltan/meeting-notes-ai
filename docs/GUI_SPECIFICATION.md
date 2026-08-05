# MeetingNotesAI GUI Specification v1.0

## Product promise

**Every conversation becomes verified notes and completed work.** The interface is organized around outcomes rather than transcripts and implements three layers:

1. **Capture:** live, uploaded, calendar-imported, or in-person conversations with visible privacy choices.
2. **Trust:** source-linked notes, speaker confidence, human review, and explicit approval.
3. **Execution:** confirmed actions, integrations, controlled sharing, search, insights, and compliance evidence.

## Information architecture

Desktop navigation contains Home, Meetings, Record, Actions, Batches, Team, Sharing, Insights, Compliance, Integrations, and Settings. Mobile navigation contains Home, Meetings, a central Record action, Actions, and More. Technical backend concepts are placed under user goals rather than exposed as product navigation.

## Key screens

- **Home:** review queue, actions, saved time, evidence coverage, and next-best actions.
- **Meeting setup:** capture method, context, template, language, policy, retention, and data path.
- **Live workspace:** recording status, speaker-aware transcript, confidence correction, and live intelligence.
- **Processing:** eight durable stages with accurate recovery language.
- **Review:** outline, editable notes, audio, transcript evidence, decisions, actions, and approval.
- **Actions:** Suggested, Confirmed, Synced, and Completed lifecycle with source moments.
- **Sharing:** five-step wizard with exact recipient preview.
- **Insights:** cross-meeting synthesis where every claim links to source moments.
- **Compliance:** critical issues and remediation before passing controls or trends.

## Visual and accessibility system

The product uses a calm dark navigation, light content surfaces, one deep-purple accent, semantic green/amber/red statuses, restrained shadows, 10-18px radii, and generous spacing. It includes semantic landmarks, skip navigation, ARIA live regions, visible focus, reduced-motion support, non-color status text, responsive layouts, and 44px mobile targets.

## Existing API contracts used by the GUI

- `POST /api/v1/meetings` for upload processing
- `POST /api/v1/auth/login` for authentication
- `POST /api/v1/meetings/live/start` and `WS /api/v1/meetings/live` for live capture
- `POST /api/v1/meetings/{meeting_id}/share` for secure share creation
- Existing batch, team, audit, compliance, webhook, and storage APIs remain authoritative for subsequent data wiring

## v1.0.1 persistence contract

The React workspace now reads and writes `/api/v1/workspace/*`. The service atomically persists local workspace state under `data/workspace_state.json`, which is intentionally ignored by Git. Review updates create immutable version and audit records. Action synchronization uses connector adapters and returns durable provider-shaped external references; vendor OAuth and remote API credentials remain deployment-specific. Safe sharing is limited to backend-enforced expiry, approval gating, persistence, and revocation. Unsupported passcode/domain/permission claims were removed.

## v1.1.0 modern experience system

The primary hierarchy is now **next action → meeting lifecycle → verified record → accountable execution**. Home prioritizes review and action queues instead of transcript volume. The global Command Palette provides keyboard-first search and navigation. Meeting Review is a dedicated studio with lifecycle state, autosave feedback, source confidence, previous/next evidence, original/current comparison, mobile content tabs, sticky playback, and explicit approval controls. The design system also includes compact density, dark theme, skeletons, and reusable loading, partial-success, offline, permission-denied, retry, and empty states.
