# Analysis Brief — In-Person Bot-Free Recording (Ambient Capture + Local Whisper STT)

**Feature:** "Record in person" — ambient device-mic capture → local/API Whisper transcription → speaker diarization → privacy-first review-workspace integration.
**Repo:** `/home/zoltan/meeting-notes-ai` (branch `master`; task bodies say `main` — the repo default is `master`).
**Version:** `pyproject.toml` reports `1.2.0`; `CHANGELOG.md` head is `1.3.0` (2026-08-10) — the feature shipped there.
**Analyst:** kanban t_e7e32231 (re-run of t_754e14fb analysis; selector cron re-promoted idea meeting-notes-ai-cfd5e4).
**Research source:** `analysis/research-brief.md` (read in full) + direct repo inspection of every file cited below.
**HEAD at analysis time:** `546f590` (== `origin/master`, clean tree).

---

## 0. Executive Summary — READ THIS FIRST

The feature is **already implemented and merged** at HEAD `546f590` ("feat: In-Person Bot-Free Recording — ambient capture, batch transcription, diarization, review integration"), with its pre-dev RED suite in `552ef57` and the original spec in `4aefa7f`. The selector cron re-promoted the same idea, so this cycle's downstream cards (pre-tester ×2 → developer ×2 → tech-lead review) execute against **already-green code**.

What this means for every downstream worker:

1. **Do NOT greenfield.** The modules the pre-tester cards describe already exist:
   - Ambient audio capture = the existing `POST /api/v1/meetings/live/upload` + `POST /api/v1/meetings/live/start` endpoints and the `LiveTranscriptionService` streaming/WS path — there is NO separate `src/audio_capture.py`. The decomposer's generic examples (`src/audio_capture.py`, `capture_audio(duration: float) -> bytes`) do **not** match this repo. The brief is authoritative.
   - Local Whisper STT = `src/meeting_notes_ai/services/local_transcription.py::LocalWhisperTranscriptionService` (faster-whisper, `TRANSCRIPTION_BACKEND=local`). There is NO `src/whisper_stt.py` / bare `transcribe(audio: bytes) -> str`.
