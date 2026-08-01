"""Pre-development tests for FileEncryptor (AES-256-GCM at-rest encryption).

Verifies the blob header layout (magic "MNAS1"), encrypt/decrypt roundtrip,
tamper detection, wrong-key failure, plaintext SHA-256 integrity, and the
fail-fast key requirement when mode=aes256gcm. RED phase: skips until
meeting_notes_ai/storage/encryption.py exists.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

pytestmark = pytest.mark.quick

storage_encryption = pytest.importorskip(
    "meeting_notes_ai.storage.encryption",
    reason="implementation pending: meeting_notes_ai/storage/encryption.py",
)

FileEncryptor = storage_encryption.FileEncryptor

# Blob layout from the analysis brief (Section 8):
#   magic (5B, b"MNAS1") || wrapped_dek_len (1B) || wrapped_dek ||
#   nonce (12B) || ciphertext
MAGIC = b"MNAS1"
NONCE_LEN = 12
DEK_LEN_BYTE = 5  # offset of the wrapped_dek_len byte


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileEncryptorInterface:
    """Verify the FileEncryptor contract."""

    def test_class_exists(self):
        assert FileEncryptor is not None
        assert inspect.isclass(FileEncryptor)

    def test_encrypt_method_exists(self):
        assert callable(FileEncryptor.encrypt)

    def test_decrypt_method_exists(self):
        assert callable(FileEncryptor.decrypt)

    def test_encrypt_accepts_payload(self):
        sig = inspect.signature(FileEncryptor.encrypt)
        params = sig.parameters
        assert any(p in ("payload", "data", "plaintext") for p in params)

    def test_decrypt_accepts_blob(self):
        sig = inspect.signature(FileEncryptor.decrypt)
        params = sig.parameters
        assert any(p in ("blob", "data", "ciphertext") for p in params)


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileEncryptorBehavioral:
    """Roundtrip, header layout, tamper/wrong-key, integrity, fail-fast."""

    KEY_A = "test-storage-key-a-32-bytes-long!!"
    KEY_B = "test-storage-key-b-32-bytes-long!!"

    @pytest.fixture
    def encryptor(self, monkeypatch):
        monkeypatch.setenv("STORAGE_ENCRYPTION", "aes256gcm")
        monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", self.KEY_A)
        return FileEncryptor(mode="aes256gcm")

    def test_encrypt_decrypt_roundtrip(self, encryptor):
        payload = b"meeting transcript with PHI"
        blob = encryptor.encrypt(payload)
        assert isinstance(blob, bytes)
        assert encryptor.decrypt(blob) == payload

    def test_blob_has_magic_header(self, encryptor):
        blob = encryptor.encrypt(b"payload")
        assert blob[: len(MAGIC)] == MAGIC

    def test_blob_header_layout(self, encryptor):
        blob = encryptor.encrypt(b"payload")
        assert len(blob) > DEK_LEN_BYTE + 1
        dek_len = blob[DEK_LEN_BYTE]
        assert 1 <= dek_len <= 255
        nonce_start = DEK_LEN_BYTE + 1 + dek_len
        assert len(blob) >= nonce_start + NONCE_LEN + 1

    def test_ciphertext_differs_from_plaintext(self, encryptor):
        payload = b"hello world"
        blob = encryptor.encrypt(payload)
        assert blob != payload
        assert payload not in blob

    def test_encrypted_blobs_are_unique_per_nonce(self, encryptor):
        blob1 = encryptor.encrypt(b"same payload")
        blob2 = encryptor.encrypt(b"same payload")
        # Fresh nonce per encryption -> blobs differ.
        assert blob1 != blob2

    def test_tampered_blob_raises(self, encryptor):
        blob = bytearray(encryptor.encrypt(b"secret"))
        blob[-1] ^= 0xFF  # flip last ciphertext byte
        with pytest.raises(Exception):
            encryptor.decrypt(bytes(blob))

    def test_wrong_key_fails(self, monkeypatch, encryptor):
        blob = encryptor.encrypt(b"secret")
        monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", self.KEY_B)
        wrong = FileEncryptor(mode="aes256gcm")
        with pytest.raises(Exception):
            wrong.decrypt(blob)

    def test_plaintext_sha256_integrity(self, encryptor):
        payload = b"integrity-check payload"
        decrypted = encryptor.decrypt(encryptor.encrypt(payload))
        assert hashlib.sha256(decrypted).hexdigest() == hashlib.sha256(payload).hexdigest()

    def test_key_from_hipaa_master_key_fallback(self, monkeypatch):
        monkeypatch.setenv("STORAGE_ENCRYPTION", "aes256gcm")
        monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("HIPAA_MASTER_KEY", "hipaa-master-key-32-bytes!!!")
        enc = FileEncryptor(mode="aes256gcm")
        blob = enc.encrypt(b"payload")
        assert enc.decrypt(blob) == b"payload"

    def test_fails_fast_without_key(self, monkeypatch):
        monkeypatch.setenv("STORAGE_ENCRYPTION", "aes256gcm")
        monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("HIPAA_MASTER_KEY", raising=False)
        with pytest.raises(Exception):
            FileEncryptor(mode="aes256gcm")
