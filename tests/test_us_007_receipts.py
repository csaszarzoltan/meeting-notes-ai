from meeting_notes_ai.services.governance.receipts import sign_receipt, verify_receipt


def test_us_007_ac_3_receipt_detects_one_byte_mutation():
    key = b"x" * 32
    receipt = sign_receipt({"job_id": "j", "results": []}, key)
    assert verify_receipt(receipt, key)
    receipt["job_id"] = "k"
    assert not verify_receipt(receipt, key)
