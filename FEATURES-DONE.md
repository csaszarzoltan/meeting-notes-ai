# Features Done

## Features Done (this pass)
- Regression isolation fixes: portable subprocess tests, async helper isolation, hermetic Calendar status, session reset API, and completed API-key tests without obsolete strict xfail markers.
- Deterministic diarization contract: dictionary and model segment representations use the same positive-overlap semantics.
- Release verification groups: API/auth/session, transcription/review/Calendar, and sharing/storage/UI groups pass independently.

## Sources
- research-findings.md items addressed: trusted record reliability and release confidence
- implementation-plan.md requirements addressed: PR-7 regression stabilization, partially completed
- user stories covered: regression support for US-001, US-003, US-007, US-009
- CHANGELOG.md section this maps to: 1.7.0
