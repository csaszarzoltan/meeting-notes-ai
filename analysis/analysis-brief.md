# Analysis Brief — In-Person Bot-Free Recording (Ambient Capture + Local STT + Diarization)

**Feature:** "Record in person" — ambient device-mic capture → batch/local Whisper transcription → speaker diarization → privacy-first review-workspace integration.

**Repo:** `/home/zoltan/meeting-notes-ai` (checked-out branch `master`; task body said `main`, but the repo default is `master` — confirmed by `git branch --show-current`).
**Analyst:** kanban t_754e14fb (this task). **Protocol:** structure work, no implementation/tests.
**Version:** pyproject.toml reports `1.2.0` (`pyproject.toml:6`); task body said v1.1.2 — repo is newer.
**Research source:** `/home/zoltan/meeting-notes-ai/analysis/research-brief.md` (parent t_6caff5dc, read in full) + direct repo inspection of every file cited below.

---

## 0. Executive Summary

The "Record in person" capture card exists in the UI (`MeetingSetup.tsx:5` — 4th CAPTURE item, icon `◎`), but its primary button is disabled because `isAvailable` only admits `'Record live'` and `'Upload recording'` (`MeetingSetup.tsx:8`), and the button's disabled label literally reads `"Record in person is not available yet"`. **Critically, the entire downstream pipeline already exists and is tested**: browser-mic → WebSocket → Whisper → LLM extraction → review workspace (`useLiveSession.ts`, `routes/live_transcription.py`, `services/live_transcription.py`, `services/extraction.py`, `ReviewWorkspace.tsx`). The highest-value work is **wiring the stub** and adding **two genuine capability tiers**:

1. **Local (faster-whisper) STT backend** — a `TRANSCRIPTION_BACKEND=local|openai` switch so regulated (Healthcare/Legal) meetings never send audio to a third party, returning the exact same `TranscriptionResult` shape so no downstream code changes.
2. **Speaker diarization** — per-speaker labels carried through `TranscriptSegment.speaker` into `LiveTranscriptResponse`, extraction `assignee`, and `ReviewWorkspace` evidence.

The core insight (confirmed by both the research brief and direct code inspection) is: **do not greenfield a capture mode; wire the existing live path to the in-person card and bolt on local-STT + diarization tiers.** This keeps blast radius small and reuses ~1000 already-tested lines.

---

## 1. Current State Assessment

Each finding is grounded in a concrete file:line.

### 1.1 Frontend — the gate is the only true gap
- `frontend/src/workspace/MeetingSetup.tsx:5` — `CAPTURE = ['Record live', 'Upload recording', 'Import calendar meeting', 'Record in person']`. The 4th element ('Record in person', icon `◎`, desc `"In-person workflow preview"`) **is rendered and selectable**; selecting it just highlights the card.
- `MeetingSetup.tsx:8` — `const isAvailable = capture === 'Record live' || capture === 'Upload recording'`. 'Record in person' is **not** in `isAvailable`.
- `MeetingSetup.tsx:10 (button JSX)` — `<button className="primary full" disabled={!isAvailable} onClick={() => capture === 'Record live' ? onLive() : setConfigured(true)}>{isAvailable ? `Continue with ${capture}` : `${capture} is not available yet`}</button>`. So for 'Record in person': button disabled, label `"Record in person is not available yet"`. **This is the entire frontend blocker.**
- The `Record live` mode calls `onLive()` → `App.tsx:47` `onLive={() => setLive(true)}` → renders `LiveWorkspace` (`App.tsx:44`).
- `App.tsx:43` — `ReviewWorkspace` renders when a meeting is `selected` or `result` is set. `onComplete={setResult}` (`App.tsx:47`) is how upload flows drop into review. So there are **two** downstream targets already wired: live (`setLive`) and review (`setResult`).

### 1.2 Frontend — capture machinery already built (keep it)
- `frontend/src/live/useLiveSession.ts:117-134` — picks `audio/webm;codecs=opus` else `audio/webm` (`MediaRecorder.isTypeSupported`), `recorder.start(1000)` (1s timeslice), streams binary WebM chunks over a JWT WebSocket. Mic-permission errors are mapped to a user-facing message (`useLiveSession.ts:187-191`: `NotAllowedError` → "Microphone permission denied…").
- `useLiveSession.ts:196-204` — `finalize()` sends `{"type":"finalize"}` control frame; finalized result carries transcript/summary/action_items/decisions (`LiveTranscriptionView.tsx:178-213`).
- `LiveTranscriptionView.tsx:5-13` — `STATUS_LABEL` maps the full `LiveStatus` (idle→error) to UI text — exactly the "recording status" the task's acceptance criteria #6 asks for. It already surfaces recording status, partial count, sequence, and duration.
- `frontend/src/workspace/LiveWorkspace.tsx` — thin wrapper rendering `LiveTranscriptionView`.
- **Important gap for #6/#4:** after `finalize`, `LiveTranscriptionView.tsx` shows a static "finalized" overlay (`:178-213`) and **does not navigate/route into `ReviewWorkspace`**. There is no `useNavigate`-style transition from finalize → review. This is a **real missing integration** (research FC-5).

