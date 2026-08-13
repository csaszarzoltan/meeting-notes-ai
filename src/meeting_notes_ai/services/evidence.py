"""Evidence validation for grounded meeting claims."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentSpan:
    segment_id: str
    meeting_id: str
    segment_start_ms: int
    segment_end_ms: int
    start_ms: int
    end_ms: int


def validate_spans(meeting_id: str, spans: list[SegmentSpan]) -> None:
    if not spans:
        raise ValueError("A publishable claim requires evidence")
    for span in spans:
        if span.meeting_id != meeting_id:
            raise ValueError("Evidence must belong to the same meeting")
        if span.start_ms < span.segment_start_ms or span.end_ms > span.segment_end_ms:
            raise ValueError("Evidence boundaries must be inside the segment")
        if span.start_ms >= span.end_ms:
            raise ValueError("Evidence start must precede end")


def publication_blockers(claims: list[dict]) -> list[dict]:
    blockers = []
    for claim in claims:
        if not claim.get("evidence"):
            blockers.append({"claim_id": claim["id"], "code": "UNSUPPORTED"})
        if claim.get("status") in {"rejected", "needs_reapproval"}:
            blockers.append({"claim_id": claim["id"], "code": claim["status"].upper()})
    return blockers
