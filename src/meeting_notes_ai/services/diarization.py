"""Speaker diarization — best-effort multi-speaker attribution (P1-1).

After transcription, a diarization pass assigns a ``speaker`` label to each
``TranscriptSegment`` via max-overlap alignment against diarization turns.
Labels surface in evidence and seed extraction ``assignee``.

Design (per analysis/analysis-brief.md §4 P1-1):

- ``SpeakerDiarizer`` wraps a pyannote.audio 3.1 pipeline, gated on
  ``HF_TOKEN`` and explicitly enabled via ``DIARIZATION=1``. The default
  (``DIARIZATION=0``) is OFF, so P0 output stays byte-identical to the
  no-speaker path. The pyannote import is lazy and entirely injectable
  (``backend=`` constructor kwarg), so tests can stand in a duck-typed
  pipeline without the heavy HF dependency.
- ``assign_speakers`` — the pure alignment primitive: for each segment pick
  the turn with the maximum time overlap (ties resolve to the earliest turn);
  segments overlapping no turn keep ``speaker=None``.
- ``apply_diarization`` — convenience that aligns a list of
  ``TranscriptSegment`` objects against turns and returns the same segments
  with their ``speaker`` fields set.

Best-effort by design: raw accuracy is intentionally NOT asserted by tests.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from meeting_notes_ai.models import TranscriptSegment

# A diarization turn: (start_seconds, end_seconds, speaker_label).
Turn = tuple[float, float, str]

_OVERLAP_EPSILON = 1e-9


def assign_speakers(
    segments: Sequence[dict[str, Any] | TranscriptSegment],
    turns: Iterable[Turn],
) -> dict[int, str]:
    """Assign each segment to the single diarization turn it overlaps most.

    For every segment the overlap duration with each turn is computed as
    ``max(0, min(seg_end, turn_end) - max(seg_start, turn_start))``; the turn
    with the maximum overlap wins. Ties resolve to the earliest turn. A
    boundary touch (zero-length overlap) does not count, and segments that
    overlap no turn keep ``speaker=None`` (absent from the result dict).

    Args:
        segments: Iterable of objects exposing ``start``/``end`` (dicts or
            ``TranscriptSegment`` models).
        turns: Iterable of ``(start, end, speaker)`` diarization turns.

    Returns:
        Mapping of segment index → speaker label for segments with a positive
        overlap. Segments without any overlap are omitted.
    """
    turn_list = list(turns)
    best_labels: dict[int, str] = {}
    for idx, seg in enumerate(segments):
        seg_start = float(seg["start"] if isinstance(seg, dict) else seg.start)
        seg_end = float(seg["end"] if isinstance(seg, dict) else seg.end)
        best_turn: str | None = None
        best_overlap = 0.0
        for start, end, speaker in turn_list:
            overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
            if overlap > best_overlap + _OVERLAP_EPSILON:
                best_overlap = overlap
                best_turn = speaker
        if best_turn is not None and best_overlap > 0.0:
            best_labels[idx] = best_turn
    return best_labels


def apply_diarization(
    segments: list[TranscriptSegment],
    turns: Iterable[Turn],
) -> list[TranscriptSegment]:
    """Return the segments with ``speaker`` labels set by max-overlap alignment.

    Mutates the ``speaker`` attribute of the given segments in place and also
    returns the list, mirroring the reference behavior tests assert against.

    Args:
        segments: Transcript segments (Whisper output) to label.
        turns: Diarization turns ``(start, end, speaker)``.

    Returns:
        The same segments with ``speaker`` set where a positive overlap exists.
    """
    labels = assign_speakers(segments, turns)
    for idx, speaker in labels.items():
        segments[idx].speaker = speaker
    return segments


class SpeakerDiarizer:
    """Multi-speaker attribution wrapper around a pyannote pipeline.

    Args:
        backend: Injectable diarization backend whose
            ``__call__(audio, sample_rate)`` returns an iterable of
            ``(start, end, speaker)`` turns. When ``None``, a pyannote
            ``SpeakerDiarization`` pipeline is built lazily from ``HF_TOKEN``.
        hf_token: HuggingFace token for the gated pyannote model. Falls back to
            the ``HF_TOKEN`` environment variable.

    The class is constructed eagerly only when ``DIARIZATION=1``; with the
    default (off) configuration the pipeline never loads and ``diarize`` is
    never called, preserving P0 behavior.
    """

    def __init__(self, backend: Any | None = None, hf_token: str | None = None) -> None:
        import os

        self._backend = backend
        self._hf_token = hf_token if hf_token is not None else os.getenv("HF_TOKEN", "")

    def _build_pipeline(self) -> Any:
        """Lazily import and build the pyannote SpeakerDiarization pipeline."""
        if self._backend is None:
            from pyannote.audio import Pipeline

            self._backend = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", token=self._hf_token or None
            )
        return self._backend

    async def diarize(
        self, audio_bytes: bytes, sample_rate: int
    ) -> list[tuple[float, float, str]]:
        """Run diarization over raw audio and return ``(start, end, speaker)`` turns.

        Args:
            audio_bytes: Raw audio file bytes (WAV/WebM/…).
            sample_rate: Sample rate of the audio in Hz.

        Returns:
            A list of ``(start_seconds, end_seconds, speaker_label)`` turns. An
            empty list is returned when diarization is unavailable (best-effort
            design — callers keep ``speaker=None``).
        """
        pipeline = self._build_pipeline()
        result = pipeline(audio_bytes, sample_rate=sample_rate)
        turns: list[tuple[float, float, str]] = []
        for turn in result.itertracks(yield_label=True):
            segment, _, label = turn
            turns.append((float(segment.start), float(segment.end), str(label)))
        return turns
