"""BAA (Business Associate Agreement) template generation and management.

HIPAA §164.504(e) requires covered entities to obtain satisfactory assurances
from business associates that they will appropriately safeguard PHI.
This module provides template generation, PDF export, and immutable storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# ── Data Models ─────────────────────────────────────────────────────────────────


@dataclass
class BAATemplate:
    """A stored BAA template version."""
    id: str = ""
    version: str = "1.0"
    content: str = ""          # Markdown template body
    is_active: bool = True


@dataclass
class BAAgreement:
    """A signed business associate agreement (immutable after signing)."""
    id: str = ""
    org_name: str = ""         # Covered entity name
    ba_name: str = ""          # Business associate name
    effective_date: str = ""   # ISO date string
    signed_by: str = ""        # Signatory identifier
    content_md: str = ""       # Rendered markdown
    status: str = "active"     # active, expired, terminated


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
        raise NotImplementedError("BAAService.__init__")

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
        raise NotImplementedError("BAAService.generate_template")

    async def generate_pdf(self, agreement_id: str) -> bytes:
        """Export a signed agreement as PDF bytes.

        Args:
            agreement_id: UUID of the stored agreement.

        Returns:
            Valid PDF document as bytes.
        """
        raise NotImplementedError("BAAService.generate_pdf")

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
        raise NotImplementedError("BAAService.store_agreement")

    async def get_agreement(self, agreement_id: str) -> BAAgreement:
        """Retrieve a stored agreement by ID.

        Args:
            agreement_id: UUID of the agreement.

        Returns:
            BAAgreement dataclass with all fields populated.
        """
        raise NotImplementedError("BAAService.get_agreement")

    async def list_agreements(self) -> list[BAAgreementSummary]:
        """List all BAA agreements (summary view).

        Returns:
            List of BAAgreementSummary dataclasses, ordered by creation date descending.
        """
        raise NotImplementedError("BAAService.list_agreements")
