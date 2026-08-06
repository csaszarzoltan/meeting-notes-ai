"""Token-level AES-256-GCM envelope encryption.

Lightweight wrapper around the same DEK/KEK pattern used by
FileEncryptor (storage/encryption.py) but designed for short strings
(OAuth access/refresh tokens). Each encrypt() call generates a fresh
DEK, so compromised ciphertexts do not expose other tokens.

Layout (base64-encoded):
    MAGIC(b"MNAT1") || wrapped_dek_len(1B) || wrapped_dek || nonce(12B) || ciphertext
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meeting_notes_ai.config import settings

MAGIC = b"MNAT1"
_MAGIC_LEN = 5
_NONCE_LEN = 12
_DEK_LEN = 32
_DEK_AAD = b"MNAT1-DEK"
_PAYLOAD_AAD = b"MNAT1-PAYLOAD"


def _derive_kek(seed: str) -> bytes:
    return hashlib.sha256(seed.encode("utf-8")).digest()


class TokenEncryptor:
    """AES-256-GCM envelope encryptor for OAuth tokens.

    Uses STORAGE_ENCRYPTION_KEY (or HIPAA_MASTER_KEY) as KEK seed,
    matching FileEncryptor's key derivation. Tokens are base64-encoded
    after encryption so they fit cleanly in DB text columns.
    """

    def __init__(self, key: str | None = None) -> None:
        seed = key or settings.storage_encryption_key or os.getenv("HIPAA_MASTER_KEY", "")
        if not seed:
            raise ValueError(
                "TokenEncryptor requires STORAGE_ENCRYPTION_KEY or HIPAA_MASTER_KEY"
            )
        self._kek = _derive_kek(seed)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a token string. Returns base64-encoded ciphertext."""
        dek = os.urandom(_DEK_LEN)
        nonce = os.urandom(_NONCE_LEN)
        cipher = AESGCM(dek)
        wrapped_dek = AESGCM(self._kek).encrypt(nonce, dek, _DEK_AAD)
        ciphertext = cipher.encrypt(nonce, plaintext.encode("utf-8"), _PAYLOAD_AAD)
        raw = MAGIC + bytes([len(wrapped_dek)]) + wrapped_dek + nonce + ciphertext
        return base64.b64encode(raw).decode("ascii")

    def decrypt(self, token_b64: str) -> str:
        """Decrypt a base64-encoded ciphertext. Returns plaintext string."""
        raw = base64.b64decode(token_b64)
        if len(raw) < _MAGIC_LEN + 1 + _NONCE_LEN + 1:
            raise ValueError("token blob too short")
        if raw[:_MAGIC_LEN] != MAGIC:
            raise ValueError("invalid token blob magic")
        dek_len = raw[_MAGIC_LEN]
        nonce_start = _MAGIC_LEN + 1 + dek_len
        wrapped_dek = raw[_MAGIC_LEN + 1 : nonce_start]
        nonce = raw[nonce_start : nonce_start + _NONCE_LEN]
        ciphertext = raw[nonce_start + _NONCE_LEN :]
        dek = AESGCM(self._kek).decrypt(nonce, wrapped_dek, _DEK_AAD)
        return AESGCM(dek).decrypt(nonce, ciphertext, _PAYLOAD_AAD).decode("utf-8")
