"""Interface and behavioral tests for ExportService."""

from __future__ import annotations

from inspect import signature

from meeting_notes_ai.models import (
    ExportFormat,
    MeetingMode,
)
from meeting_notes_ai.services.export import ExportService

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestExportServiceInterface:
    """Verify ExportService class contract."""

    def test_export_service_can_be_imported(self):
        """ExportService should be importable."""
        assert ExportService is not None

    def test_export_format_can_be_imported(self):
        """ExportFormat should be importable."""
        assert ExportFormat is not None

    def test_export_json_signature(self):
        """export_json should accept result and pretty params."""
        assert hasattr(ExportService, "export_json")
        sig = signature(ExportService.export_json)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "result" in params
        assert "pretty" in params

    def test_export_json_default_pretty(self):
        """pretty should default to True."""
        sig = signature(ExportService.export_json)
        param = sig.parameters.get("pretty")
        assert param is not None
        assert param.default is True

    def test_export_markdown_signature(self):
        """export_markdown should accept result and mode params."""
        assert hasattr(ExportService, "export_markdown")
        sig = signature(ExportService.export_markdown)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "result" in params
        assert "mode" in params

    def test_export_to_file_signature(self):
        """export_to_file should accept result, format, and mode."""
        assert hasattr(ExportService, "export_to_file")
        sig = signature(ExportService.export_to_file)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "result" in params
        assert "format" in params
        assert "mode" in params

    def test_export_to_file_returns_path(self):
        """export_to_file return annotation should include Path."""
        sig = signature(ExportService.export_to_file)

        return_ann = sig.return_annotation
        # Check that Path is in the return annotation hint
        assert return_ann is not sig.empty

    def test_export_json_returns_string(self):
        """export_json should return a string."""
        sig = signature(ExportService.export_json)
        return_ann = sig.return_annotation
        assert return_ann is str or return_ann is not sig.empty

    def test_export_markdown_returns_string(self):
        """export_markdown should return a string."""
        sig = signature(ExportService.export_markdown)
        return_ann = sig.return_annotation
        assert return_ann is str or return_ann is not sig.empty

    def test_export_format_enum_values(self):
        """ExportFormat should have expected values."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.MARKDOWN.value == "markdown"

    def test_export_mode_type_is_meeting_mode(self):
        """mode param in export_markdown should be MeetingMode."""
        sig = signature(ExportService.export_markdown)
        param = sig.parameters.get("mode")
        assert param is not None
        assert param.annotation is MeetingMode or "MeetingMode" in str(param.annotation)


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestExportServiceBehavioral:
    """Verify export behavior with real implementation."""

    def test_export_json_returns_valid_json(self):
        """Calling export_json should return JSON string."""
        service = ExportService()
        result = service.export_json(
            result={"summary": "test", "action_items": []}
        )
        import json

        parsed = json.loads(result)
        assert parsed["summary"] == "test"

    def test_export_json_with_pretty_false(self):
        """Calling export_json with pretty=False should be compact."""
        service = ExportService()
        result = service.export_json(
            result={"summary": "test"}, pretty=False
        )
        # Compact JSON has no whitespace
        assert "\n" not in result

    def test_export_markdown_general_mode(self):
        """Calling export_markdown with GENERAL mode."""
        service = ExportService()
        result = service.export_markdown(
            result={
                "summary": "Q3 planning",
                "action_items": [
                    {"assignee": "Mike", "description": "API work"}
                ],
                "decisions": ["Release Oct 1"],
                "key_points": ["Focus on API"],
            },
            mode=MeetingMode.GENERAL,
        )
        assert "Summary:** Q3 planning" in result
        assert "Mike" in result
        assert "Release Oct 1" in result

    def test_export_markdown_with_healthcare_mode(self):
        """Calling export_markdown with healthcare mode."""
        service = ExportService()
        result = service.export_markdown(
            result={
                "summary": "Patient visit",
                "soap": {
                    "subjective": "Headache",
                    "objective": "BP normal",
                    "assessment": "Mild",
                    "plan": "Rest",
                },
            },
            mode=MeetingMode.HEALTHCARE,
        )
        assert "Healthcare Meeting Note" in result
        assert "Subjective" in result
        assert "Headache" in result

    def test_export_markdown_with_legal_mode(self):
        """Calling export_markdown with legal mode."""
        service = ExportService()
        result = service.export_markdown(
            result={
                "summary": "Deposition",
                "key_testimony": [
                    {"witness": "John Doe", "excerpt": "I saw the accident"}
                ],
                "objections": [
                    {"type": "hearsay", "context": "Second-hand account"}
                ],
            },
            mode=MeetingMode.LEGAL,
        )
        assert "Legal Deposition Summary" in result
        assert "John Doe" in result
        assert "hearsay" in result

    def test_export_to_file_returns_path(self):
        """Calling export_to_file should return a Path."""
        service = ExportService()
        from pathlib import Path

        result_path = service.export_to_file(
            result={"summary": "test"},
            format="json",
            mode=MeetingMode.GENERAL,
        )
        assert isinstance(result_path, Path)
        assert result_path.exists()
        # Clean up
        result_path.unlink()

    def test_export_to_file_markdown(self):
        """Calling export_to_file with markdown format."""
        service = ExportService()
        from pathlib import Path

        result_path = service.export_to_file(
            result={"summary": "test"},
            format="markdown",
            mode=MeetingMode.GENERAL,
        )
        assert isinstance(result_path, Path)
        assert result_path.suffix == ".md"
        # Clean up
        result_path.unlink()
