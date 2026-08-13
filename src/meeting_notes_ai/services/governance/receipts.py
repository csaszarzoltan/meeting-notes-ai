"""Canonical HMAC signed deletion receipts."""

import hashlib
import hmac
import json


def sign_receipt(body: dict, key: bytes) -> dict:
    if len(key) < 32:
        raise ValueError("Receipt signing key must be at least 32 bytes")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {**body, "signature": hmac.new(key, raw, hashlib.sha256).hexdigest()}


def verify_receipt(receipt: dict, key: bytes) -> bool:
    signature = receipt.get("signature", "")
    body = {k: v for k, v in receipt.items() if k != "signature"}
    try:
        expected = sign_receipt(body, key)["signature"]
    except ValueError:
        return False
    return hmac.compare_digest(signature, expected)
