#!/usr/bin/env python3
"""Encryption key management example — per-tenant keys and master-key rotation.

Uses the library API:

    from meeting_notes_ai.hipaa.encryption import EncryptionService

Requires the HIPAA_MASTER_KEY environment variable (the KEK seed). The KEK
is derived from this value with SHA-256; per-tenant DEKs are wrapped with it.

Run from the repository root:

    HIPAA_MASTER_KEY=dev-master-key .venv/bin/python examples/hipaa_rotate_key.py
"""

import asyncio
import os

from meeting_notes_ai.hipaa.config import HIPAAConfig
from meeting_notes_ai.hipaa.encryption import EncryptionService


async def main() -> None:
    if not os.environ.get("HIPAA_MASTER_KEY"):
        raise SystemExit("set HIPAA_MASTER_KEY first (e.g. HIPAA_MASTER_KEY=dev-master-key)")

    svc = EncryptionService(config=HIPAAConfig())

    print("== Provision tenant key ==")
    fingerprint = await svc.generate_tenant_key("tenant-1")
    print(f"  fingerprint: {fingerprint}")

    print("\n== Field-level encrypt/decrypt ==")
    ciphertext = await svc.encrypt_field("tenant-1", "PHI: John Smith 123-45-6789")
    print(f"  ciphertext: {ciphertext[:40]}...")
    print(f"  plaintext : {await svc.decrypt_field('tenant-1', ciphertext)}")

    print("\n== Document-level encrypt/decrypt ==")
    doc = {"name": "John Smith", "age": 42, "nested": {"mrn": "123456789"}}
    encrypted = await svc.encrypt_document("tenant-1", doc)
    print(f"  encrypted keys: {list(encrypted.keys())}, age kept as-is: {encrypted['age']}")
    print(f"  decrypted     : {await svc.decrypt_document('tenant-1', encrypted)}")

    print("\n== Master key rotation (re-wraps all DEKs) ==")
    count = await svc.rotate_master_key("new-master-key-after-rotation")
    print(f"  re-wrapped {count} DEK(s)")

    print("\n== Key info ==")
    print(f"  {await svc.get_key_info('tenant-1')}")


if __name__ == "__main__":
    asyncio.run(main())
