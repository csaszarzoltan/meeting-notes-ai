"""Multi-format export service — JSON, Markdown, PDF, and ZIP batch export."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Literal

from meeting_notes_ai.models import MeetingMode


def _get(d: Any, key: str, default: str = "") -> str:
    """Safely get a key from dict or attribute from object."""
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


class ExportService:
    """Export meeting notes in JSON, Markdown, or PDF format."""

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
                items = result["action_items"]
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except (json.JSONDecodeError, TypeError):
                        items = []
                for item in items:
                    if isinstance(item, dict):
                        assignee = _get(item, "assignee", "Unassigned")
                        desc = _get(item, "description", "")
                        lines.append(f"- **{assignee}**: {desc}")
                    else:
                        lines.append(f"- {item}")
            if result.get("decisions"):
                lines.append("## Decisions\n")
                decisions = result["decisions"]
                if isinstance(decisions, str):
                    try:
                        decisions = json.loads(decisions)
                    except (json.JSONDecodeError, TypeError):
                        decisions = []
                for d in decisions:
                    lines.append(f"- {d}")
            if result.get("key_points"):
                lines.append("## Key Points\n")
                points = result["key_points"]
                if isinstance(points, str):
                    try:
                        points = json.loads(points)
                    except (json.JSONDecodeError, TypeError):
                        points = []
                for p in points:
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
            self.export_json(result) if format == "json" else self.export_markdown(result, mode)
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(content)
            return Path(f.name)

    def export_pdf(
        self,
        result: dict[str, Any],
        mode: MeetingMode,
    ) -> bytes:
        """Export meeting notes as PDF bytes.

        Uses weasyprint to convert HTML (generated from Markdown template)
        to a PDF document.

        Args:
            result: The meeting data dict to export.
            mode: Meeting mode for section formatting.

        Returns:
            PDF file content as bytes.
        """
        import weasyprint

        md_content = self.export_markdown(result, mode)
        # Convert markdown to simple HTML
        html_body = md_content.replace("\n", "<br>\n")
        html = f"<html><body>{html_body}</body></html>"
        pdf_bytes = weasyprint.from_string(html)
        return pdf_bytes  # type: ignore

    def export_batch_zip(
        self,
        results: list[dict[str, Any]],
        modes: list[MeetingMode],
        formats: list[str] | None = None,
    ) -> bytes:
        """Export multiple meeting results as a ZIP archive.

        Each meeting is exported in all requested formats and collected
        into a single ZIP file.

        Args:
            results: List of meeting data dicts to export.
            modes: Meeting modes for each result.
            formats: List of formats to include (default: all).

        Returns:
            ZIP archive content as bytes.
        """
        if formats is None:
            formats = ["json", "markdown", "pdf"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, (result, mode) in enumerate(zip(results, modes)):
                base_name = result.get("filename", result.get("title", f"meeting_{i}"))
                stem = Path(base_name).stem

                if "json" in formats:
                    json_content = self.export_json(result)
                    zf.writestr(f"{stem}.json", json_content)

                if "markdown" in formats:
                    md_content = self.export_markdown(result, mode)
                    zf.writestr(f"{stem}.md", md_content)

                if "pdf" in formats:
                    try:
                        pdf_content = self.export_pdf(result, mode)
                        zf.writestr(f"{stem}.pdf", pdf_content)
                    except Exception:
                        # Skip PDF if weasyprint not available
                        pass

        return buf.getvalue()
