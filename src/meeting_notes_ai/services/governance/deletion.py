"""Idempotent deletion result planning."""


def deletion_outcomes(artifacts: list[dict]) -> list[dict]:
    results = []
    for a in reversed(artifacts):
        outcome = (
            "external_remediation_required"
            if a["location_class"] == "external"
            else ("already_absent" if a.get("deleted_at") else "deleted")
        )
        results.append({"artifact_id": a["id"], "kind": a["kind"], "outcome": outcome})
    return results
