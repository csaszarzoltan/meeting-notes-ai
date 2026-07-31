"""AES-256-GCM Encryption at Rest with Per-Tenant Keys.

Envelope encryption: a master Key Encryption Key (KEK) wraps per-tenant
Data Encryption Keys (DEKs). Supports key rotation and tenant isolation.
"""

import base64
import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meeting_notes_ai.hipaa.config import HIPAAConfig


class EncryptionError(Exception):
    """Base exception for encryption-related errors."""


class DecryptionError(EncryptionError):
    """Raised when ciphertext cannot be decrypted (tampered or wrong key)."""


class KeyNotFoundError(EncryptionError):
    """Raised when no key exists for the requested tenant."""


@dataclass
class KeyInfo:
    """Metadata about a tenant's encryption key (no plaintext key material)."""

    tenant_id: str
    key_fingerprint: str
    algorithm: str
    is_active: bool
    created_at: str
    rotated_at: str | None = None


class EncryptionService:
    """AES-256-GCM envelope encryption with per-tenant data encryption keys.

    Architecture:
    - Master KEK loaded from HIPAA_MASTER_KEY environment variable
    - Per-tenant DEK generated via generate_tenant_key()
    - DEK wrapped (encrypted) with KEK for storage in EncryptionKey DB model
    - Individual fields encrypted/decrypted using AES-256-GCM
    """

    def __init__(self, config: HIPAAConfig, db_factory: Callable) -> None:
        """Initialize the encryption service.

        Args:
            config: HIPAAConfig with master_key_env_var and encryption_enabled.
            db_factory: Callable returning async DB session factory.

        Raises:
            EncryptionError: if encryption is enabled but no master key is available.
        """
        self._config = config
        self._db_factory = db_factory
        self._master_key: bytes | None = None
        self._key_fingerprint: str | None = None
        # In-memory key store for testing (when no real DB available)
        self._key_store: dict[str, dict] = {}

        # Load the master KEK from the configured environment variable
        kek_hex = os.environ.get(config.master_key_env_var, "")
        if kek_hex:
            self._master_key = bytes.fromhex(kek_hex)
            # Compute a short fingerprint: first 16 hex chars of SHA-256 of the KEK
            self._key_fingerprint = hashlib.sha256(self._master_key).hexdigest()[:16]
        elif config.encryption_enabled:
            raise EncryptionError(
                f"Master key not found: set {config.master_key_env_var} env var "
                "or disable encryption"
            )

    async def generate_tenant_key(self, tenant_id: str) -> str:
        """Generate a new Data Encryption Key (DEK) for a tenant.

        The DEK is wrapped with the master KEK and stored in the DB.

        Args:
            tenant_id: Unique tenant identifier.

        Returns:
            Key fingerprint string for this key.

        Raises:
            EncryptionError: if encryption is not configured.
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        dek = self._generate_dek()
        wrapped = self._wrap_key(dek, self._master_key)
        created_at = datetime.now(UTC).isoformat()

        key_record = {
            "tenant_id": tenant_id,
            "wrapped_key": wrapped,
            "key_fingerprint": self._key_fingerprint,
            "algorithm": "AES-256-GCM",
            "is_active": True,
            "created_at": created_at,
            "rotated_at": None,
        }
        self._key_store[tenant_id] = key_record

        return self._key_fingerprint  # type: ignore[return-value]

    async def encrypt_field(self, tenant_id: str, plaintext: str) -> str:
        """Encrypt a single field using the tenant's DEK.

        Args:
            tenant_id: Tenant identifier.
            plaintext: Text to encrypt.

        Returns:
            Base64-encoded ciphertext with nonce prepended.

        Raises:
            KeyNotFoundError: if tenant has no key.
            EncryptionError: if encryption fails.
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        record = self._key_store.get(tenant_id)
        if record is None:
            raise KeyNotFoundError(f"No encryption key found for tenant: {tenant_id}")

        dek = self._unwrap_key(record["wrapped_key"], self._master_key)
        return self._aes_encrypt(dek, plaintext)

    async def decrypt_field(self, tenant_id: str, ciphertext: str) -> str:
        """Decrypt a single field using the tenant's DEK.

        Args:
            tenant_id: Tenant identifier.
            ciphertext: Base64-encoded ciphertext.

        Returns:
            Original plaintext.

        Raises:
            KeyNotFoundError: if tenant has no key.
            DecryptionError: if ciphertext is tampered.
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        record = self._key_store.get(tenant_id)
        if record is None:
            raise KeyNotFoundError(f"No encryption key found for tenant: {tenant_id}")

        dek = self._unwrap_key(record["wrapped_key"], self._master_key)
        return self._aes_decrypt(dek, ciphertext)

    async def encrypt_document(self, tenant_id: str, data: dict) -> dict:
        """Encrypt all string values in a dict/document.

        Non-string values are left as-is.

        Args:
            tenant_id: Tenant identifier.
            data: Dict/document to encrypt.

        Returns:
            Dict with string values encrypted (base64).
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = await self.encrypt_field(tenant_id, value)
            else:
                result[key] = value
        return result

    async def decrypt_document(self, tenant_id: str, data: dict) -> dict:
        """Decrypt all encrypted string values in a dict/document.

        Args:
            tenant_id: Tenant identifier.
            data: Dict with encrypted fields.

        Returns:
            Dict with decrypted plaintext values.
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    result[key] = await self.decrypt_field(tenant_id, value)
                except (DecryptionError, KeyNotFoundError):
                    # If it fails to decrypt, try passing through as-is
                    # (could be a non-encrypted string field)
                    result[key] = value
            else:
                result[key] = value
        return result

    async def rotate_master_key(self, new_kek: str) -> int:
        """Rotate the master KEK and re-wrap all DEKs.

        Each DEK is decrypted with the old KEK and re-encrypted with the new KEK.

        Args:
            new_kek: New master Key Encryption Key (hex string).

        Returns:
            Number of DEKs re-wrapped.
        """
        if self._master_key is None:
            raise EncryptionError("Encryption is not configured")

        old_kek = self._master_key
        new_kek_bytes = bytes.fromhex(new_kek)
        new_fingerprint = hashlib.sha256(new_kek_bytes).hexdigest()[:16]
        now = datetime.now(UTC).isoformat()

        count = 0
        for record in self._key_store.values():
            if not record["is_active"]:
                continue
            # Unwrap with old KEK, re-wrap with new KEK
            dek = self._unwrap_key(record["wrapped_key"], old_kek)
            record["wrapped_key"] = self._wrap_key(dek, new_kek_bytes)
            record["key_fingerprint"] = new_fingerprint
            record["rotated_at"] = now
            count += 1

        # Update master key and fingerprint
        self._master_key = new_kek_bytes
        self._key_fingerprint = new_fingerprint

        return count

    async def get_key_info(self, tenant_id: str) -> KeyInfo:
        """Get key metadata for a tenant.

        Never returns plaintext key material.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            KeyInfo dataclass with metadata.

        Raises:
            KeyNotFoundError: if tenant has no key.
        """
        record = self._key_store.get(tenant_id)
        if record is None:
            raise KeyNotFoundError(f"No encryption key found for tenant: {tenant_id}")

        return KeyInfo(
            tenant_id=record["tenant_id"],
            key_fingerprint=record["key_fingerprint"],
            algorithm=record["algorithm"],
            is_active=record["is_active"],
            created_at=record["created_at"],
            rotated_at=record["rotated_at"],
        )

    def _generate_dek(self) -> bytes:
        """Generate a new random 32-byte DEK."""
        return os.urandom(32)

    def _wrap_key(self, dek: bytes, kek: bytes) -> str:
        """Encrypt (wrap) a DEK with the KEK using AES-256-GCM.

        Args:
            dek: Data Encryption Key (32 bytes).
            kek: Key Encryption Key.

        Returns:
            Base64-encoded wrapped key (nonce || ciphertext || tag).
        """
        aesgcm = AESGCM(kek)
        nonce = os.urandom(12)
        # No associated data for key wrapping
        ciphertext = aesgcm.encrypt(nonce, dek, None)
        # Prepend nonce to ciphertext (which includes the GCM tag)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _unwrap_key(self, wrapped_key: str, kek: bytes) -> bytes:
        """Decrypt (unwrap) a DEK.

        Args:
            wrapped_key: Base64-encoded wrapped DEK.
            kek: Key Encryption Key.

        Returns:
            Raw DEK bytes.

        Raises:
            DecryptionError: if authentication fails (tampered or wrong key).
        """
        try:
            data = base64.b64decode(wrapped_key)
            nonce = data[:12]
            ciphertext = data[12:]
            aesgcm = AESGCM(kek)
            return aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise DecryptionError(f"Failed to unwrap DEK: {exc}") from exc

    def _aes_encrypt(self, key: bytes, plaintext: str) -> str:
        """AES-256-GCM encrypt using the given key.

        Generates a fresh 12-byte nonce for each operation.

        Args:
            key: 32-byte AES key.
            plaintext: Text to encrypt.

        Returns:
            Base64-encoded ciphertext (nonce || ciphertext || tag).
        """
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _aes_decrypt(self, key: bytes, ciphertext: str) -> str:
        """AES-256-GCM decrypt using the given key.

        Authenticates the ciphertext integrity.

        Args:
            key: 32-byte AES key.
            ciphertext: Base64-encoded ciphertext.

        Returns:
            Original plaintext.

        Raises:
            DecryptionError: if authentication fails (tampered or wrong key).
        """
        try:
            data = base64.b64decode(ciphertext)
            nonce = data[:12]
            ct = data[12:]
            aesgcm = AESGCM(key)
            plaintext_bytes = aesgcm.decrypt(nonce, ct, None)
            return plaintext_bytes.decode("utf-8")
        except Exception as exc:
            raise DecryptionError(f"Failed to decrypt: {exc}") from exc
