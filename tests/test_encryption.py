"""Interface + behavioral pre-tests for EncryptionService."""

import os

import pytest

from meeting_notes_ai.hipaa.encryption import (
    DecryptionError,
    EncryptionError,
    EncryptionService,
    KeyInfo,
    KeyNotFoundError,
)

# ── Interface tests (should pass immediately) ──────────────────────────────


class TestEncryptionExceptions:
    """Verify exception hierarchy."""

    def test_encryption_error_is_base(self):
        assert issubclass(EncryptionError, Exception)

    def test_decryption_error_inherits(self):
        assert issubclass(DecryptionError, EncryptionError)

    def test_key_not_found_inherits(self):
        assert issubclass(KeyNotFoundError, EncryptionError)


class TestKeyInfoInterface:
    """Verify KeyInfo dataclass structure."""

    def test_is_dataclass(self):
        assert hasattr(KeyInfo, "__dataclass_fields__")

    def test_has_tenant_id_field(self):
        assert "tenant_id" in KeyInfo.__dataclass_fields__

    def test_has_key_fingerprint_field(self):
        assert "key_fingerprint" in KeyInfo.__dataclass_fields__

    def test_has_algorithm_field(self):
        assert "algorithm" in KeyInfo.__dataclass_fields__

    def test_has_is_active_field(self):
        assert "is_active" in KeyInfo.__dataclass_fields__

    def test_has_created_at_field(self):
        assert "created_at" in KeyInfo.__dataclass_fields__

    def test_has_rotated_at_field(self):
        assert "rotated_at" in KeyInfo.__dataclass_fields__

    def test_rotated_at_optional(self):
        info = KeyInfo(
            tenant_id="tenant1",
            key_fingerprint="abc123",
            algorithm="AES-256-GCM",
            is_active=True,
            created_at="2026-07-30T12:00:00Z",
        )
        assert info.rotated_at is None


