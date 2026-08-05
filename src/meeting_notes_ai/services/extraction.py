"""LLM extraction service — structured data from transcripts."""

from __future__ import annotations

import json
import os

from openai import AsyncOpenAI

from meeting_notes_ai.models import ActionItem, ExtractionResult, MeetingMode


class ExtractionService:
    """Extract structured action items, decisions, key points from transcript."""

    def __init__(self, provider: str, model: str = "gpt-4o", api_key: str | None = None) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazy-init the LLM client."""
        if self._client is None:
            key = self.api_key or os.getenv("OPENAI_API_KEY", "")
            self._client = AsyncOpenAI(api_key=key)
        return self._client

    async def extract(
        self,
        transcript: str,
        mode: MeetingMode = MeetingMode.GENERAL,
    ) -> ExtractionResult:
        """Extract structured data from transcript.

        Builds a mode-specific prompt, calls the LLM, and parses the response.
        """
        prompt = await self._build_prompt(transcript, mode)
        client = self._get_client()

        raw = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise meeting note extractor. "
                    "Return ONLY valid JSON matching the requested schema. "
                    "No markdown, no commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        if not raw.choices:
            return ExtractionResult(
                summary="LLM returned no response choices",
                raw_llm_response="",
            )

        response_text = raw.choices[0].message.content or "{}"
        return await self._parse_response(response_text)

    async def _build_prompt(self, transcript: str, mode: MeetingMode) -> str:
        """Build the LLM prompt for extraction based on meeting mode."""
        base_prompt = f"""Extract structured information from the following meeting transcript.

Transcript:
{transcript}

Return a JSON object with these fields:
- "summary": A brief one-paragraph summary of the meeting
- "action_items": A list of objects with "assignee" (string or null),
- "decisions": A list of strings representing decisions made
- "key_points": A list of strings representing key discussion points
"""
        if mode == MeetingMode.HEALTHCARE:
            base_prompt += """
Additionally, format for healthcare context. Identify:
- Patient-reported symptoms (subjective)
- Clinical observations (objective)
- Clinical assessment
- Treatment plan
"""
        elif mode == MeetingMode.LEGAL:
            base_prompt += """
Additionally, format for legal/deposition context. Identify:
- Witness statements and key testimony
- Objections raised and their rulings
- Case metadata references
"""

        return base_prompt

    async def _parse_response(self, raw: str) -> ExtractionResult:
        """Parse LLM response into ExtractionResult."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ExtractionResult(
                summary="Failed to parse LLM response",
                raw_llm_response=raw,
            )

        action_items_raw = data.get("action_items", [])
        action_items = [
            ActionItem(
                assignee=item.get("assignee"),
                description=item.get("description", ""),
                deadline=item.get("deadline"),
            )
            for item in action_items_raw
        ]

        return ExtractionResult(
            action_items=action_items,
            decisions=data.get("decisions", []),
            key_points=data.get("key_points", []),
            summary=data.get("summary", ""),
            raw_llm_response=raw,
        )
