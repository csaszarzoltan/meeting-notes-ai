"""Healthcare mode — SOAP note formatting with HIPAA markers."""

from __future__ import annotations

from meeting_notes_ai.models import (
    ConsentStatus,
    ExtractionResult,
    HealthcareNote,
    HIPAAMarker,
    MeetingMode,
    SOAPNote,
)
from meeting_notes_ai.services.extraction import ExtractionService


class HealthcareService:
    """Transform transcript into SOAP note with HIPAA compliance."""

    def __init__(self, extraction_service: ExtractionService) -> None:
        self.extraction_service = extraction_service

    async def process(
        self,
        transcript: str,
        patient_id: str | None = None,
        consent_confirmed: bool = False,
    ) -> HealthcareNote:
        """Process transcript into structured healthcare note.

        Uses the extraction service to extract structured data, then
        formats it into SOAP note format with HIPAA compliance markers.
        """
        extraction: ExtractionResult = await self.extraction_service.extract(
            transcript, mode=MeetingMode.HEALTHCARE
        )

        # Extract SOAP components from the extraction result
        # In a full implementation, the extraction would provide structured SOAP data
        soap = SOAPNote(
            subjective=_extract_subjective(extraction),
            objective=_extract_objective(extraction),
            assessment=_extract_assessment(extraction),
            plan=_extract_plan(extraction),
        )

        # Generate HIPAA markers based on content
        hipaa_markers = _generate_hipaa_markers(extraction, patient_id)

        # Consent status
        consent = ConsentStatus(
            confirmed=consent_confirmed,
            note="Consent confirmed by provider" if consent_confirmed else "Consent not confirmed",
        )

        return HealthcareNote(
            soap=soap,
            hipaa_markers=hipaa_markers,
            consent_status=consent,
            de_identified=patient_id is None,
        )


def _extract_subjective(result: ExtractionResult) -> str:
    """Extract subjective content (patient-reported symptoms)."""
    # Use key_points as subjective symptoms if available
    if result.key_points:
        return "Patient reported: " + "; ".join(result.key_points[:3])
    return result.summary


def _extract_objective(result: ExtractionResult) -> str:
    """Extract objective clinical observations."""
    if result.decisions:
        return "Clinical observations: " + "; ".join(result.decisions[:3])
    return ""


def _extract_assessment(result: ExtractionResult) -> str:
    """Extract clinical assessment."""
    if result.key_points and len(result.key_points) > 3:
        return "Assessment based on: " + "; ".join(result.key_points[3:6])
    return result.summary


def _extract_plan(result: ExtractionResult) -> str:
    """Extract treatment plan from action items."""
    if result.action_items:
        plans = [
            f"{item.assignee or 'Provider'}: {item.description}" for item in result.action_items
        ]
        return "\n".join(plans)
    return ""


def _generate_hipaa_markers(result: ExtractionResult, patient_id: str | None) -> list[HIPAAMarker]:
    """Generate HIPAA compliance markers based on extracted content."""
    markers: list[HIPAAMarker] = []

    if patient_id:
        markers.append(
            HIPAAMarker(
                field="patient_id",
                risk_level="high",
                recommendation="Include only with explicit consent in medical records",
            )
        )

    if result.summary:
        markers.append(
            HIPAAMarker(
                field="summary",
                risk_level="medium",
                recommendation="De-identify before sharing outside treatment context",
            )
        )

    for item in result.action_items:
        if item.assignee:
            markers.append(
                HIPAAMarker(
                    field="action_item_assignee",
                    risk_level="low",
                    recommendation="No PHI typically present",
                )
            )
            break

    return markers