class TestEncryptionServiceInterface:
    """Verify EncryptionService class structure."""

    def test_class_exists(self):
        assert EncryptionService is not None

    def test_method_generate_tenant_key(self):
        assert hasattr(EncryptionService, "generate_tenant_key")

    def test_method_encrypt_field(self):
        assert hasattr(EncryptionService, "encrypt_field")

    def test_method_decrypt_field(self):
        assert hasattr(EncryptionService, "decrypt_field")

    def test_method_encrypt_document(self):
        assert hasattr(EncryptionService, "encrypt_document")

    def test_method_decrypt_document(self):
        assert hasattr(EncryptionService, "decrypt_document")

    def test_method_rotate_master_key(self):
        assert hasattr(EncryptionService, "rotate_master_key")

    def test_method_get_key_info(self):
        assert hasattr(EncryptionService, "get_key_info")

    def test_internal_generate_dek(self):
        assert hasattr(EncryptionService, "_generate_dek")

    def test_internal_wrap_key(self):
        assert hasattr(EncryptionService, "_wrap_key")

    def test_internal_unwrap_key(self):
        assert hasattr(EncryptionService, "_unwrap_key")

    def test_internal_aes_encrypt(self):
        assert hasattr(EncryptionService, "_aes_encrypt")

    def test_internal_aes_decrypt(self):
        assert hasattr(EncryptionService, "_aes_decrypt")

    def test_init_accepts_config(self):
        """Constructor should accept HIPAAConfig + db_factory."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig
        old = os.environ.get("HIPAA_MASTER_KEY")
        os.environ["HIPAA_MASTER_KEY"] = TEST_MASTER_KEY_HEX
        try:
            svc = EncryptionService(HIPAAConfig(), lambda: None)
            assert isinstance(svc, EncryptionService)
        finally:
            if old is None:
                del os.environ["HIPAA_MASTER_KEY"]
            else:
                os.environ["HIPAA_MASTER_KEY"] = old

    def test_init_raises_without_master_key(self):
        """Constructor should raise EncryptionError when no master key is set."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        saved = os.environ.pop("HIPAA_MASTER_KEY", None)
        try:
            with pytest.raises(EncryptionError, match="Master key not found"):
                EncryptionService(HIPAAConfig(encryption_enabled=True), lambda: None)
        finally:
            if saved is not None:
                os.environ["HIPAA_MASTER_KEY"] = saved

    def test_init_disabled_without_master_key(self):
        """Constructor should work when encryption is disabled and no key set."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        saved = os.environ.pop("HIPAA_MASTER_KEY", None)
        try:
            svc = EncryptionService(HIPAAConfig(encryption_enabled=False), lambda: None)
            assert svc._master_key is None
        finally:
            if saved is not None:
                os.environ["HIPAA_MASTER_KEY"] = saved


# ── Behavioral tests ──────────────────────────────────────────────────────

TEST_MASTER_KEY_HEX = "ab" * 32  # 64 hex chars = 32 bytes


class TestEncryptionServiceBehavioral:
    """Expected behaviors once EncryptionService is implemented."""

    @pytest.fixture(autouse=True)
    def _set_master_key_env(self):
        """Set a test master key in the environment for each test."""
        old = os.environ.get("HIPAA_MASTER_KEY")
        os.environ["HIPAA_MASTER_KEY"] = TEST_MASTER_KEY_HEX
        yield
        if old is None:
            del os.environ["HIPAA_MASTER_KEY"]
        else:
            os.environ["HIPAA_MASTER_KEY"] = old

    @pytest.fixture
    def svc(self):
        from meeting_notes_ai.hipaa.config import HIPAAConfig
        import json
        from pathlib import Path

        # Clear any persisted key store from previous tests (B4 fix)
        key_store_path = Path.home() / ".meeting-notes-ai" / "key_store.json"
        if key_store_path.exists():
            key_store_path.unlink()

        return EncryptionService(
            HIPAAConfig(encryption_enabled=True),
            lambda: None,
        )

    @pytest.mark.asyncio
    async def test_generate_tenant_key_returns_fingerprint(self, svc):
        """generate_tenant_key() should return a string fingerprint."""
        fingerprint = await svc.generate_tenant_key("tenant1")
        assert isinstance(fingerprint, str)
        assert len(fingerprint) > 0

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_round_trip(self, svc):
        """encrypt_field() + decrypt_field() should return original plaintext."""
        await svc.generate_tenant_key("tenant1")
        original = "Patient: John Smith, SSN: 123-45-6789"
        ciphertext = await svc.encrypt_field("tenant1", original)
        decrypted = await svc.decrypt_field("tenant1", ciphertext)
        assert decrypted == original

    @pytest.mark.asyncio
    async def test_decrypt_tampered_ciphertext_raises(self, svc):
        """Tampered ciphertext should raise DecryptionError."""
        await svc.generate_tenant_key("tenant1")
        ciphertext = await svc.encrypt_field("tenant1", "test data")
        # Flip one character in the base64 to tamper it
        tampered = ciphertext[:-1] + ("0" if ciphertext[-1] == "1" else "1")
        with pytest.raises(DecryptionError):
            await svc.decrypt_field("tenant1", tampered)

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, svc):
        """Different tenants should produce different ciphertexts for same plaintext."""
        await svc.generate_tenant_key("tenant_a")
        await svc.generate_tenant_key("tenant_b")
        plaintext = "Same sensitive data"
        ct_a = await svc.encrypt_field("tenant_a", plaintext)
        ct_b = await svc.encrypt_field("tenant_b", plaintext)
        assert ct_a != ct_b

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_decrypt_tenant_a(self, svc):
        """Tenant B should not be able to decrypt Tenant A's ciphertext."""
        await svc.generate_tenant_key("tenant_a")
        await svc.generate_tenant_key("tenant_b")
        ct = await svc.encrypt_field("tenant_a", "secret data")
        with pytest.raises(DecryptionError):
            await svc.decrypt_field("tenant_b", ct)

    @pytest.mark.asyncio
    async def test_key_info_no_plaintext(self, svc):
        """get_key_info() should not expose plaintext key material."""
        await svc.generate_tenant_key("tenant1")
        info = await svc.get_key_info("tenant1")
        # Verify no plaintext key field exists
        assert not hasattr(info, "plaintext_key")
        assert info.key_fingerprint is not None
        assert info.tenant_id == "tenant1"
        assert info.algorithm == "AES-256-GCM"

    @pytest.mark.asyncio
    async def test_key_not_found_raises(self, svc):
        """decrypt_field() for unknown tenant should raise KeyNotFoundError."""
        with pytest.raises(KeyNotFoundError):
            await svc.decrypt_field("nonexistent", "ciphertext")

    @pytest.mark.asyncio
    async def test_encrypt_document_round_trip(self, svc):
        """encrypt_document() + decrypt_document() should return original dict."""
        await svc.generate_tenant_key("tenant1")
        doc = {"name": "John Smith", "ssn": "123-45-6789", "age": 45}
        encrypted = await svc.encrypt_document("tenant1", doc)
        decrypted = await svc.decrypt_document("tenant1", encrypted)
        assert decrypted["name"] == "John Smith"
        assert decrypted["age"] == 45

    @pytest.mark.asyncio
    async def test_key_rotation(self, svc):
        """rotate_master_key() should re-wrap all DEKs with new KEK."""
        await svc.generate_tenant_key("tenant1")
        await svc.generate_tenant_key("tenant2")
        # New KEK: another 64-char hex string
        new_kek_hex = "cd" * 32
        count = await svc.rotate_master_key(new_kek_hex)
        assert count >= 2

    @pytest.mark.asyncio
    async def test_rotation_does_not_break_decryption(self, svc):
        """Old ciphertexts should still decrypt after key rotation."""
        await svc.generate_tenant_key("tenant1")
        ct = await svc.encrypt_field("tenant1", "important data")
        new_kek_hex = "ef" * 32
        await svc.rotate_master_key(new_kek_hex)
        decrypted = await svc.decrypt_field("tenant1", ct)
        assert decrypted == "important data"

    @pytest.mark.asyncio
    async def test_nonce_uniqueness(self, svc):
        """Each encryption should use a unique nonce (no nonce reuse)."""
        await svc.generate_tenant_key("tenant1")
        results = set()
        for _ in range(10):
            ct = await svc.encrypt_field("tenant1", "same data")
            results.add(ct)
        assert len(results) == 10

    def test_generate_dek_returns_32_bytes(self, svc):
        """_generate_dek() should return 32 random bytes."""
        dek = svc._generate_dek()
        assert isinstance(dek, bytes) and len(dek) == 32
