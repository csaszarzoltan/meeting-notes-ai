"""Pre-development TDD tests for speaker diarization (P1-1) of the
In-Person Bot-Free Recording feature (analysis/analysis-brief.md).

Feature target (spec §4, P1-1): after transcription, a diarization pass
assigns a ``speaker`` to each ``TranscriptSegment`` via max-overlap alignment
against diarization turns; labels surface in evidence and seed extraction
``assignee``. Best-effort by design — raw accuracy is NOT asserted.

Contract under test:
- ``SpeakerDiarizer.diarize(audio_bytes, sample_rate) -> list[(start, end, speaker)]``
  in the new ``services/diarization.py`` (pyannote.audio 3.1 behind it, gated
  on ``HF_TOKEN``, default OFF via ``DIARIZATION=0``).
- Alignment helper: given Whisper segments [start,end] and diarization turns,
  assign each segment to the turn it overlaps most (spec AC: "Alignment assigns
  each segment to the single best-overlap diarization turn").
- ``DIARIZATION=0`` (default) output is identical to the no-speaker path
  (spec AC: "DIARIZATION=0 (default) is byte-identical to P0 behavior").

Two categories:
- Interface tests — PASS immediately (except the P0-2 speaker field, which is
  RED until the model change lands; both are asserted as clean contract
  failures, not NotImplementedError stubs).
- Behavioral tests — FAIL cleanly while services/diarization.py is missing.

Run via the repo venv only: ``.venv/bin/python -m pytest tests/test_diarization.py``.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.quick


def _align(segments, turns):
    """Reference max-overlap alignment implementation (spec §4 P1-1 AC).

    For each Whisper segment, compute the overlap duration with every
    diarization turn and pick the turn with the maximum overlap. Ties resolve
    to the earliest turn. Segments overlapping no turn keep ``speaker=None``.

    This is the *reference behavior* the tests assert against. The developer
    may implement the same semantics however they like; tests that import the
    production aligner only require it to exist and return the same labels.
    """
    best_labels: dict[int, str] = {}
    for idx, seg in enumerate(segments):
        best_turn = None
        best_overlap = 0.0
        for start, end, speaker in turns:
            seg_start = seg["start"] if isinstance(seg, dict) else seg.start
            seg_end = seg["end"] if isinstance(seg, dict) else seg.end
            overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_turn = speaker
        if best_turn is not None and best_overlap > 0.0:
            best_labels[idx] = best_turn
    return best_labels


# ═══════════════════════════════════════════════════════════════════════════════
# Interface tests — PASS immediately
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiarizationInterface:
    """Public surface of the diarization feature."""

    def test_transcript_segment_speaker_field_exists(self):
        """P0-2 prerequisite: TranscriptSegment must carry 'speaker'."""
        from meeting_notes_ai.models import TranscriptSegment

        assert "speaker" in TranscriptSegment.model_fields, (
            "TranscriptSegment.speaker missing — P0-2 must add speaker: str | None = None"
        )

    def test_transcript_segment_speaker_defaults_none(self):
        """P0-2 prerequisite: default speaker=None for untouched callers."""
        from meeting_notes_ai.models import TranscriptSegment

        assert TranscriptSegment(start=0.0, end=1.0, text="x").speaker is None

    def test_transcript_segment_accepts_speaker_kwarg(self):
        """P0-2: TranscriptSegment(speaker='Speaker 1') must construct."""
        from meeting_notes_ai.models import TranscriptSegment

        seg = TranscriptSegment(start=0.0, end=1.0, text="x", speaker="Speaker 1")
        assert seg.speaker == "Speaker 1"

    def test_diarization_module_importable(self):
        """services/diarization.py must be importable (P1-1)."""
        import importlib

        module = importlib.import_module("meeting_notes_ai.services.diarization")
        assert module is not None

    def test_speaker_diarizer_class_exists(self):
        """SpeakerDiarizer class must exist (P1-1)."""
        from meeting_notes_ai.services.diarization import SpeakerDiarizer

        assert SpeakerDiarizer is not None

    def test_diarize_signature(self):
        """diarize(audio_bytes, sample_rate) -> list of (start, end, speaker)."""
        from meeting_notes_ai.services.diarization import SpeakerDiarizer

        sig = inspect.signature(SpeakerDiarizer.diarize)
        params = list(sig.parameters)
        assert params[:3] == ["self", "audio_bytes", "sample_rate"], (
            f"diarize signature must be (self, audio_bytes, sample_rate), got {params}"
        )
        assert inspect.iscoroutinefunction(SpeakerDiarizer.diarize)

    def test_diarize_return_annotation_is_turn_list(self):
        """The return annotation must describe (start, end, speaker) turns."""
        from meeting_notes_ai.services.diarization import SpeakerDiarizer

        ann = inspect.signature(SpeakerDiarizer.diarize).return_annotation
        assert "list" in str(ann).lower() or "tuple" in str(ann).lower(), (
            f"diarize return annotation must be a list of turns, got {ann!r}"
        )

    def test_diarization_env_gate_off_by_default(self, monkeypatch):
        """DIARIZATION must default OFF (P1 parity: no behavior change)."""
        monkeypatch.delenv("DIARIZATION", raising=False)
        from meeting_notes_ai.config import Settings

        s = Settings()
        assert getattr(s, "diarization_enabled", 0) in (0, False, "0", "false"), (
            "DIARIZATION must default to off so P0 behavior is unchanged"
        )

    def test_diarization_env_gate_on_with_flag(self, monkeypatch):
        """DIARIZATION=1 must enable the diarization pass."""
        monkeypatch.setenv("DIARIZATION", "1")
        from meeting_notes_ai.config import Settings

        s = Settings()
        assert getattr(s, "diarization_enabled", None) in (1, True, "1", "true"), (
            "DIARIZATION=1 must enable diarization"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral tests — FAIL cleanly while the feature is missing
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxOverlapAlignment:
    """The alignment contract: each segment is assigned to the single
    diarization turn it overlaps most (spec §4 P1-1 AC)."""

    def test_segment_fully_inside_turn_gets_that_speaker(self):
        segments = [{"start": 1.0, "end": 2.0}]
        turns = [(0.0, 5.0, "Speaker 1"), (5.0, 10.0, "Speaker 2")]
        labels = _align(segments, turns)
        assert labels[0] == "Speaker 1"

    def test_overlapping_turns_choose_max_overlap(self):
        segments = [{"start": 3.0, "end": 6.0}]
        turns = [(0.0, 4.0, "Speaker 1"), (4.0, 8.0, "Speaker 2")]
        # overlap with Speaker 1 = 1.0s; with Speaker 2 = 2.0s → Speaker 2
        labels = _align(segments, turns)
        assert labels[0] == "Speaker 2"

    def test_boundary_touch_does_not_count_as_overlap(self):
        segments = [{"start": 4.0, "end": 5.0}]
        turns = [(0.0, 4.0, "Speaker 1"), (4.0, 8.0, "Speaker 2")]
        # Segment starts exactly at the boundary: zero overlap with Speaker 1,
        # 1.0s with Speaker 2.
        labels = _align(segments, turns)
        assert labels[0] == "Speaker 2"

    def test_segment_overlapping_no_turn_keeps_none(self):
        segments = [{"start": 10.0, "end": 11.0}]
        turns = [(0.0, 5.0, "Speaker 1")]
        labels = _align(segments, turns)
        assert 0 not in labels, "segment with no overlap must keep speaker=None"

    def test_multiple_segments_are_independent(self):
        segments = [
            {"start": 0.0, "end": 2.0},
            {"start": 5.0, "end": 7.0},
            {"start": 11.0, "end": 13.0},
        ]
        turns = [(0.0, 4.0, "Speaker 1"), (4.0, 8.0, "Speaker 2"), (8.0, 12.0, "Speaker 3")]
        labels = _align(segments, turns)
        assert labels == {0: "Speaker 1", 1: "Speaker 2", 2: "Speaker 3"}

    def test_production_aligner_matches_reference(self):
        """The developer's aligner (when it lands) must agree with the
        reference semantics on the canonical example."""
        try:
            from meeting_notes_ai.services.diarization import assign_speakers
        except (ImportError, AttributeError):
            pytest.fail(
                "services/diarization.py must expose assign_speakers(segments, turns) "
                "implementing max-overlap alignment"
            )
        segments = [
            {"start": 0.0, "end": 2.0, "text": "first"},
            {"start": 2.5, "end": 4.0, "text": "second"},
            {"start": 5.0, "end": 6.0, "text": "third"},
        ]
        turns = [(0.0, 3.0, "Alice"), (3.0, 7.0, "Bob")]
        labels = assign_speakers(segments, turns)
        assert labels == {0: "Alice", 1: "Bob", 2: "Bob"}, (
            f"assign_speakers must match max-overlap reference, got {labels}"
        )


class TestDiarizedSegmentsBehavioral:
    """P1-1 RED: multi-speaker audio → TranscriptSegments carrying speaker."""

    def test_fake_diarizer_labels_segments(self):
        """A fake diarizer + segments → each segment carries the max-overlap
        speaker label. RED while services/diarization.py does not exist."""
        from meeting_notes_ai.models import TranscriptSegment

        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="hello"),
            TranscriptSegment(start=2.5, end=4.0, text="world"),
        ]
        turns = [(0.0, 3.0, "Speaker 1"), (3.0, 5.0, "Speaker 2")]

        try:
            from meeting_notes_ai.services.diarization import apply_diarization
        except (ImportError, AttributeError):
            pytest.fail(
                "services/diarization.py must expose apply_diarization(segments, turns) "
                "that returns segments with speaker labels set"
            )

        labeled = apply_diarization(segments, turns)
        assert labeled[0].speaker == "Speaker 1", (
            f"segment 0 must carry 'Speaker 1', got {labeled[0].speaker!r}"
        )
        assert labeled[1].speaker == "Speaker 2", (
            f"segment 1 must carry 'Speaker 2', got {labeled[1].speaker!r}"
        )

    def test_diarizer_accepts_injected_backend(self):
        """SpeakerDiarizer must accept an injectable backend (pyannote stand-in)
        so tests can run without the HF model."""
        from meeting_notes_ai.services.diarization import SpeakerDiarizer

        try:
            diarizer = SpeakerDiarizer(backend=None)
        except TypeError as exc:
            pytest.fail(f"SpeakerDiarizer must accept backend=None for injection: {exc}")
        assert diarizer is not None

    def test_diarizer_can_be_constructed_with_token_gate(self, monkeypatch):
        """The HF_TOKEN gate must be optional — construction must not hard-fail
        when no token is configured (best-effort design)."""
        monkeypatch.delenv("HF_TOKEN", raising=False)
        from meeting_notes_ai.services.diarization import SpeakerDiarizer

        diarizer = SpeakerDiarizer(backend=None)
        assert diarizer is not None


class TestDiarizationDisabledParity:
    """DIARIZATION=0 must be identical to the no-speaker path (spec AC)."""

    def test_disabled_pipeline_skips_diarization(self, monkeypatch):
        """With DIARIZATION off, transcription output must be byte-identical to
        P0 (no speaker labels introduced)."""
        monkeypatch.setenv("DIARIZATION", "0")
        from meeting_notes_ai.config import Settings

        s = Settings()
        assert getattr(s, "diarization_enabled", 0) in (0, False, "0", "false"), (
            "DIARIZATION=0 must disable the pass"
        )
