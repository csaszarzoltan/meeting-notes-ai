"""Interface and behavioral tests for LegalService (deposition summaries)."""

from __future__ import annotations

from inspect import signature
from unittest.mock import AsyncMock

import pytest

from meeting_notes_ai.models import (
    CaseMetadata,
    ExtractionResult,
    LegalNote,
    Objection,
    TestimonyPoint,
)
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.legal import LegalService

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestLegalServiceInterface:
    """Verify LegalService class contract."""

    def test_legal_service_can_be_imported(self):
        """LegalService should be importable."""
        assert LegalService is not None

    def test_legal_note_can_be_imported(self):
        """LegalNote model should be importable."""
        assert LegalNote is not None

    def test_testimony_point_can_be_imported(self):
        """TestimonyPoint model should be importable."""
        assert TestimonyPoint is not None

    def test_objection_can_be_imported(self):
        """Objection model should be importable."""
        assert Objection is not None

    def test_case_metadata_can_be_imported(self):
        """CaseMetadata model should be importable."""
        assert CaseMetadata is not None

    def test_legal_init_signature(self):
        """__init__ should accept extraction_service."""
        sig = signature(LegalService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "extraction_service" in params

    def test_process_signature(self):
        """process method should have expected signature."""
        assert hasattr(LegalService, "process")
        sig = signature(LegalService.process)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "transcript" in params
        assert "case_metadata" in params

    def test_process_is_async(self):
        """process should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(LegalService.process)

    def test_case_metadata_default_none(self):
        """case_metadata should default to None."""
        sig = signature(LegalService.process)
        param = sig.parameters.get("case_metadata")
        assert param is not None
        assert param.default is None

    def test_legal_note_instantiation(self):
        """LegalNote should be instantiable with fields."""
        note = LegalNote(
            summary="Deposition of John Doe",
            key_testimony=[
                TestimonyPoint(
                    witness="John Doe",
                    topic="Contract signing",
                    excerpt="I signed the contract on March 15th",
                    timestamp_range=(120.0, 145.0),
                )
            ],
            objections=[
                Objection(
                    type="hearsay",
                    context="Witness testifying about what defendant said",
                    ruling="Sustained",
                )
            ],
            case_metadata=CaseMetadata(
                case_number="2026-CV-0042",
                parties=["Plaintiff Corp.", "Defendant LLC"],
                date="2026-07-15",
                jurisdiction="Southern District of New York",
            ),
        )
        assert note.summary == "Deposition of John Doe"
        assert len(note.key_testimony) == 1
        assert len(note.objections) == 1
        assert note.case_metadata is not None
        assert note.case_metadata.case_number == "2026-CV-0042"

    def test_legal_note_defaults(self):
        """LegalNote should have sensible defaults."""
        note = LegalNote()
        assert note.summary == ""
        assert note.key_testimony == []
        assert note.objections == []
        assert note.case_metadata is None

    def test_testimony_point_instantiation(self):
        """TestimonyPoint should be instantiable."""
        tp = TestimonyPoint(
            witness="Jane Smith",
            topic="Email communication",
            excerpt="I received the email on Tuesday",
            timestamp_range=(45.0, 60.0),
        )
        assert tp.witness == "Jane Smith"
        assert tp.topic == "Email communication"
        assert tp.timestamp_range == (45.0, 60.0)

    def test_testimony_point_defaults(self):
        """TestimonyPoint should have optional fields."""
        tp = TestimonyPoint(topic="General", excerpt="...")
        assert tp.witness is None
        assert tp.timestamp_range is None

    def test_objection_instantiation(self):
        """Objection should be instantiable."""
        obj = Objection(type="relevance", context="Irrelevant to case", ruling="Overruled")
        assert obj.type == "relevance"
        assert obj.ruling == "Overruled"

    def test_objection_defaults(self):
        """Objection should have optional ruling."""
        obj = Objection(type="compound", context="Compound question")
        assert obj.ruling is None

    def test_case_metadata_instantiation(self):
        """CaseMetadata should be instantiable."""
        cm = CaseMetadata(
            case_number="2026-CV-0042",
            parties=["Plaintiff", "Defendant"],
            date="2026-07-15",
            jurisdiction="SDNY",
        )
        assert cm.case_number == "2026-CV-0042"
        assert cm.parties == ["Plaintiff", "Defendant"]

    def test_case_metadata_defaults(self):
        """CaseMetadata should have optional fields."""
        cm = CaseMetadata(date="2026-07-15")
        assert cm.case_number is None
        assert cm.parties == []
        assert cm.jurisdiction is None


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestLegalServiceBehavioral:
    """Verify legal behavior with real implementation."""

    def test_init_succeeds(self):
        """Instantiating LegalService should not raise."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = LegalService(extraction_service=extraction)
        assert service.extraction_service is extraction

    @pytest.mark.asyncio
    async def test_process_returns_legal_note(self, sample_transcript):
        """Calling process should return a LegalNote."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = LegalService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="Deposition of witness",
            key_points=["Witness confirmed signing the contract"],
            action_items=[],
            decisions=["Objection overruled"],
        )
        service.extraction_service = mock_extraction

        result = await service.process(sample_transcript)
        assert isinstance(result, LegalNote)
        assert result.case_metadata is None

    @pytest.mark.asyncio
    async def test_process_with_case_metadata(self, sample_transcript):
        """Calling process with case_metadata."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = LegalService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="Deposition",
            key_points=[],
            action_items=[],
            decisions=[],
        )
        service.extraction_service = mock_extraction

        cm = CaseMetadata(
            case_number="2026-CV-0042",
            parties=["Plaintiff"],
            date="2026-07-15",
        )
        result = await service.process(
            sample_transcript, case_metadata=cm
        )
        assert result.case_metadata is not None
        assert result.case_metadata.case_number == "2026-CV-0042"

    @pytest.mark.asyncio
    async def test_process_with_empty_transcript(self, empty_transcript):
        """Calling process with empty transcript returns LegalNote."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = LegalService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="",
            key_points=[],
            action_items=[],
            decisions=[],
        )
        service.extraction_service = mock_extraction

        result = await service.process(empty_transcript)
        assert isinstance(result, LegalNote)
        assert result.summary == ""