### 1.3 Backend — full streaming pipeline exists and is tested
- `src/meeting_notes_ai/routes/live_transcription.py`:
  - `get_live_service()` (`:55-70`) builds `LiveTranscriptionService` with `TranscriptionService(api_key=api_key, model=settings.whisper_model)` + `ExtractionService`. **This is the single construction point to rewire for the local backend.**
  - WebSocket `""` (`:73-186`) — JWT (token query param), meeting/room/team scoping, binary chunks (WebM magic detection `:147-152`), partial frames, `finalize` control frame.
  - `POST /start` (`:189-212`) — provisions a draft `Meeting` row the WS attaches to (owner/team checks).
  - `POST /upload` (`:215-244`) — REST fallback; empty→`400` (`:225`), unsupported content-type→`415` (`:229`), >`max_audio_size_mb`→`413` (`:234`), rate-limit→`429` (`:243`). **This is the reference for audio-upload validation the pre-tester's ambient-recording tests should target.**
- `src/meeting_notes_ai/services/live_transcription.py`:
  - `ingest_chunk` (`:185-219`) accumulates audio and re-transcribes the **whole accumulated buffer** per chunk (`:208-209`) — **O(n²) for long rooms** (research risk — batch finalize path avoids this).
  - `finalize` (`:230-279`) — transcribe + extract + persist meeting (transcript + summary in `metadata_json` via `_persist_meeting` `:378-422`), marks session `FINALIZED`.
  - `transcribe_file` (`:281-328`) — REST batch path, creates meeting with `create_if_missing=True`.
  - `_assemble_audio` (`:424-431`) / `_pcm16_to_wav` (`:88-114`) — frames 16 kHz PCM as WAV; WebM chunks concatenated raw.
  - `LiveRateLimitExceeded` (`:84`) — mapped to 429 / WS error frame.
- **NOTE on rate limiting:** `create_session` (`:139-165`)/`finalize`/`transcribe_file` do **not** pass `hipaa`/`phi_classification` through to the persist path, and `finalize` hard-codes `mode="general"` (`finalize` `:253`, `_persist_meeting` `:259`). A Healthcare/Legal in-person meeting would be persisted as `general` → **the privacy tier (FC-4) requires threading meeting `mode`/`hipaa` through finalize/transcribe_file.** Grounded at `live_transcription.py:253 & 259`.

### 1.4 Models & config — extension points already present
- `src/meeting_notes_ai/models.py:67-77` — `TranscriptionResult` (text/language/duration_seconds/`segments`) and `TranscriptSegment` (start/end/text). **No `speaker` field yet** — diarization needs to add `speaker: str | None = None` to `TranscriptSegment`.
- `models.py:107-117` (ConsentStatus/HealthcareNote), `:83-88` `ExtractionResult`, `ActionItem` (assignee). `ExtractionResult.action_items[].assignee` already exists — diarized speaker can seed `assignee`.
- `src/meeting_notes_ai/config.py:16` — `whisper_model` env (`WHISPER_MODEL`, default `"whisper-1"`). Only interpreted as an OpenAI model name today. **Add `transcription_backend` (`TRANSCRIPTION_BACKEND`, default `"openai"`) here.**
- `config.py:98-101` — `SUPPORTED_AUDIO_FORMATS = {audio/wav, audio/mpeg, audio/mp4, audio/webm}`.
- `config.py:17-19` — `max_audio_size_mb` default 25 (OpenAI cap). Local backend can raise this but keep default for parity.
- `src/meeting_notes_ai/services/workflow.py:21-35` — `resolve_processing_policy(mode, phi_redaction)` returns `ProcessingPolicy(phi_redaction, review_required)`; Healthcare → redaction+review, Legal → review. **Reuse this to gate the no-third-party assertion for the local tier.**
- `src/meeting_notes_ai/services/transcription.py` — `TranscriptionService.transcribe(audio_bytes, filename, language=None) -> TranscriptionResult` (`:26-76`). This is the **interface the local backend must share** (research hint §3 "keep the existing TranscriptionService interface").

