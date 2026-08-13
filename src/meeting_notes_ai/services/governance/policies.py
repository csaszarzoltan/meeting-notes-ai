"""Fail-closed provider and storage policy evaluator."""


def evaluate_provider(policy: dict, provider: str, available: bool = True) -> dict:
    allowed = policy.get("allowed_providers", [])
    if provider not in allowed:
        return {"outcome": "blocked", "code": "PROVIDER_NOT_ALLOWED"}
    if not available:
        return {"outcome": "paused", "code": "PROVIDER_UNAVAILABLE"}
    return {"outcome": "allowed", "code": "OK"}
