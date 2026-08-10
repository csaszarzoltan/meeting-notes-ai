# Research Brief — In-Person Bot-Free Recording

**Feature:** Ambient in-person mic capture → local/API Whisper transcription → speaker diarization → privacy-first review-workspace integration.
**Repo:** `/home/zoltan/meeting-notes-ai` (branch: `master`; task body said `main`, but the repo default branch is `master` — analyst should read this file from the checked-out branch).
**Research date:** 2026-08-10
**Researcher:** researcher profile (kanban t_6caff5dc)

---

## 1. Trend Summary

The 2026 meeting-notes market has converged on **bot-free, privacy-first capture** as the differentiator. Visible meeting bots (Otter, tl;dv, Fireflies) create social friction on client and sensitive calls; users increasingly want a tool that "does not join as a participant." The open-source response is a cluster of **local-first / self-hosted** recorders — Meetily (Rust + whisper.cpp/Parakeet + speaker diarization + Ollama summaries), OpenWhispr (local dictation/transcription), Granola (native macOS cloud notetaker) — that advertise "100% local processing, no cloud required." Repo-internal research (`research-findings.md`, 41 sources) independently reached the same conclusion: privacy/local deployment, consent-friendly capture, source-grounded review, and end-to-end action routing are the clearest openings that the big cloud vendors still serve poorly.

MeetingNotesAI is well-positioned to claim this lane: it *already* ships a working in-browser microphone → WebSocket → Whisper → extraction pipeline (`useLiveSession.ts` + `LiveTranscriptionView` + `routes/live_transcription.py` + `services/live_transcription.py`), plus a full review workspace (`ReviewWorkspace.tsx` with a `speaker` evidence field already present) and privacy affordances (mode-based PHI redaction + review-required policy in `services/workflow.py`, retention, encrypted storage). What's missing to complete "**Record in person**" is: (a) wiring the existing `MeetingSetup.tsx` "Record in person" stub to the live path, (b) a **local Whisper (faster-whisper) backend** for the privacy/compliance tier, (c) **speaker diarization**, and (d) routing the in-person meeting into the **review workspace** rather than the standalone live view. The core insight from repo inspection: **most of the plumbing already exists; the wins are in wiring and adding the local-STT + diarization tiers, not in greenfield build.**

---

## 2. Feature Candidates

### FC-1 — Wire the "Record in person" capture card to the existing live pipeline
- **What:** `MeetingSetup.tsx` already renders a `Record in person` card (icon `◎`, description "In-person workflow preview") but `isAvailable` is false for it and the primary button disables. Route it like `Record live` (`onLive()`), which opens `LiveWorkspace`. The browser mic→WS→partials→finalize stack is fully implemented and tested (`test_live_ui.py`, `test_live_transcription.py`).
- **Why:** Pure activation of existing code — the cheapest possible win. Unlocks the headline "in-person, bot-free" story from the first screen. No third-party bot is introduced (client-hostile behavior avoided).
- **Complexity:** Low.
- **Sources:** Repo: `frontend/src/workspace/MeetingSetup.tsx` (line 5 CAPTURE, lines 8/10 gating), `frontend/src/workspace/LiveWorkspace.tsx`, `frontend/src/live/useLiveSession.ts`. Market validation: `research-findings.md` §1A.2 (bot friction, reuses 41 sources); Meetily bot-free pitch — https://github.com/Zackriya-Solutions/meetily and https://meetily.ai/.

