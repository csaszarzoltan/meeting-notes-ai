"""Multi-format export service — JSON and Markdown."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Literal

from meeting_notes_ai.models import MeetingMode


def _get(d: Any, key: str, default: str = "") -> str:
    """Safely get a key from dict or attribute from object."""
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


class ExportService:
    """Export meeting notes in JSON or Markdown format."""

    def export_json(
        self,
        result: dict[str, Any],
        pretty: bool = True,
    ) -> str:
        """Export to JSON string.

        Args:
            result: The meeting data dict to export.
            pretty: If True, indent the JSON output.

        Returns:
            JSON-formatted string.
        """
        indent = 2 if pretty else None
        return json.dumps(result, indent=indent, default=str)

    def export_markdown(
        self,
        result: dict[str, Any],
        mode: MeetingMode,
    ) -> str:
        """Export to Markdown string.

        Args:
            result: The meeting data dict to export.
            mode: Meeting mode for section formatting.

        Returns:
            Markdown-formatted string.
        """
        lines: list[str] = []

        if mode == MeetingMode.HEALTHCARE:
            lines.append("# Healthcare Meeting Note\n")
            lines.append(f"**Summary:** {result.get('summary', '')}\n")
            lines.append("## SOAP Note\n")
            soap = result.get("soap", {})
            for section in ("subjective", "objective", "assessment", "plan"):
                val = soap.get(section, "") if isinstance(soap, dict) else ""
                lines.append(f"### {section.capitalize()}\n{val}\n")
            if result.get("hipaa_markers"):
                lines.append("## HIPAA Compliance\n")
                for m in result["hipaa_markers"]:
                    field = _get(m, "field")
                    risk = _get(m, "risk_level")
                    lines.append(f"- **{field}** (risk: {risk})")

        elif mode == MeetingMode.LEGAL:
            lines.append("# Legal Deposition Summary\n")
            lines.append(f"**Summary:** {result.get('summary', '')}\n")
            if result.get("key_testimony"):
                lines.append("## Key Testimony\n")
                for t in result["key_testimony"]:
                    witness = _get(t, "witness", "Unknown")
                    excerpt = _get(t, "excerpt")
                    lines.append(f"- **{witness}**: {excerpt}")
            if result.get("objections"):
                lines.append("## Objections\n")
                for o in result["objections"]:
                    otype = _get(o, "type")
                    ctx = _get(o, "context")
                    lines.append(f"- **{otype}**: {ctx}")

        else:
            lines.append("# Meeting Notes\n")
            lines.append(f"**Summary:** {result.get('summary', '')}\n")
            if result.get("action_items"):
                lines.append("## Action Items\n")
                for item in result["action_items"]:
                    assignee = _get(item, "assignee", "Unassigned")
                    desc = _get(item, "description")
                    lines.append(f"- **{assignee}**: {desc}")
            if result.get("decisions"):
                lines.append("## Decisions\n")
                for d in result["decisions"]:
                    lines.append(f"- {d}")
            if result.get("key_points"):
                lines.append("## Key Points\n")
                for p in result["key_points"]:
                    lines.append(f"- {p}")

        return "\n".join(lines)

    def export_to_file(
        self,
        result: dict[str, Any],
        format: Literal["json", "markdown"],
        mode: MeetingMode,
    ) -> Path:
        """Export to temp file, return path.

        Args:
            result: The meeting data dict to export.
            format: 'json' or 'markdown'.
            mode: Meeting mode for section formatting.

        Returns:
            Path to the exported file.
        """
        suffix = ".json" if format == "json" else ".md"
        content = (
            self.export_json(result)
            if format == "json"
            else self.export_markdown(result, mode)
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(content)
            return Path(f.name)
