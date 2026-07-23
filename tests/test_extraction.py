"""Interface and behavioral tests for ExtractionService."""

from __future__ import annotations

from inspect import signature
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meeting_notes_ai.models import (
    ActionItem,
    ExtractionResult,
    MeetingMode,
)
from meeting_notes_ai.services.extraction import ExtractionService

# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestExtractionServiceInterface:
    """Verify ExtractionService class contract."""

    def test_extraction_service_can_be_imported(self):
        """ExtractionService should be importable."""
        assert ExtractionService is not None

    def test_extraction_result_can_be_imported(self):
        """ExtractionResult model should be importable."""
        assert ExtractionResult is not None

    def test_action_item_can_be_imported(self):
        """ActionItem model should be importable."""
        assert ActionItem is not None

    def test_extraction_service_init_signature(self):
        """__init__ should accept provider and model params."""
        sig = signature(ExtractionService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "provider" in params
        assert "model" in params

    def test_extract_method_signature(self):
        """extract method should have expected signature."""
        assert hasattr(ExtractionService, "extract")
        sig = signature(ExtractionService.extract)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "transcript" in params
        assert "mode" in params

    def test_extract_is_async(self):
        """extract should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ExtractionService.extract)

    def test_build_prompt_is_async(self):
        """_build_prompt should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ExtractionService._build_prompt)

    def test_parse_response_is_async(self):
        """_parse_response should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(ExtractionService._parse_response)

    def test_extract_default_mode_is_general(self):
        """mode should default to MeetingMode.GENERAL."""
        sig = signature(ExtractionService.extract)
        param = sig.parameters.get("mode")
        assert param is not None
        assert param.default == MeetingMode.GENERAL

    def test_init_default_model_is_gpt4o(self):
        """model should default to 'gpt-4o'."""
        sig = signature(ExtractionService.__init__)
        param = sig.parameters.get("model")
        assert param is not None
        assert param.default == "gpt-4o"

    def test_extraction_result_can_be_instantiated(self):
        """ExtractionResult should be instantiable with fields."""
        result = ExtractionResult(
            action_items=[ActionItem(assignee="John", description="API integration")],
            decisions=["Target October 1st release"],
            key_points=["Focus on API integration first"],
            summary="Q3 roadmap discussion",
        )
        assert len(result.action_items) == 1
        assert result.action_items[0].assignee == "John"
        assert len(result.decisions) == 1
        assert len(result.key_points) == 1
        assert result.summary == "Q3 roadmap discussion"

    def test_extraction_result_defaults(self):
        """ExtractionResult should have sensible defaults."""
        result = ExtractionResult()
        assert result.action_items == []
        assert result.decisions == []
        assert result.key_points == []
        assert result.summary == ""
        assert result.raw_llm_response == ""

    def test_action_item_defaults(self):
        """ActionItem should have optional fields with sensible defaults."""
        item = ActionItem(description="Do something")
        assert item.assignee is None
        assert item.description == "Do something"
        assert item.deadline is None

    def test_action_item_full(self):
        """ActionItem should accept all fields."""
        item = ActionItem(assignee="Alice", description="Write tests", deadline="2026-08-01")
        assert item.assignee == "Alice"
        assert item.deadline == "2026-08-01"

    def test_meeting_mode_enum_values(self):
        """MeetingMode should have expected enum values."""
        assert MeetingMode.GENERAL.value == "general"
        assert MeetingMode.HEALTHCARE.value == "healthcare"
        assert MeetingMode.LEGAL.value == "legal"

    def test_extraction_service_has_build_prompt(self):
        """ExtractionService should have _build_prompt method."""
        assert hasattr(ExtractionService, "_build_prompt")

    def test_extraction_service_has_parse_response(self):
        """ExtractionService should have _parse_response method."""
        assert hasattr(ExtractionService, "_parse_response")


# ── Behavioral Tests (must PASS with real implementation) ─────────────────────


class TestExtractionServiceBehavioral:
    """Verify extraction behavior with real implementation."""

    def test_init_succeeds(self):
        """Instantiating ExtractionService should not raise."""
        service = ExtractionService(provider="openai")
        assert service.provider == "openai"
        assert service.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_extract_calls_llm(self, sample_transcript):
        """Calling extract should use LLM client."""
        service = ExtractionService(provider="openai")

        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"summary": "Q3 roadmap", "action_items": [], "decisions": [], "key_points": []}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract(sample_transcript)

        assert result.summary == "Q3 roadmap"

    @pytest.mark.asyncio
    async def test_extract_with_healthcare_mode(self, sample_transcript):
        """Calling extract with healthcare mode."""
        service = ExtractionService(provider="openai")

        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"summary": "Patient visit", "action_items": [], '
            '"decisions": [], "key_points": ["headache reported"]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract(
                sample_transcript, mode=MeetingMode.HEALTHCARE
            )

        assert "headache" in result.key_points[0]

    @pytest.mark.asyncio
    async def test_extract_with_legal_mode(self, sample_transcript):
        """Calling extract with legal mode."""
        service = ExtractionService(provider="openai")

        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"summary": "Deposition", "action_items": [], '
            '"decisions": ["Objection sustained"], "key_points": []}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract(
                sample_transcript, mode=MeetingMode.LEGAL
            )

        assert "Objection" in result.decisions[0]

    @pytest.mark.asyncio
    async def test_extract_with_empty_transcript(self, empty_transcript):
        """Calling extract with empty transcript."""
        service = ExtractionService(provider="openai")

        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"summary": "", "action_items": [], "decisions": [], "key_points": []}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract(empty_transcript)

        assert result.summary == ""

    @pytest.mark.asyncio
    async def test_build_prompt_returns_string(self, sample_transcript):
        """_build_prompt should return a string."""
        service = ExtractionService.__new__(ExtractionService)
        prompt = await service._build_prompt(
            sample_transcript, MeetingMode.GENERAL
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 10

    @pytest.mark.asyncio
    async def test_parse_response_returns_extraction_result(self):
        """_parse_response should return an ExtractionResult."""
        service = ExtractionService.__new__(ExtractionService)
        raw = '{"summary": "test", "action_items": [], "decisions": [], "key_points": []}'
        result = await service._parse_response(raw)
        assert isinstance(result, ExtractionResult)
        assert result.summary == "test"