### FC-2 — Add a local Whisper backend via faster-whisper (WHISPER_MODEL = local)
- **What:** Today `services/transcription.py` hard-calls the OpenAI (`AsyncOpenAI`) Whisper API with `model=settings.whisper_model` (default `"whisper-1"`). The `settings.whisper_model` env knob *already exists* (`config.py`, `WHISPER_MODEL`, default `whisper-1`) but is only interpreted as an OpenAI model name. Add a `LocalWhisperTranscriptionService` backed by **faster-whisper** (CTranslate2 runtimes: `tiny/base/small/medium/large-v3/turbo`), selectable by env (`WHISPER_MODEL=local:large-v3-turbo` or a `TRANSCRIPTION_BACKEND=local` flag), sharing the same `TranscriptionResult`/`TranscriptSegment` return types so `live_transcription.py`, `transcribe_file`, and `finalize` don't change shape.
- **Why:** Privacy/compliance tier for healthcare/legal/finance (audio never leaves the server), plus cost control at high call volume (no per-minute API fees). Latency vs. accuracy tradeoff is tunable per model (tiny/small = fast but weaker; large-v3/turbo = near-API accuracy). Matches the local-first competitor wave.
- **Complexity:** Medium (new service + env wiring + optional worker/queue; return-shape parity keeps blast radius small).
- **Sources:** faster-whisper is the canonical CTranslate2 backend used by WhisperX and most local tools; cross-checked: codersera "faster-whisper vs whisper.cpp vs OpenAI Whisper (2026)" — https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/ (model tier guidance), WhisperX README (faster-whisper backend) — https://github.com/m-bain/whisperx, OpenWhispr local-vs-cloud — https://openwhispr.com/blog/local-vs-cloud-transcription.

### FC-3 — Speaker diarization (three options)
- **What:** Add per-speaker labels to transcripts so the review workspace can show "who said what." Options, cheapest→heaviest:
  1. **OpenAI `gpt-4o-transcribe-diarize`** (API, built-in diarization; ~$0.006/min class; 16K ctx, up to 2K out tokens). No self-host infra, no HF token, but data leaves the server — fails the local tier.
  2. **pyannote.audio 3.1** (`pyannote/speaker-diarization-3.1`): best-accuracy open model (DER ~11–19%); gated on HF (must accept user conditions + HF token); mono 16 kHz input; returns RTTM annotations. Integrates into `workflow.py`/`extraction.py` as a post-transcription pass.
  3. **WhisperX** (bundles faster-whisper + wav2vec2 word alignment + pyannote diarization behind one pipeline; `--diarize --hf_token`): fastest end-to-end path to aligned, speaker-labeled segments, but pulls a heavier dependency set and wants a GPU (<8 GB for large-v2).
- **Why:** Speaker attribution is a top user pain point (in `research-findings.md` §1A.4 and multiple 2026 sources). Everything downstream — assignee extraction (`extraction.py` reads `assignee`), evidence review (`ReviewWorkspace.tsx` already renders a `speaker` field), approve/reject of notes — is dramatically better with real speaker labels.
- **Complexity:** Medium (API option low; pyannote/WhisperX medium — needs model downloads, HF token, GPU optional, and a mapping step to align diarization segments with Whisper word timestamps).
- **Sources:** pyannote 3.1 model card — https://huggingface.co/pyannote/speaker-diarization-3.1 (gating/16kHz/RTTM); brasscomparison DER — https://brasstranscripts.com/blog/speaker-diarization-models-comparison; WhisperX GitHub — https://github.com/m-bain/whisperx and Clore.ai guide (CLI with `--diarize --hf_token`) — https://docs.clore.ai/guides/audio-and-voice/whisperx; OpenAI diarize model — https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize and pricing — https://costgoat.com/pricing/openai-transcription.

