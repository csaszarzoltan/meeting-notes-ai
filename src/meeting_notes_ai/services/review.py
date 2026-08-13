"""Versioned review and speaker-correction rules."""

from copy import deepcopy


def apply_speaker_mapping(
    segments: list[dict], segment_ids: list[str], canonical_name: str, expected_revision: int
) -> tuple[list[dict], int]:
    if not canonical_name.strip():
        raise ValueError("canonical_name is required")
    if len(segment_ids) > 500:
        raise ValueError("At most 500 segments may be mapped")
    if any(s.get("revision", 1) != expected_revision for s in segments if s["id"] in segment_ids):
        raise RuntimeError("stale transcript revision")
    found = {s["id"] for s in segments}
    requested = set(segment_ids)
    if not requested.issubset(found):
        raise ValueError("Unknown segment")
    result = deepcopy(segments)
    for s in result:
        if s["id"] in requested:
            s["speaker_name"] = canonical_name.strip()
            s["revision"] = expected_revision + 1
    return result, expected_revision + 1


def evaluate_policy(claims: list[dict], strict: bool, required_approvals: int) -> list[dict]:
    blockers = []
    for c in claims:
        if strict and not c.get("evidence"):
            blockers.append({"claim_id": c["id"], "code": "UNSUPPORTED"})
        if c.get("status") in {"rejected", "needs_reapproval"}:
            blockers.append({"claim_id": c["id"], "code": "NOT_APPROVABLE"})
        if len(set(c.get("approver_ids", []))) < required_approvals:
            blockers.append({"claim_id": c["id"], "code": "APPROVALS_REQUIRED"})
    return blockers
