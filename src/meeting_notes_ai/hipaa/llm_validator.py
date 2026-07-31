"""LLM-based PHI validation pass.

After regex scan, passes redacted text + original PHI matches to an LLM
for validation. Catches context-dependent PHI and reduces false positives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMValidationResult:
    """Result of an LLM validation pass over regex PHI matches."""

    confirmed_matches: list = field(default_factory=list)
    false_positives: list = field(default_factory=list)
    new_matches: list = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    llm_analysis: str = ""


class LLMValidator:
    """Validate PHI matches using an LLM for context-aware correction.

    After the regex pass, this validator asks the LLM to:
    - Confirm or reject each regex match (reducing false positives)
    - Identify any PHI the regex missed (context-dependent detection)
    """

    def __init__(
        self,
        extraction_service: Any | None = None,
        config: Any | None = None,
    ) -> None:
        """Initialize with optional extraction service and HIPAAConfig."""
        self._extraction = extraction_service
        self._config = config

    async def validate(
        self,
        original_text: str,
        regex_matches: list,
    ) -> LLMValidationResult:
        """Validate regex matches and catch missed PHI via LLM.

        Args:
            original_text: The full original text before redaction.
            regex_matches: List of PHIMatch objects from the regex scan.

        Returns:
            LLMValidationResult with confirmed/false-positive/new matches.
        """
        # Default: confirm all regex matches (no LLM call in stub)
        return LLMValidationResult(
            confirmed_matches=list(regex_matches),
        )

    async def suggest_redactions(self, text: str) -> list:
        """Ask the LLM to suggest redactions directly (bypass regex)."""
        return []
