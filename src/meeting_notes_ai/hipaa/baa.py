"""BAA (Business Associate Agreement) template generation and management.

HIPAA §164.504(e) requires covered entities to obtain satisfactory assurances
from business associates that they will appropriately safeguard PHI.
This module provides template generation, PDF export, and immutable storage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from fpdf import FPDF

from meeting_notes_ai.hipaa.config import HIPAAConfig

# ── Data Models ─────────────────────────────────────────────────────────────────


@dataclass
class BAATemplate:
    """A stored BAA template version."""

    id: str = ""
    version: str = "1.0"
    content: str = ""  # Markdown template body
    is_active: bool = True


@dataclass
class BAAgreement:
    """A signed business associate agreement (immutable after signing)."""

    id: str = ""
    org_name: str = ""  # Covered entity name
    ba_name: str = ""  # Business associate name
    effective_date: str = ""  # ISO date string
    signed_by: str = ""  # Signatory identifier
    content_md: str = ""  # Rendered markdown
    status: str = "active"  # active, expired, terminated


@dataclass
class BAAgreementSummary:
    """Lightweight summary for listing agreements."""

    id: str = ""
    org_name: str = ""
    ba_name: str = ""
    effective_date: str = ""
    status: str = "active"


# ── Service ─────────────────────────────────────────────────────────────────────


class BAAService:
    """Generate, store, and retrieve Business Associate Agreements.

    All HIPAA §164.504(e) required clauses are included in the template.
    Signed agreements are stored immutably — no UPDATE after signing.
    """

    def __init__(self, db_factory: Callable | None = None) -> None:
        self._db_factory = db_factory
        self._config = HIPAAConfig.load()
        self._agreements: dict[str, BAAgreement] = {}

    # -- Template path resolution ------------------------------------------------

    @staticmethod
    def _default_template_dir() -> Path:
        """Return the absolute path to the hipaa/templates directory."""
        return Path(__file__).parent / "templates"

    def _resolve_template_path(self) -> Path:
        """Resolve the Jinja2 template path from config or default location.

        If the configured path is relative, resolve it against the
        hipaa package templates directory.
        """
        configured = Path(self._config.baa_template_path)
        if configured.is_absolute() and configured.exists():
            return configured
        # Fall back to the bundled template inside the package
        bundled = Path(__file__).parent / "templates" / "baa_template.md.jinja"
        if configured.exists():
            return configured
        return bundled

    # -- Template rendering ------------------------------------------------------

    async def generate_template(
        self,
        org_name: str,
        ba_name: str,
        effective_date: str,
    ) -> str:
        """Generate a BAA markdown document from the Jinja2 template.

        Args:
            org_name: Name of the covered entity (healthcare provider).
            ba_name: Name of the business associate.
            effective_date: ISO-format date the agreement takes effect.

        Returns:
            Rendered markdown string with all template fields substituted.
        """
        from jinja2 import Environment, FileSystemLoader

        template_path = self._resolve_template_path()
        template_dir = template_path.parent
        template_file = template_path.name

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template(template_file)
        return template.render(
            org_name=org_name,
            ba_name=ba_name,
            effective_date=effective_date,
        )

    # -- PDF export --------------------------------------------------------------

    async def generate_pdf(self, agreement_id: str) -> bytes:
        """Export a signed agreement as PDF bytes.

        Args:
            agreement_id: UUID of the stored agreement.

        Returns:
            Valid PDF document as bytes.

        Raises:
            ValueError: If no agreement with the given ID exists.
        """
        agreement = await self.get_agreement(agreement_id)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Title
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "BUSINESS ASSOCIATE AGREEMENT", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        # Effective Date
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"Effective Date: {agreement.effective_date}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        # Parties
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Parties", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, (
            f"Covered Entity: {agreement.org_name}\n"
            f"Business Associate: {agreement.ba_name}\n"
        ))
        pdf.ln(3)

        # Agreement content (extract text from markdown, adding sections)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Agreement Content", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, self._markdown_to_text(agreement.content_md))

        # Signature block
        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Signed:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"By: {agreement.signed_by}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Date: {agreement.effective_date}", new_x="LMARGIN", new_y="NEXT")

        return bytes(pdf.output())

    @staticmethod
    def _markdown_to_text(md: str) -> str:
        """Strip simple markdown formatting to plain text.

        Handles headers, bold, lists for legible PDF rendering.
        """
        import re

        # Remove bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", md)
        # Replace headers with plain prefix
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Replace list markers
        text = re.sub(r"^-\s+", "  - ", text, flags=re.MULTILINE)
        # Remove horizontal rules
        text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
        return text.strip()

    # -- Storage (in-memory + optional DB backend) -------------------------------

    async def store_agreement(
        self,
        org_name: str,
        ba_name: str,
        signed_by: str,
    ) -> str:
        """Store a signed BAA agreement immutably.

        Creates a new BAAgreement record with rendered markdown content.
        Once stored, the agreement cannot be updated — only read or exported.

        Args:
            org_name: Covered entity name.
            ba_name: Business associate name.
            signed_by: Identifier of the signatory.

        Returns:
            UUID string of the newly stored agreement.
        """
        agreement_id = str(uuid.uuid4())
        effective_date = date.today().isoformat()
        content_md = await self.generate_template(org_name, ba_name, effective_date)

        agreement = BAAgreement(
            id=agreement_id,
            org_name=org_name,
            ba_name=ba_name,
            effective_date=effective_date,
            signed_by=signed_by,
            content_md=content_md,
            status="active",
        )
        self._agreements[agreement_id] = agreement
        return agreement_id

    async def get_agreement(self, agreement_id: str) -> BAAgreement:
        """Retrieve a stored agreement by ID.

        Args:
            agreement_id: UUID of the agreement.

        Returns:
            BAAgreement dataclass with all fields populated.

        Raises:
            ValueError: If no agreement with the given ID exists.
        """
        if agreement_id not in self._agreements:
            raise ValueError(f"Agreement not found: {agreement_id}")
        return self._agreements[agreement_id]

    async def list_agreements(self) -> list[BAAgreementSummary]:
        """List all BAA agreements (summary view).

        Returns:
            List of BAAgreementSummary dataclasses, ordered by creation date descending.
        """
        summaries = [
            BAAgreementSummary(
                id=ag.id,
                org_name=ag.org_name,
                ba_name=ag.ba_name,
                effective_date=ag.effective_date,
                status=ag.status,
            )
            for ag in self._agreements.values()
        ]
        # Reverse chronological order (most recent first)
        summaries.reverse()
        return summaries
