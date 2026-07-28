"""Interface and behavioral tests for v0.2.0 batch processing endpoints.

Tests POST /api/v1/batches (upload + process) and GET /api/v1/batches/{id} (status).
"""

from __future__ import annotations

from inspect import signature

import pytest

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestBatchInterface:
    """Verify batch endpoint module with correct contracts."""

    def test_batches_module_importable(self):
        from meeting_notes_ai.routes.batches import router

        assert router is not None
        assert router.prefix == "/api/v1/batches"

    def test_batches_router_has_tags(self):
        from meeting_notes_ai.routes.batches import router

        assert "batches" in router.tags

    def test_batch_create_response_importable(self):
        from meeting_notes_ai.routes.batches import BatchCreateResponse

        assert BatchCreateResponse is not None

    def test_batch_create_response_fields(self):
        from meeting_notes_ai.routes.batches import BatchCreateResponse

        fields = BatchCreateResponse.model_fields
        assert "batch_id" in fields
        assert "status" in fields
        assert "file_count" in fields
        assert "created_at" in fields

    def test_batch_status_response_importable(self):
        from meeting_notes_ai.routes.batches import BatchStatusResponse

        assert BatchStatusResponse is not None

    def test_batch_status_response_fields(self):
        from meeting_notes_ai.routes.batches import BatchStatusResponse

        fields = BatchStatusResponse.model_fields
        assert "batch_id" in fields
        assert "status" in fields
        assert "total_files" in fields
        assert "completed_files" in fields
        assert "failed_files" in fields
        assert "file_results" in fields

    def test_batch_file_result_summary_importable(self):
        from meeting_notes_ai.routes.batches import BatchFileResultSummary

        assert BatchFileResultSummary is not None

    def test_batch_file_result_summary_fields(self):
        from meeting_notes_ai.routes.batches import BatchFileResultSummary

        fields = BatchFileResultSummary.model_fields
        assert "filename" in fields
        assert "status" in fields
        assert "meeting_id" in fields
        assert "error_message" in fields

    def test_batch_export_response_importable(self):
        from meeting_notes_ai.routes.batches import BatchExportResponse

        assert BatchExportResponse is not None

    def test_batch_export_response_fields(self):
        from meeting_notes_ai.routes.batches import BatchExportResponse

        fields = BatchExportResponse.model_fields
        assert "filename" in fields
        assert "content_type" in fields
        assert "content_length" in fields

    # ── Route registration ────────────────────────────────────────────────────

    def test_create_batch_route_registered(self):
        from meeting_notes_ai.routes.batches import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        assert any("/api/v1/batches" in r.path for r in routes)

    def test_batch_status_route_registered(self):
        from meeting_notes_ai.routes.batches import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        assert any("{batch_id}" in (getattr(r, "path_format", r.path)) for r in routes)

    def test_create_batch_is_post(self):
        from meeting_notes_ai.routes.batches import router

        for r in router.routes:
            if hasattr(r, "path") and r.path == "/api/v1/batches":
                if hasattr(r, "methods"):
                    assert "POST" in r.methods
                    return
        for r in router.routes:
            methods = getattr(r, "methods", set())
            if "POST" in methods:
                return
        pytest.fail("POST route not found on batch router")

    def test_batch_status_is_get(self):
        from meeting_notes_ai.routes.batches import router

        for r in router.routes:
            methods = getattr(r, "methods", set())
            if "GET" in methods:
                return
        pytest.fail("GET route not found on batch router")

    def test_upload_accepts_files_param(self):
        from meeting_notes_ai.routes.batches import create_batch

        sig = signature(create_batch)
        assert "files" in sig.parameters

    def test_upload_accepts_team_id_param(self):
        from meeting_notes_ai.routes.batches import create_batch

        sig = signature(create_batch)
        assert "team_id" in sig.parameters

    def test_upload_is_async(self):
        import inspect

        from meeting_notes_ai.routes.batches import create_batch

        assert inspect.iscoroutinefunction(create_batch)

    def test_get_batch_status_is_async(self):
        import inspect

        from meeting_notes_ai.routes.batches import get_batch_status

        assert inspect.iscoroutinefunction(get_batch_status)


# ── Behavioral Tests (model/response tests) ──────────────────────────────────


class TestBatchBehavioral:
    """Verify batch schemas and response models work correctly."""

    def test_batch_create_response_defaults(self):
        """BatchCreateResponse has correct defaults."""
        from meeting_notes_ai.routes.batches import BatchCreateResponse

        from meeting_notes_ai.db.models import BatchStatus

        resp = BatchCreateResponse(
            batch_id="b-1",
            file_count=3,
            status=BatchStatus.PENDING,
        )
        assert resp.batch_id == "b-1"
        assert resp.file_count == 3
        assert resp.status.value == "pending"

    def test_batch_status_response_defaults(self):
        """BatchStatusResponse has correct defaults."""
        from meeting_notes_ai.routes.batches import BatchStatusResponse

        from meeting_notes_ai.db.models import BatchStatus

        resp = BatchStatusResponse(
            batch_id="b-1",
            status=BatchStatus.PENDING,
        )
        assert resp.batch_id == "b-1"
        assert resp.total_files == 0
        assert resp.file_results == []

    def test_batch_file_result_summary_defaults(self):
        """BatchFileResultSummary has correct types."""
        from meeting_notes_ai.routes.batches import BatchFileResultSummary

        from meeting_notes_ai.db.models import BatchStatus

        summary = BatchFileResultSummary(filename="test.mp3", status=BatchStatus.PENDING)
        assert summary.filename == "test.mp3"
        assert summary.meeting_id is None
        assert summary.error_message is None

    def test_batch_export_response_defaults(self):
        """BatchExportResponse works correctly."""
        from meeting_notes_ai.routes.batches import BatchExportResponse

        resp = BatchExportResponse(filename="export.json", content_type="application/json")
        assert resp.filename == "export.json"
        assert resp.content_type == "application/json"

    def test_create_batch_handler_signature(self):
        """create_batch handler has correct signature with dependencies."""
        from meeting_notes_ai.routes.batches import create_batch

        sig = signature(create_batch)
        assert "files" in sig.parameters
        assert "user" in sig.parameters or "request" in sig.parameters
