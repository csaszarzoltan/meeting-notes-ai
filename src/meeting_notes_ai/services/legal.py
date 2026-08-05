"""Legal mode — deposition summaries with objection tracking."""

from __future__ import annotations

from meeting_notes_ai.models import (
    CaseMetadata,
    ExtractionResult,
    LegalNote,
    MeetingMode,
    Objection,
    TestimonyPoint,
)
from meeting_notes_ai.services.extraction import ExtractionService


class LegalService:
    """Generate deposition summaries from transcript."""

    def __init__(self, extraction_service: ExtractionService) -> None:
        self.extraction_service = extraction_service

    async def process(
        self,
        transcript: str,
        case_metadata: CaseMetadata | None = None,
    ) -> LegalNote:
        """Process transcript into structured legal note.

        Uses the extraction service to extract structured data, then
        formats it into a deposition summary with testimony points and objections.
        """
        extraction: ExtractionResult = await self.extraction_service.extract(
            transcript, mode=MeetingMode.LEGAL
        )

        # Build testimony points from key_points and action_items
        testimony = _build_testimony(extraction)

        # Build objections from decisions
        objections = _build_objections(extraction)

        return LegalNote(
            summary=extraction.summary,
            key_testimony=testimony,
            objections=objections,
            case_metadata=case_metadata,
        )


def _build_testimony(result: ExtractionResult) -> list[TestimonyPoint]:
    """Build testimony points from extraction result."""
    testimony: list[TestimonyPoint] = []

    # Use key_points as testimony excerpts
    for i, point in enumerate(result.key_points):
        tp = TestimonyPoint(
            witness=None,  # Would be identified in full LLM extraction
            topic=f"Key point {i + 1}",
            excerpt=point,
            timestamp_range=None,
        )
        testimony.append(tp)

    # Use action items as additional testimony if they reference people
    for item in result.action_items:
        if item.assignee:
            tp = TestimonyPoint(
                witness=item.assignee,
                topic="Action item",
                excerpt=item.description,
                timestamp_range=None,
            )
            testimony.append(tp)

    return testimony


def _build_objections(result: ExtractionResult) -> list[Objection]:
    """Build objection records from extraction result decisions."""
    objections: list[Objection] = []

    # Decisions may contain objection-related content
    for decision in result.decisions:
        obj = Objection(
            type="general",
            context=decision,
            ruling=None,
        )
        objections.append(obj)

    return objections
