"""AES-256-GCM envelope encryption with per-tenant keys.

Implements a KMS-inspired envelope encryption model:
- A master Key Encryption Key (KEK) loaded from ``HIPAA_MASTER_KEY`` env var
- Per-tenant Data Encryption Keys (DEKs) generated on tenant provisioning
- DEKs are wrapped (encrypted) with the KEK before storage
- AES-256-GCM provides authenticated encryption (confidentiality + integrity)
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ── Exception hierarchy ────────────────────────────────────────────────────────


class EncryptionError(Exception):
    """Base exception for all encryption errors."""


class DecryptionError(EncryptionError):
    """Raised when decryption fails (tampered data, wrong key, etc.)."""


class KeyNotFoundError(EncryptionError):
    """Raised when no key exists for the requested tenant."""


# ── Key metadata dataclass ────────────────────────────────────────────────────


@dataclass
class KeyInfo:
    """Metadata about a tenant's encryption key (never exposes plaintext)."""

    tenant_id: str = ""
    key_fingerprint: str = ""
    algorithm: str = "AES-256-GCM"
    is_active: bool = True
    created_at: str = ""
    rotated_at: str | None = None


# ── Encryption Service ────────────────────────────────────────────────────────


class EncryptionService:
    """Envelope encryption service with per-tenant key isolation.

    Supports field-level and document-level encrypt/decrypt, master key
    rotation, and key metadata queries.
    """

    def __init__(
        self,
        config: Any | None = None,
        db_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Initialise with config and optional async DB session factory."""
        self._config = config
        self._db_factory = db_factory

        # Load master key from env var
        self._master_key: bytes | None = None
        raw = os.environ.get("HIPAA_MASTER_KEY", "")
        if raw:
            self._master_key = hashlib.sha256(raw.encode("utf-8")).digest()
        elif config is None or getattr(config, "encryption_enabled", True):
            raise EncryptionError("Master key not found: set HIPAA_MASTER_KEY")

        # In-memory store: tenant_id -> wrapped DEK (base64 string)
        self._key_store: dict[str, str] = {}
        # In-memory key metadata: tenant_id -> KeyInfo
        self._key_meta: dict[str, KeyInfo] = {}

    # ── Internal crypto helpers ────────────────────────────────────────────────

    def _generate_dek(self) -> bytes:
        """Generate a 256-bit data encryption key."""
        return AESGCM.generate_key(bit_length=256)

    def _wrap_key(self, dek: bytes, kek: bytes | None = None) -> str:
        """Encrypt a DEK with the KEK. Returns base64-encoded wrapped key."""
        kek = kek or self._master_key
        assert kek is not None
        aesgcm = AESGCM(kek)
        nonce = os.urandom(12)
        aad = b"WRAP_v1"
        ciphertext = aesgcm.encrypt(nonce, dek, aad)
        wrapped = nonce + ciphertext
        return base64.b64encode(wrapped).decode("ascii")

    def _unwrap_key(self, wrapped_key: str, kek: bytes | None = None) -> bytes:
        """Decrypt a wrapped DEK. Returns raw DEK bytes."""
        kek = kek or self._master_key
        assert kek is not None
        wrapped = base64.b64decode(wrapped_key)
        nonce = wrapped[:12]
        ciphertext = wrapped[12:]
        aesgcm = AESGCM(kek)
        aad = b"WRAP_v1"
        return aesgcm.decrypt(nonce, ciphertext, aad)

    def _aes_encrypt(self, key: bytes, plaintext: str) -> str:
        """AES-256-GCM encrypt. Returns base64 nonce+ciphertext+tag."""
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        aad = b"AES256_GCM_v1"
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.b64encode(nonce + ct).decode("ascii")

    def _aes_decrypt(self, key: bytes, ciphertext: str) -> str:
        """AES-256-GCM decrypt. Returns plaintext."""
        raw = base64.b64decode(ciphertext)
        nonce = raw[:12]
        ct = raw[12:]
        aesgcm = AESGCM(key)
        aad = b"AES256_GCM_v1"
        return aesgcm.decrypt(nonce, ct, aad).decode("utf-8")

    # ── Tenant key management ──────────────────────────────────────────────────

    async def generate_tenant_key(self, tenant_id: str) -> str:
        """Generate a DEK for *tenant_id* wrapped with the current KEK.

        Returns the key fingerprint.
        """
        loop = _get_loop()

        def _gen() -> str:
            dek = self._generate_dek()
            wrapped = self._wrap_key(dek)
            self._key_store[tenant_id] = wrapped
            fp = _fingerprint(dek)
            self._key_meta[tenant_id] = KeyInfo(
                tenant_id=tenant_id,
                key_fingerprint=fp,
                algorithm="AES-256-GCM",
                is_active=True,
                created_at=_now_iso(),
                rotated_at=None,
            )
            return fp

        return await loop.run_in_executor(None, _gen)

    def _get_dek(self, tenant_id: str) -> bytes:
        """Retrieve and unwrap the DEK for a tenant."""
        wrapped = self._key_store.get(tenant_id)
        if wrapped is None:
            raise KeyNotFoundError(
                f"No encryption key found for tenant: {tenant_id}"
            )
        return self._unwrap_key(wrapped)

    # ── Field-level encryption ─────────────────────────────────────────────────

    async def encrypt_field(self, tenant_id: str, plaintext: str) -> str:
        """Encrypt a single string field. Returns base64 ciphertext."""
        loop = _get_loop()

        def _enc() -> str:
            dek = self._get_dek(tenant_id)
            return self._aes_encrypt(dek, plaintext)

        return await loop.run_in_executor(None, _enc)

    async def decrypt_field(self, tenant_id: str, ciphertext: str) -> str:
        """Decrypt a single string field. Returns plaintext.

        Raises DecryptionError if data is tampered or wrong key.
        Raises KeyNotFoundError if tenant has no key.
        """
        loop = _get_loop()

        def _dec() -> str:
            dek = self._get_dek(tenant_id)
            try:
                return self._aes_decrypt(dek, ciphertext)
            except Exception as exc:
                raise DecryptionError(
                    f"Decryption failed for tenant {tenant_id}"
                ) from exc

        return await loop.run_in_executor(None, _dec)

    # ── Document-level encryption ──────────────────────────────────────────────

    async def encrypt_document(
        self, tenant_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Encrypt all PHI fields in a document dict. Returns encrypted dict."""
        loop = _get_loop()

        def _enc_doc() -> dict[str, Any]:
            dek = self._get_dek(tenant_id)
            result: dict[str, Any] = {}
            for key, value in data.items():
                if isinstance(value, str):
                    result[key] = self._aes_encrypt(dek, value)
                elif isinstance(value, dict):
                    result[key] = self._aes_encrypt(
                        dek, _sorted_json(value)
                    )
                elif isinstance(value, (int, float)):
                    result[key] = value  # store non-string fields as-is
                elif value is None:
                    result[key] = None
                else:
                    result[key] = self._aes_encrypt(dek, str(value))
            return result

        return await loop.run_in_executor(None, _enc_doc)

    async def decrypt_document(
        self, tenant_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Decrypt all encrypted fields in a document dict. Returns plaintext."""
        loop = _get_loop()

        def _dec_doc() -> dict[str, Any]:
            dek = self._get_dek(tenant_id)
            result: dict[str, Any] = {}
            for key, value in data.items():
                if isinstance(value, str) and _is_base64(value):
                    try:
                        result[key] = self._aes_decrypt(dek, value)
                    except Exception:
                        result[key] = value
                else:
                    result[key] = value
            return result

        return await loop.run_in_executor(None, _dec_doc)

    # ── Key rotation ──────────────────────────────────────────────────────────

    async def rotate_master_key(self, new_kek_secret: str) -> int:
        """Re-wrap all DEKs with a new KEK. Returns count of re-wrapped keys."""
        loop = _get_loop()

        def _rotate() -> int:
            new_kek = hashlib.sha256(
                new_kek_secret.encode("utf-8")
            ).digest()
            count = 0
            for tenant_id in list(self._key_store.keys()):
                dek = self._unwrap_key(self._key_store[tenant_id])
                self._key_store[tenant_id] = self._wrap_key(dek, new_kek)
                if tenant_id in self._key_meta:
                    meta = self._key_meta[tenant_id]
                    meta.rotated_at = _now_iso()
                count += 1
            self._master_key = new_kek
            return count

        return await loop.run_in_executor(None, _rotate)

    # ── Key info ───────────────────────────────────────────────────────────────

    async def get_key_info(self, tenant_id: str) -> KeyInfo:
        """Return key metadata for *tenant_id* (never exposes plaintext key)."""
        loop = _get_loop()

        def _info() -> KeyInfo:
            if tenant_id not in self._key_meta:
                raise KeyNotFoundError(
                    f"No key found for tenant: {tenant_id}"
                )
            return self._key_meta[tenant_id]

        return await loop.run_in_executor(None, _info)


# ── Module-level helpers ───────────────────────────────────────────────────────


def _get_loop():
    """Get the currently running event loop."""
    import asyncio
    return asyncio.get_running_loop()


def _fingerprint(key_bytes: bytes) -> str:
    """Return a hex fingerprint of a key."""
    return hashlib.sha256(key_bytes).hexdigest()[:16]


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _sorted_json(data: dict[str, Any]) -> str:
    """JSON-serialize a dict with sorted keys."""
    import json
    return json.dumps(data, sort_keys=True)


def _is_base64(s: str) -> bool:
    """Check if a string looks like base64 (heuristic)."""
    if len(s) < 20:
        return False
    try:
        base64.b64decode(s)
        return True
    except Exception:
        return False
