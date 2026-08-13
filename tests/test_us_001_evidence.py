import pytest

from meeting_notes_ai.services.evidence import SegmentSpan, publication_blockers, validate_spans


def test_us_001_ac_1_valid_grounding():
    validate_spans("m1", [SegmentSpan("s1", "m1", 0, 2000, 200, 1200)])
    assert publication_blockers([{"id": "c1", "evidence": ["s1"], "status": "approved"}]) == []


def test_us_001_ac_2_unsupported_is_blocked():
    assert (
        publication_blockers([{"id": "c1", "evidence": [], "status": "draft"}])[0]["code"]
        == "UNSUPPORTED"
    )


def test_us_001_ac_3_cross_meeting_and_bounds_fail():
    with pytest.raises(ValueError, match="same meeting"):
        validate_spans("m1", [SegmentSpan("s1", "m2", 0, 1000, 0, 500)])
    with pytest.raises(ValueError, match="inside"):
        validate_spans("m1", [SegmentSpan("s1", "m1", 0, 1000, 0, 1500)])


def test_us_001_additional_boundary_and_status_cases():
    with pytest.raises(ValueError, match="precede"):
        validate_spans("m1", [SegmentSpan("s1", "m1", 0, 1000, 500, 500)])
    blockers = publication_blockers(
        [{"id": "c1", "evidence": ["s1"], "status": "needs_reapproval"}]
    )
    assert blockers[0]["code"] == "NEEDS_REAPPROVAL"
