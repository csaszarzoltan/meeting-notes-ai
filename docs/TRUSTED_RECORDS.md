# Trusted Meeting Records

The trusted-record API is rooted at `/api/v1/trusted`. `GET /meetings/{id}/record` projects historical meetings idempotently and returns canonical segments, claims, evidence, and the latest snapshot. Claim updates require `If-Match`; stale versions return 409 and missing headers return 428. Evidence must remain inside a same-meeting segment. Speaker mapping is bounded to 500 segments and marks approved claims for reapproval. Healthcare and legal publication requires grounding and approval. Published snapshot JSON and SHA-256 are immutable.
