import pytest

from meeting_notes_ai.services.governance.artifacts import build_lineage, register_idempotent
from meeting_notes_ai.services.governance.deletion import deletion_outcomes


def test_us_007_ac_1_lineage_is_tenant_scoped_and_idempotent():
    nodes = []
    a = {
        "id": "a",
        "team_id": "t",
        "source_key": "audio",
        "kind": "audio",
        "location_class": "object_storage",
    }
    assert register_idempotent(nodes, a) is register_idempotent(nodes, a)
    nodes.append(
        {
            "id": "foreign",
            "team_id": "x",
            "source_key": "x",
            "kind": "audio",
            "location_class": "database",
        }
    )
    assert [n["id"] for n in build_lineage(nodes, [], "t")["nodes"]] == ["a"]


def test_us_007_ac_2_external_is_never_falsely_deleted():
    out = deletion_outcomes([{"id": "x", "kind": "task", "location_class": "external"}])
    assert out[0]["outcome"] == "external_remediation_required"


def test_us_007_ac_3_cycle_is_rejected():
    nodes = [{"id": "a", "team_id": "t"}, {"id": "b", "team_id": "t"}]
    with pytest.raises(ValueError, match="acyclic"):
        build_lineage(
            nodes, [{"parent_id": "a", "child_id": "b"}, {"parent_id": "b", "child_id": "a"}], "t"
        )


def test_us_007_acyclic_edge_and_internal_outcomes():
    nodes = [{"id": "a", "team_id": "t"}, {"id": "b", "team_id": "t"}]
    graph = build_lineage(nodes, [{"parent_id": "a", "child_id": "b"}], "t")
    assert len(graph["edges"]) == 1
    outcomes = deletion_outcomes(
        [
            {"id": "a", "kind": "audio", "location_class": "database"},
            {"id": "b", "kind": "export", "location_class": "database", "deleted_at": "yes"},
        ]
    )
    assert {item["outcome"] for item in outcomes} == {"deleted", "already_absent"}
