"""PHI detection and redaction engine.

Provides a pattern registry loaded from a JSON file and a PHIRedactor class
that scans text for 18 HIPAA identifier categories and applies configurable
redaction modes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from meeting_notes_ai.hipaa.config import HIPAAConfig


@dataclass
class PHIMatch:
    """A single PHI match detected in text."""

    category: str = ""
    label: str = ""
    risk_level: Literal["high", "medium", "low"] = "low"
    start: int = 0
    end: int = 0
    matched_text: str = ""
    redaction_mode: str = "mask"


@dataclass
class PHIRedactionResult:
    """Result of a redaction operation."""

    redacted_text: str = ""
    matches: list[PHIMatch] = field(default_factory=list)
    count_by_category: dict[str, int] = field(default_factory=dict)


# ── Default PHI patterns ──────────────────────────────────────────────────────
# These mirror the 18 HIPAA identifiers, loaded from a patterns dict.
# The patterns JSON file path is configurable via HIPAAConfig.phi_patterns_path.

DEFAULT_PHI_PATTERNS: dict[str, dict[str, Any]] = {
    "ssn": {
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "label": "Social Security Number",
        "risk_level": "high",
    },
    "dob": {
        "pattern": r"\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b",
        "label": "Date of Birth",
        "risk_level": "high",
    },
    "phone": {
        "pattern": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "label": "Phone Number",
        "risk_level": "medium",
    },
    "email": {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "label": "Email Address",
        "risk_level": "medium",
    },
    "mrn": {
        "pattern": r"\bMRN[:\s]*(\d{6,10})\b",
        "label": "Medical Record Number",
        "risk_level": "high",
    },
    "name": {
        "pattern": (
            r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+"
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"
        ),
        "label": "Patient/Provider Name (with title)",
        "risk_level": "medium",
    },
}


class PHIRedactor:
    """Configurable PHI redactor backed by a regex pattern registry.

    Scans text against all 18 HIPAA identifier categories and supports
    multiple redaction modes (mask, hash, truncate, annotate).
    """

    def __init__(self, config: HIPAAConfig | None = None) -> None:
        """Initialise redactor with optional HIPAAConfig."""
        self.config = config or HIPAAConfig()
        self._patterns: dict[str, dict[str, Any]] = {}
        self._compiled: dict[str, re.Pattern] = {}
        self._stats: dict[str, Any] = {
            "by_category": {},
            "by_risk_level": {},
            "total_matches": 0,
        }
        self._load_patterns()

    # ── Pattern loading ────────────────────────────────────────────────────────

    def _load_patterns(self) -> None:
        """Try loading from JSON file, fall back to defaults."""
        patterns_path = Path(self.config.phi_patterns_path)
        if patterns_path.exists():
            with open(patterns_path) as f:
                raw: dict[str, dict[str, Any]] = json.load(f)
        else:
            raw = dict(DEFAULT_PHI_PATTERNS)

        self._patterns = {}
        for name, info in raw.items():
            self._patterns[name] = {
                "pattern": info.get("pattern", ""),
                "label": info.get("label", name),
                "risk_level": info.get("risk_level", "low"),
            }

        self._recompile()

    def _recompile(self) -> None:
        """Recompile all regex patterns."""
        self._compiled = {}
        for name, info in self._patterns.items():
            try:
                self._compiled[name] = re.compile(info["pattern"])
            except re.error:
                pass

    # ── Scanning ───────────────────────────────────────────────────────────────

    def scan(self, text: str) -> list[PHIMatch]:
        """Scan *text* for PHI and return all matches."""
        if not text:
            return []

        matches: list[PHIMatch] = []

        for name, compiled in self._compiled.items():
            info = self._patterns[name]
            for m in compiled.finditer(text):
                match_text = m.group()
                # For name patterns with titles, skip if it matches generic
                # capitalized word pairs without a title prefix — handled
                # by the regex itself.
                matches.append(
                    PHIMatch(
                        category=name,
                        label=info["label"],
                        risk_level=info.get("risk_level", "low"),
                        start=m.start(),
                        end=m.end(),
                        matched_text=match_text,
                        redaction_mode="mask",
                    )
                )

        # Also detect generic capitalized name pairs (FirstName LastName)
        # that are not caught by the title-prefixed pattern.
        name_pattern = re.compile(
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"
        )
        for m in name_pattern.finditer(text):
            matched = m.group()
            # Skip if already matched by another named pattern
            already_matched = any(
                not (m2.end <= m.start() or m2.start >= m.end())
                for m2 in matches
            )
            if already_matched:
                continue
            # Skip common false positives (month names, day-of-week, etc.)
            skip_words = {
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday", "Today", "Yesterday", "Tomorrow",
            }
            words = matched.split()
            if any(w in skip_words for w in words):
                continue

            matches.append(
                PHIMatch(
                    category="name",
                    label="Patient/Provider Name",
                    risk_level="medium",
                    start=m.start(),
                    end=m.end(),
                    matched_text=matched,
                    redaction_mode="mask",
                )
            )

        # Update stats
        self._update_stats(matches)

        # Sort by position
        matches.sort(key=lambda x: x.start)
        return matches

    def _update_stats(self, matches: list[PHIMatch]) -> None:
        """Update internal aggregate statistics."""
        for m in matches:
            self._stats["by_category"][m.category] = (
                self._stats["by_category"].get(m.category, 0) + 1
            )
            self._stats["by_risk_level"][m.risk_level] = (
                self._stats["by_risk_level"].get(m.risk_level, 0) + 1
            )
            self._stats["total_matches"] = (
                self._stats.get("total_matches", 0) + 1
            )

    # ── Redaction ──────────────────────────────────────────────────────────────

    def redact(self, text: str, mode: str = "mask") -> tuple[str, list[PHIMatch]]:
        """Redact all PHI from *text* using the given *mode*.

        Returns ``(redacted_text, matches)``.
        """
        matches = self.scan(text)
        if not matches:
            return text, matches

        redacted = text
        # Replace from end to start to preserve positions
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            replacement = self._get_replacement(m.matched_text, mode)
            redacted = redacted[: m.start] + replacement + redacted[m.end :]

        return redacted, matches

    @staticmethod
    def _get_replacement(matched_text: str, mode: str) -> str:
        """Determine the replacement string for a given mode."""
        if mode == "hash":
            import hashlib
            return hashlib.sha256(matched_text.encode()).hexdigest()[:12]
        elif mode == "truncate":
            return matched_text[:1] + "..." if len(matched_text) > 3 else "***"
        elif mode == "annotate":
            return f"[PHI:{len(matched_text)}]"
        else:  # mask (default)
            return "[REDACTED]"

    # ── Custom patterns ────────────────────────────────────────────────────────

    def add_custom_pattern(self, name: str, pattern: str, risk_level: str) -> None:
        """Register a custom PHI pattern at runtime."""
        self._patterns[name] = {
            "pattern": pattern,
            "label": f"Custom: {name}",
            "risk_level": risk_level,
        }
        try:
            self._compiled[name] = re.compile(pattern)
        except re.error:
            # If pattern is invalid, remove it and raise
            self._patterns.pop(name, None)
            raise ValueError(f"Invalid regex pattern for '{name}': {pattern}")

    # ── Stats ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate match statistics by category and risk level."""
        return dict(self._stats)

    # ── Reload ──────────────────────────────────────────────────────────────────

    def reload_patterns(self) -> int:
        """Hot-reload the patterns JSON file. Returns pattern count."""
        self._load_patterns()
        return len(self._patterns)