### FC-4 — Privacy-first / compliance tier plumbing (local-only, no-bot)
- **What:** Make "Record in person" respect the mode already set in `MeetingSetup.tsx` (General / Healthcare / Legal). Healthcare & Legal already force `review_required=True` and `phi_redaction=True` via `resolve_processing_policy()` (`services/workflow.py`) — but for a *local* tier we add: (a) `TRANSCRIPTION_BACKEND=local` to route audio to faster-whisper (never OpenAI), (b) explicit "audio stays in EU/Zürich / on your hardware" affordance in the setup `data-path` panel (it already lists "Processing region: Zürich / EU"), (c) BAA/retention already present (encrypted storage, retention days, BAA generation, audit logging — all implemented). 
- **Why:** Healthcare/legal/finance buyers require a no-third-party-bot flow. HIPAA itself doesn't mandate data residency, but local/on-prem processing removes the third-party breach vector entirely and is the practical gold standard for regulated use (multiple 2026 sources agree on BAA + data-residency + no-training-on-customer-data as the checkboxes). This is the strongest differentiated moat vs. cloud bots.
- **Complexity:** Medium (mostly wiring existing safeguards to the new local backend + surfacing guarantees in UI).
- **Sources:** Microsoft "Building HIPAA-Compliant Medical Transcription with Local AI" — https://techcommunity.microsoft.com/blog/azuredevcommunityblog/building-hipaa-compliant-medical-transcription-with-local-ai/4490777 (on-prem removes third-party risk); Aptible HIPAA data-residency — https://www.aptible.com/hipaa-ai-security/data-residency (HIPAA doesn't impose residency; end-to-end residency is above baseline); transcribe.health BAA/no-training warning signs — https://transcribe.health/en-us/blog/is-ai-transcription-hipaa-compliant.

### FC-5 — Deliver the in-person result into the ReviewWorkspace (evidence-first)
- **What:** Today `finalize()` returns a summary/actions overlay inside `LiveTranscriptionView`; it does not drop the user into `ReviewWorkspace.tsx` for evidence-linked approve/reject. Route the finalized in-person meeting through the existing review flow (`/meetings/{id}/review` PATCH, `review_status`, evidence with `speaker`/`timestamp`/`confidence`) so the live capture becomes an editable, reviewable, shareable record.
- **Why:** Completes the "reviewable evidence → approved notes → accountable actions → controlled shares" promise in the README (line 3) and the product's core value. In-person capture without a review workspace is just a transcript; with it, it's an accountable artifact for regulated meetings.
- **Complexity:** Medium (reuse existing `ReviewWorkspace` + `workspace.py` routes; add navigation from live → review and map diarized segments into evidence items).
- **Sources:** Repo: `frontend/src/workspace/ReviewWorkspace.tsx` (evidence with speaker/timestamp/confidence), `src/meeting_notes_ai/routes/workspace.py` (speaker field at line 239, review route). README value prop (repo). Market: `research-findings.md` §1A.8 (trustworthy evidence/approval) and §"What competition does poorly" (source-grounded human review is an open gap).

### FC-6 — Batch / long-recording handling for in-person sessions
- **What:** Add a chunked-upload vs true streaming decision for long in-person meetings. Current `ingest_chunk` re-transcribes the *accumulated* audio on every 1s chunk (O(n²) cost at scale) — fine for live preview but wasteful on a 60-min room. For in-person, offer: live partials (small timeslice) OR a "record then transcribe on finalize" batch path (send WebM chunks to `POST /meetings/live/upload` / `transcribe_file` at the end), plus the existing 25 MB `max_audio_size_mb` cap and `SUPPORTED_AUDIO_FORMATS` check as guardrails.
- **Why:** Cost/latency management at meeting length. Honest engineering note: the current accumulate-and-retranscribe loop is the single biggest scaling risk for ambient capture; a local faster-whisper backend makes incremental decode cheap, but a batch finalize path is simpler and cheaper for non-live rooms.
- **Complexity:** Medium.
- **Sources:** Repo: `src/meeting_notes_ai/services/live_transcription.py` (ingest_chunk accumulate pattern, lines 206–209; `_assemble_audio`), `routes/live_transcription.py` (`/upload`, 25 MB / format checks). MediaRecorder timeslice semantics (chunked vs single blob) — https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder and https://fsjs.dev/beyond-basics-mediastream-recording-api/ (timeslice latency/overhead tradeoff).

---

## 3. Implementation Hints

