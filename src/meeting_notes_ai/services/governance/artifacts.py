"""In-memory graph rules shared by persistence and tests."""


def build_lineage(nodes: list[dict], edges: list[dict], team_id: str) -> dict:
    safe = [n for n in nodes if n["team_id"] == team_id]
    ids = {n["id"] for n in safe}
    safe_edges = [e for e in edges if e["parent_id"] in ids and e["child_id"] in ids]
    # Kahn cycle check
    incoming = {i: 0 for i in ids}
    for e in safe_edges:
        incoming[e["child_id"]] += 1
    queue = [i for i, v in incoming.items() if v == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for e in safe_edges:
            if e["parent_id"] == cur:
                incoming[e["child_id"]] -= 1
                if incoming[e["child_id"]] == 0:
                    queue.append(e["child_id"])
    if seen != len(ids):
        raise ValueError("Artifact lineage must be acyclic")
    return {"nodes": safe, "edges": safe_edges, "warnings": []}


def register_idempotent(nodes: list[dict], artifact: dict) -> dict:
    existing = next(
        (
            n
            for n in nodes
            if n["team_id"] == artifact["team_id"] and n["source_key"] == artifact["source_key"]
        ),
        None,
    )
    if existing:
        return existing
    nodes.append(artifact)
    return artifact
