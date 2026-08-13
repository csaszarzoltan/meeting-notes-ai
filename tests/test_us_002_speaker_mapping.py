import pytest

from meeting_notes_ai.services.review import apply_speaker_mapping

BASE = [
    {"id": "s1", "speaker_name": "Speaker 1", "revision": 1},
    {"id": "s2", "speaker_name": "Speaker 1", "revision": 1},
]


def test_us_002_ac_1_atomic_mapping():
    out, rev = apply_speaker_mapping(BASE, ["s1", "s2"], "Alex", 1)
    assert rev == 2 and [x["speaker_name"] for x in out] == ["Alex", "Alex"]
    assert BASE[0]["speaker_name"] == "Speaker 1"


def test_us_002_ac_2_unknown_is_not_guessed():
    with pytest.raises(ValueError, match="Unknown"):
        apply_speaker_mapping(BASE, ["missing"], "Alex", 1)


def test_us_002_ac_3_stale_mapping_fails_without_mutation():
    with pytest.raises(RuntimeError, match="stale"):
        apply_speaker_mapping(BASE, ["s1"], "Alex", 2)
    assert BASE[0]["revision"] == 1


def test_us_002_additional_validation_cases():
    with pytest.raises(ValueError, match="required"):
        apply_speaker_mapping(BASE, ["s1"], " ", 1)
    with pytest.raises(ValueError, match="500"):
        apply_speaker_mapping(BASE, ["s1"] * 501, "Alex", 1)
