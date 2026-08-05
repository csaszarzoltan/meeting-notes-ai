"""Client-side AES-256-GCM encryption at rest for stored files.

:class:`FileEncryptor` encrypts each file with a fresh random 256-bit
data-encryption key (DEK) wrapped by a key-encryption key (KEK) derived
from ``STORAGE_ENCRYPTION_KEY`` (falling back to ``HIPAA_MASTER_KEY``).
The blob layout is versioned and self-describing:

``magic (b"MNAS1", 5B) || wrapped_dek_len (1B) || wrapped_dek ||
 nonce (12B) || ciphertext``

This works identically on every storage backend (local, S3, R2, MinIO) —
critical because Cloudflare R2 has no SSE-KMS / customer-managed server
side keys (analysis brief §8). Keys come from the environment only and
are never logged or serialized.

Plaintext integrity is enforced two ways: (1) AES-GCM authenticates the
ciphertext and the payload AAD, so any tamper raises before data is
returned; (2) the plaintext SHA-256 stored in ``storage_files.sha256``
is verified by the routes layer after decryption.
"""

from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meeting_notes_ai.config import settings

# Blob header magic (versioned). Bump the suffix on breaking layout changes.
MAGIC = b"MNAS1"
_MAGIC_LEN = len(MAGIC)  # 5
_DEK_LEN_BYTE = 1
_NONCE_LEN = 12
_DEK_LEN = 32  # AES-256
_DEK_AAD = b"MNAS1-DEK"
# Domain-separated AAD for the payload ciphertext (bound to the header
# format so ciphertexts cannot be transplanted across formats).
_PAYLOAD_AAD = b"MNAS1-PAYLOAD"

# Allowed STORAGE_ENCRYPTION modes.
MODE_NONE = "none"
MODE_AES256GCM = "aes256gcm"
_SUPPORTED_MODES = {MODE_NONE, MODE_AES256GCM}


class EncryptionError(Exception):
    """Raised when an encrypted blob cannot be decrypted."""


def _derive_kek(seed: str) -> bytes:
    """Derive the 32-byte key-encryption key from the env secret."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


class FileEncryptor:
    """AES-256-GCM envelope encryptor with per-file DEKs.

    Args:
        mode: ``"none"`` (passthrough) or ``"aes256gcm"``. Defaults to the
            ``STORAGE_ENCRYPTION`` setting.
        key: Optional explicit KEK seed (defaults to ``STORAGE_ENCRYPTION_KEY``
            or ``HIPAA_MASTER_KEY``). Primarily used by tests.

    Raises:
        ValueError: When ``mode="aes256gcm"`` but no KEK seed is available
            (fail fast — the app must not silently store plaintext).
    """

    def __init__(
        self,
        mode: str | None = None,
        key: str | None = None,
    ) -> None:
        self.mode = mode or settings.storage_encryption or MODE_NONE
        if self.mode not in _SUPPORTED_MODES:
            raise ValueError(
                f"Unsupported STORAGE_ENCRYPTION mode: {self.mode!r} "
                f"(expected {sorted(_SUPPORTED_MODES)})"
            )
        if self.mode == MODE_AES256GCM:
            seed = (
                key
                or settings.storage_encryption_key
                or os.getenv("STORAGE_ENCRYPTION_KEY", "")
                or os.getenv("HIPAA_MASTER_KEY", "")
            )
            if not seed:
                raise ValueError(
                    "STORAGE_ENCRYPTION=aes256gcm requires STORAGE_ENCRYPTION_KEY "
                    "(or HIPAA_MASTER_KEY) — refusing to store plaintext"
                )
            self._kek = _derive_kek(seed)
        else:
            self._kek = b""

    @property
    def enabled(self) -> bool:
        """True when this encryptor actually encrypts payloads."""
        return self.mode == MODE_AES256GCM

    # ── Public API ────────────────────────────────────────────────────────────

    def encrypt(self, payload: bytes) -> bytes:
        """Encrypt *payload* and return the versioned blob.

        With ``mode="none"`` this returns the payload unchanged.
        """
        if not self.enabled:
            return payload

        dek = os.urandom(_DEK_LEN)
        nonce = os.urandom(_NONCE_LEN)
        cipher = AESGCM(dek)
        wrapped_dek = AESGCM(self._kek).encrypt(nonce, dek, _DEK_AAD)
        ciphertext = cipher.encrypt(nonce, payload, _PAYLOAD_AAD)

        header = MAGIC + bytes([len(wrapped_dek)]) + wrapped_dek + nonce
        return header + ciphertext

    def decrypt(self, blob: bytes) -> bytes:
        """Decrypt a blob produced by :meth:`encrypt`.

        Raises:
            EncryptionError: On invalid header, tampered ciphertext, or an
                unknown KEK (wrong key). Raw ciphertext is never returned.
        """
        if not self.enabled:
            return blob

        try:
            if len(blob) < _MAGIC_LEN + _DEK_LEN_BYTE + _NONCE_LEN + 1:
                raise EncryptionError("blob too short")
            if blob[:_MAGIC_LEN] != MAGIC:
                raise EncryptionError("invalid blob header magic")
            dek_len = blob[_MAGIC_LEN]
            if not 1 <= dek_len <= 255:
                raise EncryptionError("invalid wrapped DEK length")
            nonce_start = _MAGIC_LEN + _DEK_LEN_BYTE + dek_len
            if len(blob) < nonce_start + _NONCE_LEN:
                raise EncryptionError("blob truncated")
            wrapped_dek = blob[_MAGIC_LEN + _DEK_LEN_BYTE : nonce_start]
            nonce = blob[nonce_start : nonce_start + _NONCE_LEN]
            ciphertext = blob[nonce_start + _NONCE_LEN :]

            dek = AESGCM(self._kek).decrypt(nonce, wrapped_dek, _DEK_AAD)
            return AESGCM(dek).decrypt(nonce, ciphertext, _PAYLOAD_AAD)
        except (InvalidTag, ValueError, EncryptionError) as exc:
            if isinstance(exc, EncryptionError):
                raise
            raise EncryptionError("decryption failed (tampered blob or wrong key)") from exc