2. **The 9 failing tests are broken TESTS, not broken code.** Baseline at HEAD: `tests/test_ambient_recording.py test_batch_transcription.py test_diarization.py test_review_integration.py` → **39 passed / 9 failed**, and all 9 failures reproduce on the pristine commit (verified below). The implementation commit note says exactly the same: "39 pass / 9 fail (all 9 pre-existing RED-suite test bugs confirmed identical on clean commit: 5x _align dict attr error, 3x asyncio.run-in-loop, 1x fixture logic bug)". A pre-tester whose job is "write tests that RED" must instead **repair these 9 to GREEN** (they are the feature's own tests, so this is not scope creep) or, if explicitly out of scope, document them — never re-report them as new failures.
3. **Repo conventions:** `.venv/bin/python -m pytest` (never bare pytest), `.venv/bin/ruff`, deps pinned in `pyproject.toml` (faster-whisper/pyannote/torch are already there, lines 33-35). No frontend JS test framework exists.

---

## 1. Current State Assessment (post-implementation ground truth)

Each finding grounded in a concrete file:line at HEAD 546f590.

### 1.1 Ambient audio capture — ALREADY IMPLEMENTED (P0)
- `src/meeting_notes_ai/routes/live_transcription.py`:
  - `get_live_service()` (`:56-84`) — FastAPI dependency; selects backend from `settings.transcription_backend`: `"local"` → `LocalWhisperTranscriptionService(model=settings.whisper_model if != "whisper-1" else None)` (`:68-71`), else `TranscriptionService(api_key=..., model=...)` (`:73-75`); wraps both in `LiveTranscriptionService(transcription_service=..., extraction_service=..., diarizer=...)`. **This is the single backend-switch point.**
  - `POST /api/v1/meetings/live/upload` (`:225-263`) — REST capture path: `await file.read()`; **empty → 400** "The uploaded audio file is empty."; content-type not in `settings.SUPPORTED_AUDIO_FORMATS` (`config.py:113-117`: wav/mpeg/mp4/webm) → **415**; `len(contents) > max_audio_size_mb*MiB` → **413**; `LiveRateLimitExceeded` → **429**. Calls `service.transcribe_file(contents, file.filename or "recording.wav", user_id=user["user_id"])`. Response model `LiveTranscriptResponse`, status 200.
  - `POST /api/v1/meetings/live/start` — provisions a draft `Meeting` row the WS session attaches to.
  - WS `""` route — JWT (token query param), binary WebM chunks, partial frames, `finalize` control frame.
- `src/meeting_notes_ai/services/live_transcription.py`:
  - `transcribe_file(audio_bytes, filename, *, user_id, team_id=None, meeting_id=None, mode="general", language=None) -> LiveTranscriptResponse` (`:308-360`) — rate-limit check; **empty-buffer guard returns empty `LiveTranscriptResponse`** (`:327-337`, "An empty buffer is not a valid ambient capture: never invent content"); transcribe → `_maybe_diarize` → extract (`mode` threaded from the call, `MeetingMode` fallback GENERAL) → `_persist_meeting(..., create_if_missing=True)`.
  - `finalize(...)` (`:252-300`) — WS path; `_meeting_mode` resolves the meeting's `mode` from its DB row (`:524-545`), so regulated meetings persist as regulated (P0-4 privacy fix).
  - `_persist_meeting` (`:418-496`) — writes transcript+summary into `metadata_json`, applies `resolve_processing_policy(mode, None)` (`services/workflow.py:21-35`) so Healthcare→`review_status="needs_review"`+redaction, Legal→`needs_review`; unknown modes keep `"ready"`.
  - `_sync_workspace_meeting` (`:545+`) — best-effort sync of finalized meetings into the workspace: creates/updates the workspace `Meeting` with `evidence[]` items `{timestamp, speaker: seg.speaker or "Speaker 1", text, confidence: 0.0}` (`:564-577`), fallback single evidence from `transcript[:500]` when no segments.
  - `_maybe_diarize(result, audio)` (`:500-523`) — runs the diarizer in a worker thread (`asyncio.to_thread(lambda: asyncio.run(diarizer.diarize(audio, sample_rate=16_000)))`) so the event loop never blocks; any exception → segments keep `speaker=None` (best-effort by design, `# pragma: no cover`).
- Frontend `frontend/src/workspace/MeetingSetup.tsx` — the 4th card **is unblocked**: `isAvailable = capture === 'Record live' || capture === 'Upload recording' || capture === 'Record in person'` (`:8`); the disabled label is gone (`:10` renders `Continue with ${capture}`). `onClick`: `'Record live' → onLive()`, anything else → `setConfigured(true)` — 'Record in person' now proceeds to configuration. (The `onLive` route for in-person-vs-live distinction is a possible P2 nicety, not required.)

### 1.2 Local Whisper STT — ALREADY IMPLEMENTED (P0)
- `src/meeting_notes_ai/services/local_transcription.py` (95 lines) — `class LocalWhisperTranscriptionService`:
  - `__init__(self, whisper: Any | None = None, model: str | None = None, compute_type: str = "int8")` (`:40-51`) — `model` defaults to env `WHISPER_MODEL` ("small"), `compute_type` to env `WHISPER_COMPUTE_TYPE` ("int8"); `_whisper` injectable (duck-typed faster-whisper).
  - `_build_model(self)` (`:53-59`) — lazy `from faster_whisper import WhisperModel; WhisperModel(self.model, compute_type=self.compute_type)`; cached on `self._whisper`.
  - `async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None) -> TranscriptionResult` (`:61-95`) — `segments, info = model.transcribe(audio_bytes, language=language)`; maps `(start, end, text)` tuples → `TranscriptSegment(start=float(start), end=float(end), text=str(text))`; `TranscriptionResult(text=" ".join(text_parts).strip(), language=getattr(info,"language", language or ""), duration_seconds=float(getattr(info,"duration",0.0) or 0.0), segments=parsed)`.
  - **Privacy guarantee:** never imports/constructs the `openai` package (`:16-18` docstring, `self._client: Any | None = None  # local backend never holds an OpenAI client` at `:51`).
- `src/meeting_notes_ai/config.py`:
  - `transcription_backend` (`:17-19`) — dataclass field `default="openai"`, env `TRANSCRIPTION_BACKEND` honored in `__post_init__` (`:108-115`).
  - `diarization_enabled: int` (`:20-22`) — `int(os.getenv("DIARIZATION", "0"))` (off by default).
  - `hf_token` (`:23`) — `os.getenv("HF_TOKEN", "")`.
  - `whisper_model` (`:16`) — `os.getenv("WHISPER_MODEL", "whisper-1")` (OpenAI default; local path uses it when != "whisper-1").
- `src/meeting_notes_ai/models.py:78` — `TranscriptSegment.speaker: str | None = None` (P0-2, backwards compatible).
- `pyproject.toml:33-35` — `faster-whisper>=1.0.0`, `pyannote.audio>=3.1.0`, `torch>=2.2.0` pinned (P0-3/P1-1 deps).
- **Known asymmetry (document, don't fix unless asked):** `get_live_service()` honors `TRANSCRIPTION_BACKEND` but `routes/meetings.py::_build_services` (`:24-39`) hard-codes `TranscriptionService(api_key=...)`. The REST `/api/v1/meetings` upload path is therefore always OpenAI-backed regardless of env. In-person/ambient capture uses the live routes, so the feature is unaffected — but a pre-tester asserting "TRANSCRIPTION_BACKEND=local makes ALL transcription local" would be wrong; scope the assertion to the live/ambient path.

### 1.3 Diarization — ALREADY IMPLEMENTED (P1)
- `src/meeting_notes_ai/services/diarization.py` (149 lines):
  - `Turn = tuple[float, float, str]` (`:32`).
  - `def assign_speakers(segments: Sequence[dict[str, Any] | TranscriptSegment], turns: Iterable[Turn]) -> dict[int, str]` (`:37-72`) — max-overlap alignment; handles BOTH dicts (`seg["start"]`) and models (`seg.start`) (`:61-62`); ties → earliest turn; zero-length boundary touch excluded (`_OVERLAP_EPSILON = 1e-9`, `:34`); segments with no positive overlap omitted.
  - `def apply_diarization(segments: list[TranscriptSegment], turns: Iterable[Turn]) -> list[TranscriptSegment]` (`:75-94`) — mutates `speaker` in place AND returns the list.
  - `class SpeakerDiarizer` (`:97-149`): `__init__(self, backend: Any | None = None, hf_token: str | None = None)` (`:113-117`); `_build_pipeline()` lazy `Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=self._hf_token or None)` (`:119-127`); `async def diarize(self, audio_bytes: bytes, sample_rate: int) -> list[tuple[float, float, str]]` (`:129-149`) — `result.itertracks(yield_label=True)` → `(float(segment.start), float(segment.end), str(label))`.
- Wiring: `LiveTranscriptionService.__init__` accepts `diarizer`; `_maybe_diarize` (above) gates on `DIARIZATION=1` + `diarizer is not None`.

### 1.4 Test baseline (the numbers downstream workers need)
- Feature test files (all exist, committed in `552ef57`):
  - `tests/test_ambient_recording.py` (435 lines) — upload/start endpoints, 400/415/413/429 validation, happy-path persistence, `TranscriptSegment.speaker`, MeetingSetup 'Record in person' gate via source assertions (no JS framework exists).
  - `tests/test_batch_transcription.py` (459 lines) — Whisper payload/result contract with mocked API, `transcribe_file` batch shape, `TRANSCRIPTION_BACKEND=local` signature parity + `_FakeLocalWhisper` behavioral tests.
  - `tests/test_diarization.py` — P1-1 max-overlap alignment reference + production aligner contract; `DIARIZATION` gate off-by-default parity.
  - `tests/test_review_integration.py` — P0-4 finalize → workspace detail with `evidence[]`, mode threading (healthcare) + `review_status=needs_review`, no-OpenAI-call assert for local backend.
- **Baseline run (verified this cycle):** `.venv/bin/python -m pytest tests/test_ambient_recording.py tests/test_batch_transcription.py tests/test_diarization.py tests/test_review_integration.py -q` → **39 passed, 9 failed** (see §5 for the exact 9 and their fixes).
- `pytestmark = pytest.mark.quick` in test_diarization.py (`:32`) — the suite is marked; run with `-m "not slow"` aware commands if the repo's config distinguishes markers.
- The canonical AI-seam pattern lives in `tests/test_live_ui.py:25-50` (`_FakeTranscription`/`_FakeExtraction` duck-types) and `:159` (`app.dependency_overrides[get_live_service] = lambda: service`).

### 1.5 What is genuinely NOT done (candidates for P2 / next cycle)
- `routes/meetings.py::_build_services` does not honor `TRANSCRIPTION_BACKEND` (asymmetry above).
- `_maybe_diarize` swallows all diarization exceptions (documented best-effort; no metric/alert).
- No speaker-label correction UI in `ReviewWorkspace` (P2-3 from the original brief).
- No consent-state persistence for 'Record in person' into `ConsentStatus` (P2-4).
- No AudioWorklet/PCM capture path for Safari (P2-2); no dedicated chunked long-recording upload endpoint (P2-1).

---

## 2. Clustered Options (as decided; implementation matches)

The original analysis (t_754e14fb) clustered these decisions; the merged implementation confirms them:

| Cluster | Decision (chosen) | Status at HEAD |
|---|---|---|
| A — Capture path | **Reuse live WS + REST `/upload`**; no new protocol | ✅ `routes/live_transcription.py` WS + `/upload` |
| B — STT backend | **Dual backend** `TRANSCRIPTION_BACKEND=openai\|local`, shared `TranscriptionResult` | ✅ `local_transcription.py` + `get_live_service` switch |
| C — Diarization | **pyannote.audio 3.1**, `DIARIZATION=1` gate, max-overlap alignment | ✅ `diarization.py` + `_maybe_diarize` |
| D — Upload endpoint | **Reuse `POST /live/upload`** (400/415/413/429 contract) | ✅ unchanged |
| E — Privacy tier | `resolve_processing_policy` + mode threading + no-OpenAI in local tier | ✅ `_persist_meeting`/`_meeting_mode` |

Rejected options (unchanged from original brief): greenfield capture protocol, local-only STT default, WhisperX end-to-end, dedicated streaming upload endpoint for P0.

---

## 3. Chosen Tech Stack (post-implementation, with rationale)

| Concern | Choice (in repo) | Rationale (grounded) |
|---|---|---|
| Capture | `useLiveSession.ts` MediaRecorder → WS; REST `/upload` fallback | Already built + tested (`useLiveSession.ts:117-134`); in-person card unblocked (`MeetingSetup.tsx:8,10`) |
| STT (openai tier) | `TranscriptionService` (`services/transcription.py:26`) | Default `TRANSCRIPTION_BACKEND=openai`; unchanged behavior |
| STT (local tier) | `LocalWhisperTranscriptionService` (faster-whisper, `compute_type="int8"`, lazy import, injectable `whisper=`) | Privacy/compliance; interface parity `transcribe(audio_bytes, filename, language) -> TranscriptionResult`; never imports openai (`local_transcription.py:16-18,51`) |
| Backend switch | `settings.transcription_backend` + `get_live_service()` (`routes/live_transcription.py:56-84`) | Single construction point; env `TRANSCRIPTION_BACKEND` honored in `config.py:108-115` |
| Diarization | `SpeakerDiarizer` (pyannote 3.1, gated `HF_TOKEN`) + `assign_speakers`/`apply_diarization`; `DIARIZATION=1` gate | Best-effort; off-by-default parity; injectable `backend=` for tests |
| Upload endpoint | `POST /api/v1/meetings/live/upload` (`routes/live_transcription.py:225-263`) | 400/415/413/429 validation contract already defined and tested |
| Evidence/review | `_sync_workspace_meeting` + `workspace.py` routes | Evidence items carry `speaker`/`timestamp`/`text`/`confidence`; `review_status` from `resolve_processing_policy` |
| Privacy | `workflow.py:21-35` policy + mode threading (`_meeting_mode`, `transcribe_file(mode=)`) | Healthcare/Legal → `needs_review`; local tier never calls OpenAI |
| Runtime deps | `faster-whisper>=1.0.0`, `pyannote.audio>=3.1.0`, `torch>=2.2.0` (`pyproject.toml:33-35`) | Pinned per repo convention, not pip-only |

---

## 4. Prioritized Task List (P0 / P1 / P2) — post-implementation specs

The two pre-tester cards (t_bb3039fd ambient capture, t_9a657d60 local Whisper) consume the P0 specs below. **"Already implemented" is not "nothing to do"**: the spec defines the contract, the exact paths/signatures, and the baseline; the deliverable is the pre-tester test file per the contract (and repair of the 9 known test bugs if the card scope allows, see §5).

### P0-A — Ambient audio capture contract (pre-tester t_bb3039fd → developer t_ea19e2a9)

- **Module (repo-truth path):** `src/meeting_notes_ai/services/live_transcription.py` (`LiveTranscriptionService`), `src/meeting_notes_ai/routes/live_transcription.py` (`/upload`, `/start`, WS). **There is no `src/audio_capture.py`; the decomposer's `capture_audio(duration) -> bytes` example does NOT apply.** If a test file must exercise a "capture" function, the correct seam is the endpoint contract + `transcribe_file` — or, for a pure unit, `LiveTranscriptionService.transcribe_file`.
- **Expected behavior:** POST a valid audio file → `LiveTranscriptResponse` (200) with transcript/summary/duration; empty file → 400; unsupported content-type → 415; >25 MB → 413; rate-limited → 429; empty buffer never fabricates a transcript (`transcribe_file` returns empty `LiveTranscriptResponse`).
- **Interfaces (exact):**
  - `POST /api/v1/meetings/live/upload` — multipart `file: UploadFile`; `user` via `Depends(get_current_user)`; `db` via `Depends(get_db_session)`; `service` via `Depends(get_live_service)`; returns `LiveTranscriptResponse`.
  - `async def transcribe_file(self, audio_bytes: bytes, filename: str, *, user_id: str, team_id: str | None = None, meeting_id: str | None = None, mode: str = "general", language: str | None = None) -> LiveTranscriptResponse` (`services/live_transcription.py:308`).
  - `async def create_session(self, ..., hipaa: bool = False, ...)` (`:161-186`) — used by `/start`.
  - `settings.SUPPORTED_AUDIO_FORMATS` = `{"audio/wav","audio/mpeg","audio/mp4","audio/webm"}` (`config.py:113-117`); `settings.max_audio_size_mb` (default 25).
- **Dependencies:** existing; none new.
- **Test file to create (exact path):** `tests/test_audio_capture.py` — see §5 for the contract; the existing `tests/test_ambient_recording.py` is the prior implementation of that contract and must be reconciled (repair the 9 or reuse its 39 passing tests; do not duplicate blindly).
- **Commit message format:** `test(pre-dev): ambient audio capture contract — <what> (RED|GREEN)` / `feat(audio-capture): <what>`.
- **Acceptance criteria (concrete commands):**
  - `.venv/bin/python -m pytest tests/test_audio_capture.py -q` → all pass (or interface-pass/behavioral-RED split per pre-tester convention, with the 9 known bugs repaired or documented).
  - `.venv/bin/ruff check tests/test_audio_capture.py` → clean.
  - Validation assertions present: empty→400, content-type→415, size→413, rate-limit→429 (mirror `tests/test_ambient_recording.py`).

### P0-B — Local Whisper STT contract (pre-tester t_9a657d60 → developer t_1da6d35f)

- **Module (repo-truth path):** `src/meeting_notes_ai/services/local_transcription.py` (`LocalWhisperTranscriptionService`). **There is no `src/whisper_stt.py` / bare `transcribe(audio) -> str`; the decomposer's example does NOT apply.** Wiring: `routes/live_transcription.py::get_live_service` (`:56-84`), `config.py:17-19` + `:108-115`.
- **Expected behavior:** with `TRANSCRIPTION_BACKEND=local`, transcription is served by faster-whisper locally (no network, no OpenAI import); with `openai` (default), behavior unchanged. Same signature/return shape as `TranscriptionService.transcribe`.
- **Interfaces (exact):**
  - `class LocalWhisperTranscriptionService` with:
    - `def __init__(self, whisper: Any | None = None, model: str | None = None, compute_type: str = "int8") -> None`
    - `async def transcribe(self, audio_bytes: bytes, filename: str, language: str | None = None) -> TranscriptionResult`
  - Injectable duck-typed whisper: `model.transcribe(audio_bytes, language=...)` returning `(segments_iterable_of_(start,end,text), info_with_.language/.duration)`.
  - `TRANSCRIPTION_BACKEND` env (`config.py:17-19`, override at `:108-115`); `WHISPER_MODEL` (default "whisper-1" for OpenAI, "small" via local fallback); `WHISPER_COMPUTE_TYPE` (default "int8").
  - `models.py:78` — `TranscriptSegment.speaker: str | None = None`.
- **Dependencies:** `faster-whisper>=1.0.0` (`pyproject.toml:33`, already pinned).
- **Test file to create (exact path):** `tests/test_whisper_stt.py` — see §5; reconcile with existing `tests/test_batch_transcription.py` (which already covers backend parity + `_FakeLocalWhisper`).
- **Commit message format:** `test(pre-dev): local whisper STT contract — <what> (RED|GREEN)` / `feat(whisper-stt): <what>`.
- **Acceptance criteria (concrete commands):**
  - `.venv/bin/python -m pytest tests/test_whisper_stt.py -q` → per contract (see §5 baseline; the no-OpenAI test at `test_review_integration.py:449` has a known data bug — fix the fake's fixture text, not the production assert).
  - `.venv/bin/ruff check tests/test_whisper_stt.py` → clean.
  - Interface tests pass immediately against HEAD (class exists, signature exact, returns `TranscriptionResult`); behavioral tests assert: local backend produces text/segments from `_FakeLocalWhisper`, empty/invalid audio returns the empty result (not an exception) via `transcribe_file`, and the local tier never imports `openai` (`assert "openai" not in sys.modules`-style guard is valid ONLY if it does not trip on the `"openai"` string inside fixture text).

### P1 — Already implemented; keep as regression scope
- P1-1 diarization: `services/diarization.py` (`assign_speakers`, `apply_diarization`, `SpeakerDiarizer`) — covered by `tests/test_diarization.py` (5 known test-helper bugs to repair, §5).
- P1-2 batch finalize: `transcribe_file` already is the batch path.
- P1-3 privacy affordance: data-path panel claims already honest (local tier never calls OpenAI).

### P2 — Not implemented (next-cycle candidates; do NOT build now)
- P2-1 dedicated long-recording streaming upload endpoint; P2-2 AudioWorklet/PCM capture; P2-3 speaker-label correction UI; P2-4 consent-state persistence; plus the `_build_services` backend-switch asymmetry (§1.5). Each would be its own spec'd cycle.

---

## 5. Pre-tester handoff: the 9 known failing tests + repair guidance

Baseline: `39 passed / 9 failed` across the 4 feature files at HEAD 546f590. All 9 are **test-code defects**, reproduced identically on the pristine commit — the production code is green. The implementer documented them; this cycle's pre-tester must repair them (they are the feature's own tests) or explicitly document them as by-design RED — NEVER report them as new regressions.

| # | Test | Failure | Root cause | Fix |
|---|---|---|---|---|
| 1-5 | `tests/test_diarization.py::TestMaxOverlapAlignment::test_segment_fully_inside_turn_gets_that_speaker` / `test_overlapping_turns_choose_max_overlap` / `test_boundary_touch_does_not_count_as_overlap` / `test_segment_overlapping_no_turn_keeps_none` / `test_multiple_segments_are_independent` | `AttributeError: 'dict' object has no attribute 'end'` (`test_diarization.py:53`) | The reference `_align` helper accesses `seg.end`/`seg.start` but the test cases pass plain dicts `{"start":…, "end":…}`; production `assign_speakers` correctly handles both dicts and models (`diarization.py:61-62`) | In `_align`, use `seg["end"]`/`seg["start"]` (or `getattr(seg, "end", seg["end"])`) — mirror the production dual-access |
| 6-8 | `tests/test_review_integration.py::TestFinalizeModeThreading::test_finalize_healthcare_review_status_needs_review`, `test_finalize_persists_healthcare_mode`; `tests/test_batch_transcription.py::TestBatchTranscribeFile::test_transcribe_file_mode_threaded` | `RuntimeError: asyncio.run() cannot be called from a running event loop` (`runners.py:186`) | Test fixtures call `asyncio.run(...)` (e.g. `test_review_integration.py:90,109,136`, `test_batch_transcription.py:105,124`) inside `@pytest.mark.asyncio` tests — a running loop already exists | Replace `asyncio.run(x())` with `await x()` in async tests/fixtures |
| 9 | `tests/test_review_integration.py::TestNoOpenAICallLocalBackend::test_local_transcribe_does_not_import_openai_call` | `AssertionError: assert 'openai' not in 'no openai involved'` (`:449`) | The fake local whisper's fixture text is literally `"no openai involved"`; the test asserts the transcript text does not contain the substring "openai" — a fixture-data bug, not a production leak | Change the fake's fixture text to e.g. `"transcribed locally without cloud"` (keep the meaningful assertion on `calls == ["local_backend_called"]` and on no OpenAI client construction) |

**Contract for new test files (per pre-tester cards):**
- `tests/test_audio_capture.py` — interface tests (route registration, `transcribe_file` signature, `SUPPORTED_AUDIO_FORMATS`, empty-buffer behavior) + behavioral (200/400/415/413/429 via TestClient with `app.dependency_overrides[get_live_service]`, per `test_live_ui.py:159`). Reuse/extend `tests/test_ambient_recording.py` rather than duplicating.
- `tests/test_whisper_stt.py` — interface (class/signature/`TRANSCRIPTION_BACKEND` config) + behavioral with `_FakeLocalWhisper` (`model.transcribe` → `(segments, info)`), no-OpenAI-import assertion, empty-input handling.
- **No inverse stub-guards** (`pytest.raises(NotImplementedError)` on feature methods) — the existing suite already follows this; keep it.
- **No frontend JS tests** — no framework exists (`frontend/package.json:7-23`); MeetingSetup card validated via source assertions (as `test_ambient_recording.py` does) or backend UI-glue.
- Always `.venv/bin/python -m pytest`; new runtime deps → pin in `pyproject.toml` (none needed here).

---

## 6. Dependency Graph (as-built)

```
P0-A ambient capture (endpoints + transcribe_file)   [no new deps; reuses live pipeline]
P0-B local Whisper (LocalWhisperTranscriptionService)<- models.TranscriptSegment, config env
P0-2 speaker field (models.py:78)                    [already merged, feeds both]
P0-4 privacy/mode threading (finalize/transcribe_file)[uses workflow.resolve_processing_policy]
P1-1 diarization (diarization.py)                    <- P0-2, P0-B; DIARIZATION=1 gate
Review/evidence (_sync_workspace_meeting)            <- P0-4, P1-1
```
All P0/P1 nodes are implemented at HEAD 546f590; the active cycle's work is the test contract (P0-A/P0-B cards) + tech-lead verification (t_0399a60a).

---

## 7. Acceptance Criteria Matrix (feature AC → implementation evidence)

| Feature AC (task body) | Satisfied by (at HEAD) | Verify with |
|---|---|---|
| 1. Device mic capture via 'Record in person' card | `MeetingSetup.tsx:8,10` unblocked + `useLiveSession.ts` WS capture | `.venv/bin/python -m pytest tests/test_ambient_recording.py -q` (source-assert gate) |
| 2. Batch transcription via existing Whisper integration | `transcribe_file` (`live_transcription.py:308`) + `POST /live/upload` | `tests/test_batch_transcription.py` (39-base), `tests/test_whisper_stt.py` (new) |
| 3. Speaker diarization | `diarization.py` + `_maybe_diarize` (`DIARIZATION=1`) | `tests/test_diarization.py` (after 5-helper repair) |
| 4. Review integration (evidence-linked) | `_sync_workspace_meeting` + `workspace.py` detail/review routes | `tests/test_review_integration.py` (after 3-4 repair) |
| 5. Privacy-first (local backend, no bot) | `local_transcription.py` (no OpenAI import) + `resolve_processing_policy` | no-OpenAI assertions + `review_status=needs_review` tests |
| 6. UI state: preview→active, status+duration, →review | `LiveStatus` in `useLiveSession.ts`/`LiveTranscriptionView.tsx` | existing live UI glue tests |
| 7. Error handling (mic denied, too short, Whisper API, network) | `useLiveSession.ts:187-191`, `routes/live_transcription.py:225-263` | validation tests 400/415/413/429 |
| 8. TDD tests | `552ef57` suite (39 green + 9 repaired) + new card test files | full targeted run |

**Final gate command for the tech-lead review (t_0399a60a):**
```
cd /home/zoltan/meeting-notes-ai && \
  .venv/bin/python -m pytest tests/test_audio_capture.py tests/test_whisper_stt.py \
    tests/test_ambient_recording.py tests/test_batch_transcription.py \
    tests/test_diarization.py tests/test_review_integration.py -q && \
  .venv/bin/ruff check src/meeting_notes_ai/services/local_transcription.py \
    src/meeting_notes_ai/services/diarization.py tests/test_audio_capture.py \
    tests/test_whisper_stt.py
```
Expected end-state: **0 failed** (all 9 repaired), or the repair explicitly documented as out-of-scope with the 9 failures classified by §5 root cause.

*End of brief. Grounded entirely in `/home/zoltan/meeting-notes-ai` at HEAD 546f590 (file:line cited inline), `analysis/research-brief.md`, and the implementation commits 4aefa7f / 552ef57 / 546f590.*
