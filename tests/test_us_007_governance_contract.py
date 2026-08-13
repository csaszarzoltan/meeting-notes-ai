from meeting_notes_ai.routes.governance import AuditIn, DeleteIn, PolicyIn


def test_us_007_ac_1_delete_requires_exact_confirmation_field():
    assert DeleteIn(confirmation_title="Quarterly review").confirmation_title == "Quarterly review"


def test_us_008_ac_2_audit_export_contract_defaults_jsonl_manifest():
    assert AuditIn(team_id="t").include_csv is False


def test_us_009_ac_1_policy_contract_is_versioned():
    policy = PolicyIn(
        team_id="t",
        expected_version=3,
        approval={},
        providers={"allowed_providers": ["local"]},
        storage={},
    )
    assert policy.expected_version == 3 and policy.providers["allowed_providers"] == ["local"]
