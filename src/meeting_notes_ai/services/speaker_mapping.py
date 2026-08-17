"""Deterministic speaker-to-PM-assignee resolver.

Maps diarized speaker labels (SPEAKER_00, names, email prefixes)
to provider-specific assignee identifiers without any LLM involvement.

Matching strategy (in priority order):
  1. Exact speaker_label field match
  2. Case-insensitive name match
  3. Email-local-part (prefix) match
  4. None (unassigned fallback)
"""

from __future__ import annotations

# Maps provider slug → key expected inside a participant dict
# for the provider-specific assignee identifier.
_PROVIDER_ID_KEYS: dict[str, str] = {
    "jira": "jira_account_id",
    "linear": "linear_id",
    "asana": "asana_gid",
    "todoist": "todoist_uid",
}


def _find_participant(
    speaker_label: str,
    participants: list[dict[str, str]],
) -> dict[str, str] | None:
    """Return the first participant matching *speaker_label*.

    Priority: speaker_label field → case-insensitive name → email prefix.
    """
    if not speaker_label or not participants:
        return None

    # 1. Exact speaker_label match
    for p in participants:
        if p.get("speaker_label") == speaker_label:
            return p

    # 2. Case-insensitive name match
    lower = speaker_label.lower()
    for p in participants:
        if p.get("name", "").lower() == lower:
            return p

    # 3. Email-local-part match (prefix before @)
    for p in participants:
        email = p.get("email", "")
        if email and email.split("@", 1)[0].lower() == lower:
            return p

    return None


def resolve_assignee(
    speaker_label: str,
    participants: list[dict[str, str]],
    provider: str,
) -> str | None:
    """Map a diarized speaker label to a PM-tool assignee identifier.

    Args:
        speaker_label: e.g. ``"SPEAKER_00"`` or ``"Maya"``.
        participants: list of dicts with at least one of *name*,
            *email*, *speaker_label*, and optionally provider-specific
            ID keys (``jira_account_id``, ``linear_id``, ``asana_gid``,
            ``todoist_uid``).
        provider: target PM tool slug (``"jira"`` | ``"linear"`` |
            ``"asana"`` | ``"todoist"``).

    Returns:
        Provider-specific assignee ID when a match is found *and* the
        participant carries the provider key; otherwise the matched
        email prefix or name as a best-effort string; ``None`` when no
        participant matches at all.
    """
    matched = _find_participant(speaker_label, participants)
    if matched is None:
        return None

    # Try provider-specific ID first
    id_key = _PROVIDER_ID_KEYS.get(provider)
    if id_key and id_key in matched:
        return matched[id_key]

    # Fallback: email prefix, then raw name
    email = matched.get("email", "")
    if email:
        return email.split("@", 1)[0]

    name = matched.get("name")
    if name:
        return name

    return None
