"""Acceptance tests for the v0.6 user workflow improvements.

Written before implementation to document intended behavior.
"""

from fastapi.testclient import TestClient

from meeting_notes_ai.main import app
from meeting_notes_ai.services.workflow import ProcessingPolicy, resolve_processing_policy


def test_healthcare_defaults_to_phi_redaction_and_review():
    policy = resolve_processing_policy(mode="healthcare", phi_redaction=None)
    assert policy == ProcessingPolicy(phi_redaction=True, review_required=True)


def test_general_mode_preserves_opt_in_redaction():
    policy = resolve_processing_policy(mode="general", phi_redaction=True)
    assert policy.phi_redaction is True
    assert policy.review_required is False


def test_invalid_mode_has_actionable_validation_error():
    client = TestClient(app)
    response = client.post(
        "/api/v1/meetings",
        files={"file": ("sample.wav", b"audio", "audio/wav")},
        data={"mode": "unknown"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_mode"
    assert response.json()["detail"]["supported_modes"] == ["general", "healthcare", "legal"]


def test_empty_upload_is_rejected_before_external_processing():
    client = TestClient(app)
    response = client.post(
        "/api/v1/meetings",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_file"


def test_accessible_product_app_is_available():
    client = TestClient(app)
    response = client.get("/app")
    assert response.status_code == 200
    html = response.text
    assert '<main id="main-content"' in html
    assert 'aria-live="polite"' in html
    assert '<label for="meeting-file">' in html
    assert 'id="phi-redaction"' in html
    assert "Skip to main content" in html


def test_health_reports_current_version():
    client = TestClient(app)
    assert client.get("/healthz").json()["version"] == app.version


def test_healthcare_pipeline_redacts_and_marks_review(monkeypatch):
    from unittest.mock import AsyncMock

    from meeting_notes_ai.models import ExtractionResult, HealthcareNote, TranscriptionResult
    from meeting_notes_ai.routes import meetings

    services = {
        "transcription": type(
            "T",
            (),
            {
                "transcribe": AsyncMock(
                    return_value=TranscriptionResult(text="Patient John Smith SSN 123-45-6789")
                )
            },
        )(),
        "extraction": type(
            "E", (), {"extract": AsyncMock(return_value=ExtractionResult(summary="Consultation"))}
        )(),
        "healthcare": type("H", (), {"process": AsyncMock(return_value=HealthcareNote())})(),
        "legal": object(),
        "export": object(),
    }
    monkeypatch.setattr(meetings, "_build_services", lambda: services)
    response = TestClient(app).post(
        "/api/v1/meetings",
        files={"file": ("visit.wav", b"audio", "audio/wav")},
        data={"mode": "healthcare", "consent_confirmed": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["phi_redacted"] is True
    assert body["redaction_matches"] >= 1
    assert "123-45-6789" not in body["transcript"]
    assert body["review_status"] == "needs_review"
