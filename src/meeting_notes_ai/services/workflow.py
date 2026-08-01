"""User-centered meeting workflow policies and privacy-safe telemetry."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock
from typing import Any

from meeting_notes_ai.models import MeetingMode


@dataclass(frozen=True)
class ProcessingPolicy:
    """Resolved processing safeguards for one meeting."""

    phi_redaction: bool
    review_required: bool


def resolve_processing_policy(
    mode: str | MeetingMode, phi_redaction: bool | None
) -> ProcessingPolicy:
    """Resolve safe defaults without silently weakening an explicit workspace choice.

    Healthcare content defaults to redaction and human review. Other modes preserve
    existing behavior unless the caller explicitly opts into redaction.
    """
    parsed = mode if isinstance(mode, MeetingMode) else MeetingMode(mode)
    return ProcessingPolicy(
        phi_redaction=(
            parsed is MeetingMode.HEALTHCARE if phi_redaction is None else phi_redaction
        ),
        review_required=parsed in {MeetingMode.HEALTHCARE, MeetingMode.LEGAL},
    )


class WorkflowTelemetry:
    """Minimal in-process counters that deliberately never accept transcript text or PHI."""

    _allowed = {"started", "completed", "failed", "redacted", "needs_review"}

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._lock = Lock()

    def record(self, event: str, *, mode: MeetingMode) -> None:
        if event not in self._allowed:
            raise ValueError(f"Unsupported telemetry event: {event}")
        with self._lock:
            self._counts[f"{event}:{mode.value}"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "events": dict(self._counts),
                "privacy": "No transcript, filename, or PHI collected",
            }


workflow_telemetry = WorkflowTelemetry()
