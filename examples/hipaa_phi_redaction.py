#!/usr/bin/env python3
"""PHI redaction example — scan and redact Protected Health Information.

Mirrors what a healthcare-mode transcription pipeline would apply to a
transcript before storage. Uses the library API:

    from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

Run from the repository root:

    PYTHONPATH=src .venv/bin/python examples/hipaa_phi_redaction.py
"""

from meeting_notes_ai.hipaa.phi_patterns import PHIRedactor

TRANSCRIPT = (
    "Patient John Smith (MRN: 123456789) called Dr. Jane Doe on 555-123-4567. "
    "DOB: 03/14/1985, SSN: 123-45-6789, email: john.smith@example.com"
)


def main() -> None:
    redactor = PHIRedactor()

    print("== Scan ==")
    matches = redactor.scan(TRANSCRIPT)
    for m in matches:
        print(f"  {m.category:8s} {m.risk_level:6s} [{m.start:3d}:{m.end:3d}] {m.matched_text!r}")

    print("\n== Redaction modes ==")
    for mode in ("mask", "hash", "truncate", "annotate"):
        redacted, _ = redactor.redact(TRANSCRIPT, mode=mode)
        print(f"  {mode:9s} -> {redacted}")

    print("\n== Custom pattern ==")
    redactor.add_custom_pattern("medicare_id", r"\b\d{11}\b", "high")
    text = "Medicare ID 12345678901 on file."
    redacted, matches = redactor.redact(text)
    print(f"  {redacted}  ({[m.category for m in matches]})")

    print("\n== Stats ==")
    print(f"  {redactor.get_stats()}")


if __name__ == "__main__":
    main()
