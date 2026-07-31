"""Re-export PHIRedactor for backward compatibility.

The canonical location is meeting_notes_ai.hipaa.phi_patterns.
This module exists for behavioral tests that import from ``hipaa.redactor``.
"""

from meeting_notes_ai.hipaa.phi_patterns import PHIMatch, PHIRedactionResult, PHIRedactor

__all__ = ["PHIRedactor", "PHIMatch", "PHIRedactionResult"]
