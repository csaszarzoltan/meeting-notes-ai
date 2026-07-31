#!/usr/bin/env python3
"""BAA example — generate a Business Associate Agreement and store it.

Uses the library API:

    from meeting_notes_ai.hipaa.baa import BAAService

The template covers the HIPAA §164.504(e) required clauses (permitted uses,
safeguards, breach notification, return/destruction of PHI, etc.).

Run from the repository root:

    PYTHONPATH=src .venv/bin/python examples/hipaa_baa_generate.py
"""

import asyncio

from meeting_notes_ai.hipaa.baa import BAAService


async def main() -> None:
    svc = BAAService()

    print("== Generate template (markdown) ==")
    markdown = await svc.generate_template(
        org_name="Acme Health Systems",
        ba_name="CloudNotes Inc.",
        effective_date="2026-08-01",
    )
    print(markdown[:400])
    print("...")

    print("\n== Store agreement (immutable) ==")
    agreement_id = await svc.store_agreement(
        org_name="Acme Health Systems",
        ba_name="CloudNotes Inc.",
        signed_by="Dr. Jane Smith",
    )
    print(f"  agreement id: {agreement_id}")

    print("\n== Retrieve and list ==")
    agreement = await svc.get_agreement(agreement_id)
    print(
        f"  {agreement.org_name} <-> {agreement.ba_name}  "
        f"status={agreement.status}  effective={agreement.effective_date}"
    )
    summaries = await svc.list_agreements()
    print(f"  total stored agreements: {len(summaries)}")

    print("\n== PDF export ==")
    pdf_bytes = await svc.generate_pdf(agreement_id)
    print(f"  pdf bytes: {len(pdf_bytes)} (header={pdf_bytes[:8]!r})")


if __name__ == "__main__":
    asyncio.run(main())