- **MediaRecorder capture (already built, keep it).** `useLiveSession.ts` already picks `audio/webm;codecs=opus` when supported, falls back to `audio/webm`, slices on `recorder.start(1000)`, and streams binary WebM chunks over a JWT WebSocket; backend detects the WebM/EBML magic (`\x1a\x45\xdf\xa3`) and treats frames as `WEBM_OPUS`. Reference this exact pattern; don't rewrite it. Cross-browser caveat: **Safari often prefers `audio/mp4` over WebM/Opus** and MediaRecorder can't emit raw PCM — so for a 1:1 local tier that wants raw PCM, use the **Web Audio API + AudioWorklet** path (MediaStreamAudioSourceNode → AudioWorkletNode) instead of MediaRecorder. `_pcm16_to_wav` in `live_transcription.py` already frames 16 kHz PCM for Whisper, so that path is supported server-side.
- **Local STT.** Add `faster-whisper` as an optional dependency (not default) and a `WhisperTranscriber` protocol with two implementations (OpenAI remote, local CTranslate2). Keep the existing `TranscriptionService` interface (`transcribe(audio_bytes, filename, language) -> TranscriptionResult`) so `live_transcription.py` / `finalize` / `transcribe_file` are untouched. Use `compute_type="int8"` for CPU and model tiers `small`→`large-v3-turbo` for the accuracy/latency tradeoff. WAV is the safest interchange container for local STT.
- **Diarization alignment.** Both pyannote and WhisperX output speaker segments separately from Whisper word timestamps; you must **align**: assign each transcript segment's `[start, end]` to the diarization turn it overlaps most (max-overlap mapping). Feed `speaker` into `TranscriptSegment` and let `extraction.py` pass it into action-item `assignee` and into `ReviewWorkspace` evidence (`speaker` already a field). Note pyannote needs a **gated HF token** (user must accept the model conditions) and mono 16 kHz input — downmix in the service.
- **Privacy tier.** Model the backend choice as `TRANSCRIPTION_BACKEND=local|openai` + `WHISPER_MODEL` (e.g. `local:large-v3-turbo`). When Healthcare/Legal mode is set and backend=local, assert no audio is sent to OpenAI. Reuse `resolve_processing_policy()` for the `phi_redaction`/`review_required` flags. Keep retention + BAA + audit + encrypted-storage as-is (already implemented).
- **Routings.** `MeetingSetup.tsx`: make `Record in person` (index 3) set `isAvailable` true and call the same `onLive` (or a new `onInPerson`) that lands in `LiveWorkspace`. After `finalize`, navigate to `ReviewWorkspace` with the meeting id instead of stopping in the live overlay. Do NOT build a new route/backend for the happy path — the `workspace.py` `/meetings/{id}/review` PATCH already persists review status.
- **Testing.** Add `tests/test_transcription_local.py` (fake faster-whisper) + extend `tests/test_live_transcription.py` for diarized segments; run in the repo venv (`.venv/bin/python -m pytest`) per repo conventions.

---

## 4. Risks

