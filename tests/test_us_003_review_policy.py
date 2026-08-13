from meeting_notes_ai.services.review import evaluate_policy


def test_us_003_ac_1_policy_passes_grounded_approved_claim():
    assert (
        evaluate_policy(
            [{"id": "c", "evidence": ["s"], "status": "approved", "approver_ids": ["u"]}], True, 1
        )
        == []
    )


def test_us_003_ac_2_rejected_claim_blocks_share():
    codes = {
        x["code"]
        for x in evaluate_policy(
            [{"id": "c", "evidence": ["s"], "status": "rejected", "approver_ids": ["u"]}], True, 1
        )
    }
    assert "NOT_APPROVABLE" in codes


def test_us_003_ac_3_fail_closed_when_approval_missing():
    assert (
        evaluate_policy(
            [{"id": "c", "evidence": ["s"], "status": "draft", "approver_ids": []}], True, 1
        )[0]["code"]
        == "APPROVALS_REQUIRED"
    )
