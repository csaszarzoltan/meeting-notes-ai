"""Tests for the speaker-to-PM-assignee resolver.

Run: .venv/bin/python -m pytest tests/test_speaker_mapping.py -v
"""

from __future__ import annotations

import pytest

from meeting_notes_ai.services.speaker_mapping import resolve_assignee

pytestmark = pytest.mark.quick

# ── Fixtures ─────────────────────────────────────────────────────────────────

PARTICIPANTS = [
    {
        "name": "Maya",
        "email": "maya@acme.com",
        "speaker_label": "SPEAKER_00",
        "jira_account_id": "5f1a2b3c4d5e6f7a8b9c0d1e",
        "linear_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "asana_gid": "1234567890",
        "todoist_uid": "987654321",
    },
    {
        "name": "Ravi",
        "email": "ravi@acme.com",
        "speaker_label": "SPEAKER_01",
        "jira_account_id": "6e2b3c4d5f6a7b8c9d0e1f2a",
        "linear_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "asana_gid": "2345678901",
        "todoist_uid": "876543210",
    },
]


# ── T1-1: Jira by email prefix ──────────────────────────────────────────────


def test_resolve_assignee_jira_by_email() -> None:
    """Email-prefix match → Jira accountId."""
    result = resolve_assignee("maya", PARTICIPANTS, "jira")
    assert result == "5f1a2b3c4d5e6f7a8b9c0d1e"


# ── T1-2: Linear by speaker_label ───────────────────────────────────────────


def test_resolve_assignee_linear_by_label() -> None:
    """speaker_label match → Linear UUID."""
    result = resolve_assignee("SPEAKER_01", PARTICIPANTS, "linear")
    assert result == "b2c3d4e5-f6a7-8901-bcde-f12345678901"


# ── T1-3: No match → None ──────────────────────────────────────────────────


def test_resolve_assignee_fallback_to_none() -> None:
    """No participant matches → None."""
    result = resolve_assignee("SPEAKER_99", PARTICIPANTS, "jira")
    assert result is None


# ── T1-4: Asana by name (case-insensitive) ──────────────────────────────────


def test_resolve_assignee_asana_by_name() -> None:
    """Case-insensitive name match → Asana GID."""
    result = resolve_assignee("RAVI", PARTICIPANTS, "asana")
    assert result == "2345678901"


# ── T1-5: Todoist by email prefix ───────────────────────────────────────────


def test_resolve_assignee_todoist_by_email() -> None:
    """Email-prefix match → Todoist user ID."""
    result = resolve_assignee("ravi", PARTICIPANTS, "todoist")
    assert result == "876543210"


# ── T1-6: Empty participants ────────────────────────────────────────────────


def test_resolve_assignee_empty_participants() -> None:
    """Empty participant list → None."""
    result = resolve_assignee("SPEAKER_00", [], "jira")
    assert result is None


# ── T1-7: Unknown provider → fallback to email prefix ──────────────────────


def test_resolve_assignee_unknown_provider() -> None:
    """Unknown provider still returns a match via email/name fallback."""
    result = resolve_assignee("Maya", PARTICIPANTS, "trello")
    # No provider-specific key → falls back to email prefix
    assert result == "maya"


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_resolve_assignee_speaker_label_takes_priority() -> None:
    """Exact speaker_label match beats name/email fallback."""
    # SPEAKER_00 is Maya, but name "maya" also matches.
    # speaker_label match wins and returns Maya's Jira ID.
    result = resolve_assignee("SPEAKER_00", PARTICIPANTS, "jira")
    assert result == "5f1a2b3c4d5e6f7a8b9c0d1e"


def test_resolve_assignee_empty_string_label() -> None:
    """Empty speaker label → None."""
    result = resolve_assignee("", PARTICIPANTS, "jira")
    assert result is None


def test_resolve_assignee_no_provider_specific_id() -> None:
    """Participant lacks provider key → fallback to email prefix."""
    sparse = [
        {"name": "Lee", "email": "lee@acme.com", "speaker_label": "SPEAKER_00"},
    ]
    result = resolve_assignee("SPEAKER_00", sparse, "jira")
    assert result == "lee"


def test_resolve_assignee_name_only_fallback() -> None:
    """Participant has only name, no email → returns name."""
    sparse = [
        {"name": "Pat", "speaker_label": "SPEAKER_00"},
    ]
    result = resolve_assignee("SPEAKER_00", sparse, "jira")
    assert result == "Pat"
