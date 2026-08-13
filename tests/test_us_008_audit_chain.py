import io
import json
import zipfile

import pytest

from meeting_notes_ai.services.governance.audit_chain import (
    append_event,
    export_zip,
    validate_chain,
)


def test_us_008_ac_1_detects_tamper():
    events = []
    append_event(events, "t", "u", "review.approved", {"claim": "c"})
    events[0]["event_type"] = "changed"
    assert validate_chain(events)["valid"] is False


def test_us_008_ac_2_empty_export_is_valid():
    blob = export_zip([], b"x" * 32)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert json.loads(z.read("manifest.json"))["count"] == 0


def test_us_008_ac_3_short_key_fails():
    with pytest.raises(ValueError, match="32 bytes"):
        export_zip([], b"short")


def test_us_008_valid_chain_and_csv_export():
    events = []
    append_event(events, "t", "u", "first", {"x": 1})
    append_event(events, "t", "u", "second", {"x": 2})
    assert validate_chain(events)["valid"] is True
    blob = export_zip(events, b"x" * 32, include_csv=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert "events.csv" in archive.namelist()


def test_us_008_refuses_export_of_invalid_chain():
    events = []
    append_event(events, "t", "u", "first", {"x": 1})
    events[0]["previous_hash"] = "bad"
    with pytest.raises(ValueError, match="invalid"):
        export_zip(events, b"x" * 32)
