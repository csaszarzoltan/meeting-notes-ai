"""Interface and behavioral tests for HealthcareService (SOAP notes)."""

from __future__ import annotations

from inspect import signature
from unittest.mock import AsyncMock

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


from meeting_notes_ai.models import (
    ConsentStatus,
    ExtractionResult,
    HealthcareNote,
    HIPAAMarker,
    SOAPNote,
)
from meeting_notes_ai.services.extraction import ExtractionService
from meeting_notes_ai.services.healthcare import HealthcareService

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestHealthcareServiceInterface:
    """Verify HealthcareService class contract."""

    def test_healthcare_service_can_be_imported(self):
        """HealthcareService should be importable."""
        assert HealthcareService is not None

    def test_soap_note_can_be_imported(self):
        """SOAPNote model should be importable."""
        assert SOAPNote is not None

    def test_hipaa_marker_can_be_imported(self):
        """HIPAAMarker model should be importable."""
        assert HIPAAMarker is not None

    def test_consent_status_can_be_imported(self):
        """ConsentStatus model should be importable."""
        assert ConsentStatus is not None

    def test_healthcare_note_can_be_imported(self):
        """HealthcareNote model should be importable."""
        assert HealthcareNote is not None

    def test_healthcare_init_signature(self):
        """__init__ should accept extraction_service."""
        sig = signature(HealthcareService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "extraction_service" in params

    def test_process_signature(self):
        """process method should have expected signature."""
        assert hasattr(HealthcareService, "process")
        sig = signature(HealthcareService.process)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "transcript" in params
        assert "patient_id" in params
        assert "consent_confirmed" in params

    def test_process_is_async(self):
        """process should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(HealthcareService.process)

    def test_process_has_default_patient_id_none(self):
        """patient_id should default to None."""
        sig = signature(HealthcareService.process)
        param = sig.parameters.get("patient_id")
        assert param is not None
        assert param.default is None

    def test_process_has_default_consent_false(self):
        """consent_confirmed should default to False."""
        sig = signature(HealthcareService.process)
        param = sig.parameters.get("consent_confirmed")
        assert param is not None
        assert param.default is False

    def test_soap_note_instantiation(self):
        """SOAPNote should be instantiable with fields."""
        note = SOAPNote(
            subjective="Patient reports headache",
            objective="BP 120/80, HR 72",
            assessment="Mild hypertension",
            plan="Monitor BP, follow up in 2 weeks",
        )
        assert note.subjective == "Patient reports headache"
        assert note.objective == "BP 120/80, HR 72"
        assert note.assessment == "Mild hypertension"
        assert note.plan == "Monitor BP, follow up in 2 weeks"

    def test_soap_note_defaults(self):
        """SOAPNote should have empty string defaults."""
        note = SOAPNote()
        assert note.subjective == ""
        assert note.objective == ""
        assert note.assessment == ""
        assert note.plan == ""

    def test_hipaa_marker_instantiation(self):
        """HIPAAMarker should be instantiable."""
        marker = HIPAAMarker(
            field="patient_name",
            risk_level="high",
            recommendation="De-identify before sharing",
        )
        assert marker.field == "patient_name"
        assert marker.risk_level == "high"
        assert marker.recommendation == "De-identify before sharing"

    def test_hipaa_marker_defaults(self):
        """HIPAAMarker should have sensible defaults."""
        marker = HIPAAMarker()
        assert marker.field == ""
        assert marker.risk_level == "low"
        assert marker.recommendation == ""

    def test_hipaa_risk_level_literal(self):
        """risk_level should be constrained to high/medium/low."""
        HIPAAMarker(field="test", risk_level="high", recommendation="test")
        HIPAAMarker(field="test", risk_level="medium", recommendation="test")
        HIPAAMarker(field="test", risk_level="low", recommendation="test")

    def test_consent_status_instantiation(self):
        """ConsentStatus should be instantiable."""
        status = ConsentStatus(
            confirmed=True,
            timestamp="2026-07-23T10:00:00",
            note="Consent obtained verbally",
        )
        assert status.confirmed is True
        assert status.timestamp == "2026-07-23T10:00:00"
        assert status.note == "Consent obtained verbally"

    def test_consent_status_defaults(self):
        """ConsentStatus should default to unconfirmed."""
        status = ConsentStatus()
        assert status.confirmed is False
        assert status.timestamp is None
        assert status.note is None

    def test_healthcare_note_instantiation(self):
        """HealthcareNote should be instantiable with all fields."""
        note = HealthcareNote(
            soap=SOAPNote(subjective="Pain"),
            hipaa_markers=[HIPAAMarker(field="name", risk_level="high", recommendation="Remove")],
            consent_status=ConsentStatus(confirmed=True),
            de_identified=True,
        )
        assert note.soap.subjective == "Pain"
        assert len(note.hipaa_markers) == 1
        assert note.consent_status.confirmed is True
        assert note.de_identified is True

    def test_healthcare_note_defaults(self):
        """HealthcareNote should have sensible defaults."""
        note = HealthcareNote()
        assert note.soap == SOAPNote()
        assert note.hipaa_markers == []
        assert note.consent_status == ConsentStatus()
        assert note.de_identified is False


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestHealthcareServiceBehavioral:
    """Verify healthcare behavior with real implementation."""

    def test_init_succeeds(self):
        """Instantiating HealthcareService should not raise."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = HealthcareService(extraction_service=extraction)
        assert service.extraction_service is extraction

    @pytest.mark.asyncio
    async def test_process_returns_healthcare_note(self, sample_transcript):
        """Calling process should return a HealthcareNote."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = HealthcareService(extraction_service=extraction)

        # Mock the extraction service
        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="Patient visit for headache",
            key_points=["Patient reports headache for 3 days", "No fever"],
            action_items=[],
            decisions=["Prescribe ibuprofen"],
        )
        service.extraction_service = mock_extraction

        result = await service.process(sample_transcript)
        assert isinstance(result, HealthcareNote)
        assert result.consent_status.confirmed is False
        assert result.de_identified is True  # No patient_id provided

    @pytest.mark.asyncio
    async def test_process_with_patient_id(
        self, sample_transcript, sample_patient_id
    ):
        """Calling process with patient_id should include HIPAA markers."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = HealthcareService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="Checkup",
            key_points=["Patient is stable"],
            action_items=[],
            decisions=[],
        )
        service.extraction_service = mock_extraction

        result = await service.process(
            sample_transcript, patient_id=sample_patient_id
        )
        assert isinstance(result, HealthcareNote)
        assert any(m.risk_level == "high" for m in result.hipaa_markers)

    @pytest.mark.asyncio
    async def test_process_with_consent(self, sample_transcript):
        """Calling process with consent_confirmed."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = HealthcareService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="Checkup",
            key_points=[],
            action_items=[],
            decisions=[],
        )
        service.extraction_service = mock_extraction

        result = await service.process(
            sample_transcript, consent_confirmed=True
        )
        assert result.consent_status.confirmed is True

    @pytest.mark.asyncio
    async def test_process_with_empty_transcript(self, empty_transcript):
        """Calling process with empty transcript returns HealthcareNote."""
        extraction = ExtractionService.__new__(ExtractionService)
        service = HealthcareService(extraction_service=extraction)

        mock_extraction = AsyncMock()
        mock_extraction.extract.return_value = ExtractionResult(
            summary="",
            key_points=[],
            action_items=[],
            decisions=[],
        )
        service.extraction_service = mock_extraction

        result = await service.process(empty_transcript)
        assert isinstance(result, HealthcareNote)
        assert result.soap.subjective == ""