### 1.5 Review workspace integration point
- `src/meeting_notes_ai/routes/workspace.py:292-311` — `PATCH /meetings/{meeting_id}/review` persists `summary` + `review_status` (`needs_review|in_review|approved|rejected`) + reviewer + audit. This is the **write-back** side for review integration.
- `workspace.py:226-255` — `POST /meetings` creates meeting + initial `evidence` list; `evidence` items carry `speaker` ("Speaker 1"), `timestamp`, `text`, `confidence` (`:236-239`).
- `workspace.py:283-310` — `GET /meetings/{id}` detail; `meeting_detail` → used by `ReviewWorkspace.tsx:12` to load detail.
- `frontend/src/workspace/ReviewWorkspace.tsx:5` — `fromUpload` maps a `MeetingResult` into `MeetingDetail` (title/date/duration/participants/review_status/evidence/versions/decisions/audio_url). `:6` — `ReviewTab = 'Notes'|'Transcript'|'Evidence'|'Actions'`. Evidence fallback `:8` shows `speaker`/`timestamp`/`text`/`confidence`. So `ReviewWorkspace` **already renders a `speaker` field per evidence item** — diarized speaker labels will surface here with zero frontend schema change.
- **Gap:** the live path ends at `LiveTranscriptionView` finalize overlay, not `ReviewWorkspace`. To satisfy acceptance #4 + research FC-5, the finalized in-person meeting must navigate into review (either `selected` detail or a `result`-shaped object).

### 1.6 Testing baseline (for pre-tester handoff)
- 51 test files under `tests/`. Existing relevant coverage: `test_live_session.py`, `test_live_transcription.py`, `test_live_ui.py`, `test_upload*.py` (within `test_live_transcription`), `test_transcription.py`, `test_review_remediation_v112.py`, `test_workspace_api_v102.py`.
- **The pre-tester test seam pattern** is established in `tests/test_live_ui.py`:
  - `_FakeTranscription` (`:25-36`) and `_FakeExtraction` (`:39-50`) duck-typed AI seams returning deterministic `TranscriptionResult`/`ExtractionResult`.
  - `app.dependency_overrides[get_live_service] = lambda: service` (`:159`) to swap in the fake-backed service — **the exact pattern the new diarization/ambient tests should reuse.**
  - Interface tests introspect route registration (`:66-84`) and handler signatures (`:77-84`).
- **Frontend JS tests: NONE.** `frontend/package.json` (`:7-12`) has only `dev/build/preview/typecheck` scripts, no vitest/jest/test script, and no test devDependency (`:17-23`). **Conclusion: "add a frontend test if a pattern exists" → no frontend JS test pattern exists. The pre-tester must validate the MeetingSetup card via backend UI-glue tests (`test_live_ui.py`-style: `/app/live` route + CSP/Permissions-Policy) and negative-availability assertions, or leave UI behavior to the tester's E2E/Playwright smoke.** Do NOT invent a JS test framework.

---

## 2. Clustered Options

Clustered from `research-brief.md` §2 (6 feature candidates) + repo constraints. Options are grouped by the decision they force.

### Cluster A — Capture path: reuse live WS vs. new batch-only path
- **A1 (chosen): Reuse the existing live WebSocket pipeline** (`useLiveSession.ts` + `routes/live_transcription.py`). Already built + tested; the in-person card becomes a thin activation of `onLive()`. Cost: the `ingest_chunk` O(n²) accumulate loop (mitigated by a dedicated batch finalize — see A2).
- A2: **Add a record-then-transcribe-batch path** for long in-person rooms: capture uses the same mic/WS, but on finalize the client sends accumulated WebM once (via existing `POST /upload` / `transcribe_file`) instead of re-transcribing each chunk. Lower API cost, no live partials. **Recommended as P1 (not P0)** — P0 wires the live path; batch finalize becomes a latency/cost refinement.
- Rejected: building a brand-new WebSocket protocol for in-person only — duplicates 1000+ tested lines for no behavioral gain.