- **GPU/CPU cost of local STT + diarization.** faster-whisper large/turbo + pyannote need meaningful CPU/GPU; on a small self-hosted box this can bottleneck finalize latency. Mitigation: model-size presets, `int8`, optional GPU, and the batch-finalize path for long rooms. (High, manageable.)
- **pyannote licensing/gating.** Model is gated; commercial use requires accepting the HF user terms (it's community MIT-licensed code wrapping a gated model — check the license). A non-gated fallback is OpenAI `gpt-4o-transcribe-diarize` (cloud) at slightly higher cost. (Medium.)
- **Diarization accuracy in live rooms.** Multiple 2026 sources report diarization failing on high-quality non-overlapping multi-speaker audio (both pyannote 3.1 and 4.0). Set expectations: diarization is best-effort post-processing; provide speaker-label *correction* in the review workspace, not a guarantee. (Medium-high.)
- **Accumulate-and-re-transcribe loop.** `ingest_chunk` re-runs the whole accumulated audio per chunk — O(n²) for long meetings; could spike latency/API cost. Route long/in-person sessions to batch finalize or local backend. (Medium.)
- **Browser fragment compatibility.** Multi-file WebM chunk assembly is fragile (chunks aren't independent fragments); Safari/WebM-unsupported browsers need `audio/mp4` or the AudioWorklet/PCM path. (Medium.)
- **"Record in person" message/consent.** Consent and local-processing claims in the UI must match reality (the setup panel already claims "Encrypted processing" / "Zürich / EU"); a local backend keeps that honest for the regulated tier. (Low-Medium, reputational.)

---

## 5. Source Links

**Browser mic capture / MediaRecorder**
- MediaRecorder (timeslice, dataavailable) — https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder
- Advanced MediaRecorder techniques — https://fsjs.dev/beyond-basics-mediastream-recording-api/
- Web Audio API raw PCM / AudioWorklet — https://stackoverflow.com/questions/51687308/how-to-use-web-audio-api-to-get-raw-pcm-audio (MediaRecorder can't emit raw PCM), https://picovoice.ai/blog/how-to-record-audio-from-a-web-browser/
- Safari vs Chrome codec (mp4 vs WebM/Opus) — https://blog.openreplay.com/record-audio-browser-web-audio-api/

**Whisper STT (API vs local)**
- OpenAI Speech-to-Text guide (whisper-1 vs gpt-4o-transcribe[-diarize]; 25 MB cap) — https://platform.openai.com/docs/guides/speech-to-text
- faster-whisper vs whisper.cpp vs OpenAI — https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/
- Local vs Cloud STT tradeoffs — https://openwhispr.com/blog/local-vs-cloud-transcription
- AssemblyAI Whisper developer guide — https://www.assemblyai.com/blog/openai-whisper-developers-choosing-api-local-server-side-transcription

**Diarization**
- pyannote/speaker-diarization-3.1 model card (gated, 16 kHz, RTTM) — https://huggingface.co/pyannote/speaker-diarization-3.1
- Diarization model comparison — https://brasstranscripts.com/blog/speaker-diarization-models-comparison
- WhisperX (faster-whisper + alignment + pyannote) — https://github.com/m-bain/whisperx ; CLI guide — https://docs.clore.ai/guides/audio-and-voice/whisperx
- OpenAI gpt-4o-transcribe-diarize — https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize ; pricing — https://costgoat.com/pricing/openai-transcription

**Privacy / compliance**
- Microsoft: HIPAA-compliant local transcription — https://techcommunity.microsoft.com/blog/azuredevcommunityblog/building-hipaa-compliant-medical-transcription-with-local-ai/4490777
- Aptible: data residency for healthcare AI — https://www.aptible.com/hipaa-ai-security/data-residency
- transcribe.health: HIPAA warning signs (BAA, no model training) — https://transcribe.health/en-us/blog/is-ai-transcription-hipaa-compliant

**Competitive scan**
- Meetily (bot-free, local, Rust) — https://github.com/Zackriya-Solutions/meetily , https://meetily.ai/
- OpenWhispr (local dictation / Granola alternative) — https://openwhispr.com/ and https://openwhispr.com/compare/granola
- Self-hosted meeting transcription tools — https://meetily.ai/blog/best-self-hosted-meeting-transcription-tools-2026

**Repo-internal (ground truth)**
- `frontend/src/workspace/MeetingSetup.tsx`, `frontend/src/live/useLiveSession.ts`, `frontend/src/live/LiveTranscriptionView.tsx`, `frontend/src/workspace/ReviewWorkspace.tsx`
- `src/meeting_notes_ai/routes/live_transcription.py`, `services/live_transcription.py`, `services/transcription.py`, `services/workflow.py`, `services/extraction.py`, `config.py`
- `research-findings.md` (41-source market research, 2026-08-05)
