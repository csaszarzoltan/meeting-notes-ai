# Features Done

## Features Done (this pass)
- Release regression gate: the complete 1,400-test suite now runs with zero failures and zero errors from a clean data directory.
- API-key order independence: the empty-list scenario removes test-created keys through the public API instead of relying on method order.
- Verification hygiene: changed-scope Ruff checks, Python compilation, frontend type-check/build, backend startup, and health checks pass.

## Sources
- research-findings.md items addressed: release reliability and trusted workflow confidence
- implementation-plan.md requirements addressed: PR-7 regression stabilization
- user stories covered: regression support for all selected stories
- CHANGELOG.md section this maps to: 1.7.1