### Cluster B — Transcription backend: OpenAI API vs. local
- **B1 (chosen, both): Dual backend, switch by env.** `TRANSCRIPTION_BACKEND=openai|local`. Openai = existing `TranscriptionService` (already correct). Local = new `LocalWhisperTranscriptionService` backed by **faster-whisper** (CTranslate2). Shared return shape `TranscriptionResult` → zero downstream change. Regulated mode (Healthcare/Legal) + `local` → assert no OpenAI call.
- B2 (rejected as default): local-only. Higher infra burden (model download on first day), worse accuracy ceiling for casual users, and there's no consumer-ready packaging in-repo. Keep local as opt-in tier.
- Model tiers (research §3, faster-whisper): `small` (fast CPU) → `large-v3-turbo` (near-API accuracy); `compute_type="int8"` on CPU. `WHISPER_MODEL=local:large-v3-turbo` encoding or a separate `LOCAL_WHISPER_MODEL`.

### Cluster C — Diarization
- **C1 (chosen for P1): pyannote.audio 3.1** (`pyannote/speaker-diarization-3.1`), gated HF token, mono 16 kHz RTTM, then **max-overlap alignment** against Whisper word/segment timestamps. Best-accuracy open model (DER ~11–19%), self-hostable (privacy parity target).
- C2: OpenAI `gpt-4o-transcribe-diarize` — cloud, built-in, simplest, but **sends audio off-server** → fails the local privacy tier. Keep as a `backend=openai` convenience option behind the same speaker-label interface.
- C3 (rejected now): WhisperX end-to-end — pulls heavier dep set + wants GPU; overkill for P0/P1, can be revisited.
- **Design principle (research §3 + §4):** diarization is **best-effort post-processing**; the review workspace lets users **correct speaker labels**, never a hard guarantee. Speaker labels flow: `TranscriptSegment.speaker` → `LiveTranscriptResponse` → extraction `assignee` seed → `ReviewWorkspace` evidence `speaker`.

### Cluster D — Audio upload endpoint & storage
- D1 (chosen): Reuse `POST /api/v1/meetings/live/upload` (`routes/live_transcription.py:215`) as the batch upload endpoint — already has empty/415/413/429 validation. For the ambient-recording spec, pre-tester targets this exact endpoint contract.
- D2 (optional P2): a dedicated `POST /api/v1/meetings/in-person/{id}/audio` streaming endpoint for long recs (chunk-append to object storage). **Not needed for P0** — `transcribe_file` handles a full upload; storage already configured (local dir / S3 via `config.py:56-73`). Skip unless the tester discovers a 25 MB hardship.
- Storage: keep **existing storage backend** (`config.py:56-73`: `STORAGE_BACKEND=local|s3`, encryption, retention). In-person audio is stored identically to live/upload; no new storage path.

### Cluster E — Privacy tier plumbing
- E1 (chosen): `resolve_processing_policy()` (`workflow.py:21`) gates `phi_redaction`/`review_required`. Backend=local asserts **no OpenAI call** for Healthcare/Legal. Thread meeting `mode`/`hipaa` through `finalize`/`transcribe_file` (currently hard-coded `"general"` at `live_transcription.py:253/259`). UI already claims "Encrypted processing / Zürich / EU" (`MeetingSetup.tsx` data-path aside) — local backend makes that honest.
- E2 (deferred): new explicit "audio stays on your hardware" toggle beyond what the data-path panel already shows. Nice-to-have copy, P2.

---

## 3. Chosen Tech Stack (with rationale)

| Concern | Choice | Rationale (grounded) |
|---|---|---|
| Capture | Reuse `useLiveSession.ts` MediaRecorder → WS | Already built + tested (`useLiveSession.ts:117-134`). In-person = activate `onLive()` on the 4th card. Cross-browser WebM/Opus caveat documented (research §4); accepted for P0. |
| STT (openai tier) | Existing `TranscriptionService` (`transcription.py:26`) | Already correct; keep as `TRANSCRIPTION_BACKEND=openai` default. |
| STT (local tier) | New `LocalWhisperTranscriptionService` via **faster-whisper** (CTranslate2), `compute_type="int8"`, WAV input, shared `TranscriptionResult` | Privacy/compliance win; zero downstream change (interface parity). Faster-whisper is the canonical local backend (research FC-2). |
| Backend switch | `TRANSCRIPTION_BACKEND` env + a `WhisperTranscriber` protocol in a new module | Selection lives in ONE place: `get_live_service()` (`routes/live_transcription.py:55-70`) and `routes/meetings.py::_build_services` (`:24-27`). |
| Diarization | **pyannote.audio 3.1** (P1), gated HF token, mono 16 kHz, max-overlap alignment; optional OpenAI `gpt-4o-transcribe-diarize` for openai backend | Best open accuracy, self-hostable. See Cluster C. |
| Upload endpoint | Reuse `POST /api/v1/meetings/live/upload` (`routes/live_transcription.py:215`) | Already validates empty/415/413/429. Directly targetable by pre-tester. |
| Storage | Existing backend (`config.py:56-73`, local/S3 + encryption + retention) | No new storage path needed. |
| Review integration | Route finalized in-person meeting into `ReviewWorkspace` via `POST /meetings` (`workspace.py:226`) + `PATCH /meetings/{id}/review` (`workspace.py:292`) | Evidence `speaker` field already rendered (`ReviewWorkspace.tsx:8`). |
| Privacy policy | `resolve_processing_policy()` (`workflow.py:21`) + hard no-OpenAI assert for Healthcare/Legal+local | Reuses existing safeguards; no new policy engine. |
| Frontend state | Extend `LiveStatus`/MeetingSetup `isAvailable` + post-finalize navigation to review | Minimal surface: unblock the card + add a review transition. |

