"""Interface and behavioral tests for v0.2.0 PDF/export enhancements.

Tests PDF export via weasyprint and batch ZIP export functionality.
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestExportInterface:
    """Verify export module has PDF and batch ZIP methods."""

    def test_export_format_has_pdf(self):
        from meeting_notes_ai.models import ExportFormat

        assert ExportFormat.PDF is not None
        assert ExportFormat.PDF.value == "pdf"

    def test_export_pdf_method_exists(self):
        from meeting_notes_ai.services.export import ExportService

        assert hasattr(ExportService, "export_pdf")

    def test_export_pdf_signature(self):
        from meeting_notes_ai.services.export import ExportService

        sig = signature(ExportService.export_pdf)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "result" in params
        assert "mode" in params

    def test_export_pdf_returns_bytes(self):
        from meeting_notes_ai.services.export import ExportService

        sig = signature(ExportService.export_pdf)
        ann = sig.return_annotation
        assert ann is bytes or "bytes" in str(ann)

    def test_export_batch_zip_method_exists(self):
        from meeting_notes_ai.services.export import ExportService

        assert hasattr(ExportService, "export_batch_zip")

    def test_export_batch_zip_signature(self):
        from meeting_notes_ai.services.export import ExportService

        sig = signature(ExportService.export_batch_zip)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "results" in params
        assert "modes" in params
        assert "formats" in params

    def test_export_batch_zip_returns_bytes(self):
        from meeting_notes_ai.services.export import ExportService

        sig = signature(ExportService.export_batch_zip)
        ann = sig.return_annotation
        assert ann is bytes or "bytes" in str(ann)

    def test_export_to_file_signature_updated(self):
        """export_to_file should still work with existing signature."""
        from meeting_notes_ai.services.export import ExportService

        sig = signature(ExportService.export_to_file)
        params = list(sig.parameters.keys())
        assert "result" in params
        assert "format" in params
        assert "mode" in params


# ── Behavioral Tests (real export behavior) ──────────────────────────────────


class TestExportBehavioral:
    """Verify export methods produce real output."""

    def test_export_batch_zip_returns_non_empty_bytes(self):
        """export_batch_zip returns a valid ZIP archive."""
        from meeting_notes_ai.models import MeetingMode
        from meeting_notes_ai.services.export import ExportService

        service = ExportService()
        results = [
            {"filename": "meeting1.json", "summary": "First meeting"},
            {"filename": "meeting2.json", "summary": "Second meeting"},
        ]
        modes = [MeetingMode.GENERAL, MeetingMode.GENERAL]
        zip_bytes = service.export_batch_zip(results=results, modes=modes)

        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 20  # ZIP format has at least 22 bytes

        # Verify it's a valid ZIP by looking at magic bytes
        assert zip_bytes[:2] == b"PK"

    def test_export_batch_zip_defaults_to_all_formats(self):
        """export_batch_zip includes json, md, pdf by default."""
        from meeting_notes_ai.models import MeetingMode
        from meeting_notes_ai.services.export import ExportService

        service = ExportService()
        result = {"filename": "test.json", "summary": "Test", "action_items": []}
        zip_bytes = service.export_batch_zip(
            results=[result],
            modes=[MeetingMode.GENERAL],
        )

        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            # Should contain at least .json and .md (PDF may be skipped)
            assert any(n.endswith(".json") for n in names)
            assert any(n.endswith(".md") for n in names)

    def test_export_batch_zip_with_formats_filter(self):
        """export_batch_zip respects format filter."""
        from meeting_notes_ai.models import MeetingMode
        from meeting_notes_ai.services.export import ExportService

        service = ExportService()
        result = {"filename": "test.json", "summary": "Test"}
        zip_bytes = service.export_batch_zip(
            results=[result],
            modes=[MeetingMode.GENERAL],
            formats=["json"],
        )

        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert len(names) == 1
            assert names[0].endswith(".json")