**Decisions locked:**
1. **Whisper API vs local → BOTH**, switched by `TRANSCRIPTION_BACKEND`; local via faster-whisper. Do not replace the API path.
2. **Diarization → pyannote.audio 3.1** (openai tier optional `gpt-4o-transcribe-diarize`) behind a shared speaker-label interface; best-effort + UI correction.
3. **Audio upload design → reuse `POST /live/upload`** (validation contract already defined); no new endpoint for P0.
4. **Storage → existing backend**, no change.
5. **Frontend capture hook → reuse `useLiveSession`**, activate `onLive()` for the 4th card, add finalize→review navigation.

---

## 4. Prioritized Task List (P0 / P1 / P2)

Each task: **module, expected behavior, interface description, dependencies, acceptance criteria.** All file:line refs = current repo ground truth.

---

### P0-1 — Unblock the "Record in person" card and route to live capture
- **Module:** `frontend/src/workspace/MeetingSetup.tsx` (and `App.tsx` only if a distinct route is warranted).
- **Expected behavior:** Selecting "Record in person" makes the primary button enabled; clicking it enters the live capture flow (same as "Record live": `onLive()` → `setLive(true)` → `LiveWorkspace` at `App.tsx:44/47`). The "…is not available yet" label is gone.
- **Interface:** `isAvailable` (currently `MeetingSetup.tsx:8`) must include `'Record in person'`; the button `onClick` (`capture === 'Record live' ? onLive() : setConfigured(true)`, `MeetingSetup.tsx:10`) must map `'Record in person'` → `onLive()` (or a new `onInPerson` prop wired in `App.tsx:47` the same way — either is acceptable; keep the SHA to one file if possible).
- **Dependencies:** none (pure frontend #1 of the acceptance criteria).
- **Acceptance criteria:**
  - Selecting "Record in person" enables the primary CTA; label reads `Continue with Record in person`.
  - Clicking navigates into `LiveWorkspace` (same route as live).
  - No regression to the other three cards (`Record live`, `Upload recording`, `Import calendar meeting` behave unchanged).
  - **Pre-tester:** negative availability assertions + `/app/live` UI-glue tests (CSP allows mic/WS, `Permissions-Policy` has microphone) à la `tests/test_live_ui.py:255-277`. No JS framework exists.

### P0-2 — Add diarization primitive to the transcript data model
- **Module:** `src/meeting_notes_ai/models.py` (add `speaker`) + `src/meeting_notes_ai/live_session.py` (surface in responses) + `src/meeting_notes_ai/services/extraction.py` (seed `assignee`).
- **Expected behavior:** `TranscriptSegment` gains an optional `speaker`; `LiveTranscriptResponse` (and any batch response) can carry per-segment speaker labels; `ExtractionService` prompt optionally receives speaker-tagged transcript for assignee seeding.
- **Interface:**
  - `models.py:74-77` — `TranscriptSegment` add `speaker: str | None = None` (backwards compatible default).
  - `services/transcription.py:62-69` — when the provider returns speaker info, populate the new field (currently only start/end/text mapped).
  - `live_session.py` `LiveTranscriptResponse` (`:124-147`) — add optional `speakers: dict[int,str] | None` or extend segments; decide: keep segment-level `speaker` as the source of truth and expose a convenience `speakers` map; both optional defaults so existing serialization is unchanged.
- **Dependencies:** P0-1 (nothing code-wise, but review integration in P0-4 consumes it).
- **Acceptance criteria:**
  - `TranscriptSegment(speaker="Speaker 1")` constructs; default `speaker=None` for untouched callers (no test/API regression).
  - A transcript built from segments with `speaker` set round-trips through `TranscriptionResult` and `LiveTranscriptResponse.model_dump(mode="json")` unchanged otherwise.
  - Existing tests (`test_transcription.py`, `test_live_transcription.py`) stay green with the default `None`.

### P0-3 — Local faster-whisper STT backend behind `TRANSCRIPTION_BACKEND`
- **Module:** new `src/meeting_notes_ai/services/local_transcription.py` (+ `TranscriptionService` parity) and `src/meeting_notes_ai/config.py`.
- **Expected behavior:** With `TRANSCRIPTION_BACKEND=local`, transcription is served by faster-whisper locally; with `openai` (default), behavior is unchanged. Same `transcribe(audio_bytes, filename, language)` signature and `TranscriptionResult` return.
- **Interface:**
  - `config.py:16` — add `transcription_backend: str = os.getenv("TRANSCRIPTION_BACKEND", "openai")` and `local_whisper_model: str = os.getenv("LOCAL_WHISPER_MODEL", "small")` (or reuse `WHISPER_MODEL=local:<model>` encoding — pick one, document it).
  - `services/local_transcription.py` — `class LocalWhisperTranscriptionService` with `async def transcribe(self, audio_bytes, filename, language=None) -> TranscriptionResult`; wraps faster-whisper `WhisperModel(model, compute_type="int8")`; WAV assumed; maps segments (with `speaker` reserved for P1).
  - Wiring: `routes/live_transcription.py::get_live_service` (`:55-70`) and `routes/meetings.py::_build_services` (`:24-27`) construct the right backend from `settings.transcription_backend`.
  - `show_download_progress`/caching: keep model download on first use (faster-whisper handles caching to disk).
  - Add `faster-whisper` to `pyproject.toml` `dependencies` as optional (comment: local tier; keep default install light) or a conditional extra — **must be pinned, not just pip-installed** (repo convention).
- **Dependencies:** P0-2 (return shape already carries segments; speaker comes in P1).
- **Acceptance criteria:**
  - `TRANSCRIPTION_BACKEND=openai` keeps the exact existing behavior (regression-clean).
  - `TRANSCRIPTION_BACKEND=local` yields a `TranscriptionResult` with `text`/`language`/`duration_seconds`/`segments` from a fake faster-whisper (injectable/duck-typed — pre-tester supplies `_FakeLocalWhisper`).
  - Both backends share the same `transcribe` signature; no caller in `live_transcription.py` / `transcribe_file` changes shape.
  - Deps pinned in `pyproject.toml`; tests run via `.venv`.

### P0-4 — Route finalized in-person meeting into the review workspace
- **Module:** backend `src/meeting_notes_ai/services/live_transcription.py` (`finalize`/`transcribe_file`/`_persist_meeting`) + `src/meeting_notes_ai/routes/live_transcription.py` + frontend `frontend/src/live/LiveTranscriptionView.tsx` (finalize → review navigation).
- **Expected behavior:** A finalized in-person/live meeting ends up as a reviewable `MeetingDetail` (`workspace.py` shape) with evidence-linked summary/decisions/action items (acceptance #4), and the UI transitions from the finalize overlay into `ReviewWorkspace`.
- **Interface:**
  - `live_transcription.py:378-422` `_persist_meeting` — currently writes transcript + summary (`metadata_json`) + action_items/decisions/key_points. **Add evidence persistence** so the meeting detail returns `evidence` with `speaker`/`timestamp`/`confidence` (schema matches `workspace.py:236-239`).
  - Thread meeting `mode`/`hipaa` through `finalize` (`:230-279`, currently `mode="general"` at `:253/259`) and `transcribe_file` (`:281-328`) so Healthcare/Legal review flags and policy hold.
  - `LiveTranscriptionView.tsx` — after `status === 'finalized'` (`:153-155`), navigate to review (either lift `meetingId`/result to `App.tsx` `setResult`, or add an `onOpenReview(result)` prop). Keep the finalize overlay as the transition point.
- **Dependencies:** P0-2 (speaker in evidence), P0-3 (backend parity).
- **Acceptance criteria:**
  - Finalizing an in-person session yields a meeting retrievable via `GET /meetings/{id}` (`workspace.py:283`) with `summary` + `evidence[]` (each with speaker/timestamp/confidence).
  - Healthcare/Legal mode persists `review_status="needs_review"` and does not route audio to OpenAI when `backend=local` (no-OpenAI assert, `workflow.py:21` policy).
  - UI navigates finalize → `ReviewWorkspace` with title/summary/decisions/action items.
  - **Pre-tester `test_review_integration.py`:** a fake-backed finalized session produces a ReviewWorkspace-shaped detail via `workflow.py`/`extraction.py` with evidence-linked summary/decisions/action items.

---

### P1-1 — Speaker diarization (pyannote.audio 3.1, self-hosted)
- **Module:** new `src/meeting_notes_ai/services/diarization.py`; integration in `local_transcription.py` / `transcription.py` and `live_transcription.py::_persist_meeting`.
- **Expected behavior:** After transcription, a diarization pass assigns a `speaker` to each `TranscriptSegment` via max-overlap alignment; labels surface in evidence and seed extraction `assignee`.
- **Interface:**
  - `diarization.py` — `class SpeakerDiarizer` with `async def diarize(self, audio_bytes, sample_rate) -> list[tuple[float,float,str]]` (start,end,speaker) or returns an aligner; handles mono downmix to 16 kHz; gates on HF token (`HF_TOKEN`) config; emits best-effort labels.
  - Alignment helper: given Whisper segments `[start,end]` and diarization turns, assign each segment to the turn it overlaps most. Optional `gpt-4o-transcribe-diarize` path guarded by backend=openai.
  - `local_transcription.py`/`transcription.py` — fill `TranscriptSegment.speaker` when diarization enabled (`DIARIZATION=1` env, default off for P0 parity).
  - `extraction.py:65-94` — when speaker tags present, add speaker context to the prompt so `assignee` can be seeded from the speaker (`extraction.py:106-114`).
- **Dependencies:** P0-2 (speaker field), P0-3 (local backend).
- **Acceptance criteria:**
  - Multi-speaker input yields segments with distinct `speaker` labels.
  - Alignment assigns each segment to the single best-overlap diarization turn.
  - No requirement on raw accuracy (best-effort per research risk §4); the review UI can correct labels.
  - `DIARIZATION=0` (default) is byte-identical to P0 behavior.
  - **Pre-tester `test_diarization.py`:** fake diarizer → transcript segments carry `speaker`; alignment correctness with overlapping timestamps.

### P1-2 — Batch "record-then-transcribe" long-recording finalize
- **Module:** `frontend/src/live/useLiveSession.ts` (finalize path) + `services/live_transcription.py` (batch path).
- **Expected behavior:** For long in-person rooms, finalize sends the accumulated WebM once (`POST /upload` → `transcribe_file`) instead of re-transcribing per chunk, avoiding the O(n²) `ingest_chunk` loop (`live_transcription.py:208-209`).
- **Interface:** `useLiveSession.ts::finalize` — add a "batch finalize" branch that, when the session is long (or a local flag), uploads the assembled blob to `POST /api/v1/meetings/live/upload` and interprets the `LiveTranscriptResponse`. Keep live partials for short/interactive sessions.
- **Dependencies:** P0-4 (review routing after batch finalize).
- **Acceptance criteria:**
  - Batch finalize produces the same `LiveTranscriptResponse` shape as WS finalize.
  - Long-room finalize does not re-transcribe accumulated audio N times.
  - Validation (empty/415/413/rate-limit) preserved.

### P1-3 — Privacy-tier affordance surfacing (local-only guarantees in UI)
- **Module:** `frontend/src/workspace/MeetingSetup.tsx` (data-path aside) + config wiring.
- **Expected behavior:** When backend=local and/or mode is Healthcare/Legal, the data-path panel (already claims "Encrypted processing / Zürich / EU", `MeetingSetup.tsx` data-path aside) explicitly states audio stays on the server/hardware; a local-backend badge.
- **Interface:** read `TRANSCRIPTION_BACKEND`/mode to conditionally render a "Local processing, no third-party" line; do not overpromise if not enforced. Minimal copy change → keep it honest per research risk (§4).
- **Dependencies:** P0-3.
- **Acceptance criteria:** Copy reflects actual backend; no new claims when backend=openai.

---

### P2 (deferred / nice-to-have)
- **P2-1 — Dedicated long-recording streaming upload endpoint** (`POST /meetings/in-person/{id}/audio`, chunk-append to object storage). Only if 25 MB cap (`config.py:17-19`) becomes a real hardship. Depends on storage D2.
- **P2-2 — AudioWorklet/PCM capture path** for browsers that can't emit WebM/Opus or that want raw PCM (research §3: Safari mp4 preference). Server already supports PCM (`_pcm16_to_wav`, `live_transcription.py:88-114`). High effort, low P0 value.
- **P2-3 — Speaker-label correction UI in ReviewWorkspace** (research §4 best-effort mitigation). Requires diarization (P1-1).
- **P2-4 — Consent-state persistence** for `Record in person` mirroring the regulated checkbox (`MeetingSetup.tsx` regulated-fields) into `ConsentStatus` (`models.py:107-111`).

---

## 5. Dependency Graph

```
P0-1 (frontend card)            [no deps]
P0-2 (speaker model)            [no deps]
P0-3 (local STT)                <- P0-2 (return shape)
P0-4 (review routing+evidence)  <- P0-2, P0-3
P1-1 (diarization)              <- P0-2, P0-3
P1-2 (batch finalize)           <- P0-4
P1-3 (privacy affordance)       <- P0-3
P2-*                             <- various (deferred)
```

**P0 sequencing for dev:** P0-1 (smallest, unblocks demo) → P0-2 (data shape) → P0-3 (local STT) → P0-4 (review integration). P0-2 and P0-3 can be developed in parallel once P0-1 lands; P0-4 is the capstone that satisfies acceptance #2/#4/#5.

---

## 6. Cross-cutting notes for the pre-tester (t_32acfe3d)

The pre-tester writes the 4 test files listed in their task body. Key seams and conventions to reuse (all grounded):

1. **Seam pattern:** `tests/test_live_ui.py:25-50` — duck-typed `_FakeTranscription` / `_FakeExtraction`. For ambient recording, add a `_FakeLocalWhisper` (local STT) and a `_FakeDiarizer`. Inject via `app.dependency_overrides[get_live_service]` (`test_live_ui.py:159`).
2. **Endpoint under test:** `POST /api/v1/meetings/live/upload` (`routes/live_transcription.py:215-244`) for ambient recording + batch transcription; `POST /api/v1/meetings/live/start` for happy-path persist. Validation to assert: empty→400, wrong content-type→415, too-large→413, rate-limit→429.
3. **Review integration:** assert via `workflow.py::resolve_processing_policy` + `_persist_meeting` shape → `GET /meetings/{id}` (`workspace.py:283`) returns `summary` + `evidence[]` with `speaker`/`timestamp`/`confidence`.
4. **Interface tests** (pass immediately): `TranscriptSegment.speaker` default `None`; `LocalWhisperTranscriptionService.transcribe` signature; `TRANSCRIPTION_BACKEND` config; route registration (like `test_live_ui.py:66-84`).
5. **Behavioral tests** (RED while feature missing): local backend returns a real `TranscriptionResult`; diarized segments carry `speaker`; finalize persists evidence-backed review detail; review route persists status.
6. **NO frontend JS test framework exists** (`frontend/package.json:7-23`). Do not add one. Validate the MeetingSetup card via backend UI-glue (`/app/live` route, CSP/Permissions-Policy, `test_live_ui.py:255-277`) + negative availability; leave real browser capture to the tester's Playwright/E2E smoke.
7. Always run via `.venv/bin/python -m pytest` / `-m ruff`; pin any new runtime dep (faster-whisper, pyannote/pyannote-audio if diarization tests need import) in `pyproject.toml`, not just `.venv`.

---

## 7. Acceptance Criteria Matrix (feature-level → task-level)

| Feature AC (task body) | Satisfied by |
|---|---|
| 1. Device mic capture via "Record in person" card | P0-1 (+ existing `useLiveSession.ts`) |
| 2. Batch transcription via existing Whisper integration | P0-3 (local/API parity), P0-4 (persist) |
| 3. Speaker diarization | P1-1 (+ P0-2 model) |
| 4. Review integration (evidence-linked summary/decisions/actions) | P0-4 |
| 5. Privacy-first (local or own API key, no bot) | P0-3 (backend switch), P0-4 (mode/openai assert), P1-3 (UI affordance) |
| 6. UI state: preview→active, status+duration, → review | P0-1 (active), existing `LiveStatus` (status/duration), P0-4 (→ review) |
| 7. Error handling (mic denied, too short, Whisper API, network) | P0-1/P0-3/P0-4 + existing error paths (`useLiveSession.ts:187`, `routes/live_transcription.py:225-243`) |
| 8. TDD tests (start/stop, transcription, diarization, review) | Pre-tester t_32acfe3d (4 files) |

---

*End of brief. Grounded entirely in `/home/zoltan/meeting-notes-ai` code (file:line cited inline) and `analysis/research-brief.md`.*
