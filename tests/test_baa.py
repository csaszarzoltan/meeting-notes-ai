"""Interface and behavioral pre-dev tests for BAAService (T5).

RED phase: interface tests PASS, behavioral tests FAIL with NotImplementedError.
Dev must implement src/meeting_notes_ai/hipaa/baa.py to make behavioral tests pass.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


from meeting_notes_ai.hipaa.baa import (
    BAAgreement,
    BAAgreementSummary,
    BAAService,
    BAATemplate,
)

# ── Interface Tests (must PASS immediately) ────────────────────────────────────


class TestBAADataclassInterfaces:
    """Verify BAA dataclass definitions and field contracts."""

    def test_baa_template_is_dataclass(self):
        """BAATemplate should be a dataclass."""
        assert is_dataclass(BAATemplate)

    def test_baa_template_fields_exist(self):
        """BAATemplate should have all expected fields."""
        fields = BAATemplate.__dataclass_fields__
        assert "id" in fields
        assert "version" in fields
        assert "content" in fields
        assert "is_active" in fields

    def test_baa_template_defaults(self):
        """BAATemplate should have sensible defaults."""
        tmpl = BAATemplate()
        assert tmpl.id == ""
        assert tmpl.version == "1.0"
        assert tmpl.content == ""
        assert tmpl.is_active is True

    def test_baa_agreement_is_dataclass(self):
        """BAAgreement should be a dataclass."""
        assert is_dataclass(BAAgreement)

    def test_baa_agreement_fields_exist(self):
        """BAAgreement should have all expected fields."""
        fields = BAAgreement.__dataclass_fields__
        assert "id" in fields
        assert "org_name" in fields
        assert "ba_name" in fields
        assert "effective_date" in fields
        assert "signed_by" in fields
        assert "content_md" in fields
        assert "status" in fields

    def test_baa_agreement_defaults(self):
        """BAAgreement should have sensible defaults."""
        ag = BAAgreement()
        assert ag.id == ""
        assert ag.org_name == ""
        assert ag.ba_name == ""
        assert ag.status == "active"

    def test_baa_agreement_summary_is_dataclass(self):
        """BAAgreementSummary should be a dataclass."""
        assert is_dataclass(BAAgreementSummary)

    def test_baa_agreement_summary_fields(self):
        """BAAgreementSummary should have expected fields."""
        fields = BAAgreementSummary.__dataclass_fields__
        assert "id" in fields
        assert "org_name" in fields
        assert "ba_name" in fields
        assert "effective_date" in fields
        assert "status" in fields


class TestBAAServiceInterface:
    """Verify BAAService class and method signatures."""

    def test_baa_service_can_be_imported(self):
        """BAAService should be importable."""
        assert BAAService is not None

    def test_init_signature(self):
        """__init__ should accept optional db_factory."""
        sig = signature(BAAService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "db_factory" in params
        # db_factory should default to None
        param = sig.parameters["db_factory"]
        assert param.default is None

    def test_generate_template_signature(self):
        """generate_template should accept org_name, ba_name, effective_date."""
        assert hasattr(BAAService, "generate_template")
        sig = signature(BAAService.generate_template)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "org_name" in params
        assert "ba_name" in params
        assert "effective_date" in params

    def test_generate_template_is_async(self):
        """generate_template should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(BAAService.generate_template)

    def test_generate_pdf_signature(self):
        """generate_pdf should accept agreement_id."""
        assert hasattr(BAAService, "generate_pdf")
        sig = signature(BAAService.generate_pdf)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "agreement_id" in params

    def test_generate_pdf_is_async(self):
        """generate_pdf should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(BAAService.generate_pdf)

    def test_store_agreement_signature(self):
        """store_agreement should accept org_name, ba_name, signed_by."""
        assert hasattr(BAAService, "store_agreement")
        sig = signature(BAAService.store_agreement)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "org_name" in params
        assert "ba_name" in params
        assert "signed_by" in params

    def test_store_agreement_is_async(self):
        """store_agreement should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(BAAService.store_agreement)

    def test_get_agreement_signature(self):
        """get_agreement should accept agreement_id."""
        assert hasattr(BAAService, "get_agreement")
        sig = signature(BAAService.get_agreement)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "agreement_id" in params

    def test_get_agreement_is_async(self):
        """get_agreement should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(BAAService.get_agreement)

    def test_list_agreements_signature(self):
        """list_agreements should accept only self."""
        assert hasattr(BAAService, "list_agreements")
        sig = signature(BAAService.list_agreements)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_list_agreements_is_async(self):
        """list_agreements should be a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(BAAService.list_agreements)

    def test_generate_template_returns_str(self):
        """generate_template return annotation should be str."""
        sig = signature(BAAService.generate_template)
        # PEP 563 (from __future__ import annotations) stores annotations as strings
        assert sig.return_annotation == "str"

    def test_generate_pdf_returns_bytes(self):
        """generate_pdf return annotation should be bytes."""
        sig = signature(BAAService.generate_pdf)
        assert sig.return_annotation == "bytes"

    def test_store_agreement_returns_str(self):
        """store_agreement return annotation should be str (UUID)."""
        sig = signature(BAAService.store_agreement)
        assert sig.return_annotation == "str"

    def test_get_agreement_returns_baa_agreement(self):
        """get_agreement return annotation should be BAAgreement."""
        sig = signature(BAAService.get_agreement)
        assert sig.return_annotation == "BAAgreement"

    def test_list_agreements_returns_list(self):
        """list_agreements return annotation should be list[BAAgreementSummary]."""
        sig = signature(BAAService.list_agreements)
        assert sig.return_annotation == "list[BAAgreementSummary]"


# ── Behavioral Tests — active after implementation ──────────────────────────


class TestBAAServiceBehavioral:
    """BAAService behaviors — active after implementation replaces NotImplementedError stubs."""

    def test_init_succeeds(self):
        """BAAService should instantiate without error."""
        service = BAAService()
        assert service is not None
        assert service._agreements == {}

    def test_init_with_db_factory_succeeds(self):
        """BAAService should accept an optional db_factory."""
        service = BAAService(db_factory=lambda: None)
        assert service is not None
        assert service._db_factory is not None

    @pytest.mark.asyncio
    async def test_generate_template_works(self):
        """generate_template should produce markdown without error."""
        service = BAAService()
        result = await service.generate_template(
            org_name="Test Clinic",
            ba_name="Test BA",
            effective_date="2026-08-01",
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Test Clinic" in result
        assert "Test BA" in result
        assert "2026-08-01" in result

    @pytest.mark.asyncio
    async def test_generate_pdf_works(self):
        """generate_pdf should produce PDF bytes without error after storing agreement."""
        service = BAAService()
        ag_id = await service.store_agreement(
            org_name="PDF Test Clinic",
            ba_name="PDF Test BA",
            signed_by="pdf@test.com",
        )
        pdf_bytes = await service.generate_pdf(ag_id)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_store_agreement_works(self):
        """store_agreement should return a valid UUID string."""
        service = BAAService()
        ag_id = await service.store_agreement(
            org_name="Store Test",
            ba_name="Store BA",
            signed_by="admin@store.com",
        )
        assert isinstance(ag_id, str)
        assert len(ag_id) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_get_agreement_works(self):
        """get_agreement should retrieve a stored agreement."""
        service = BAAService()
        ag_id = await service.store_agreement(
            org_name="Get Test",
            ba_name="Get BA",
            signed_by="admin@get.com",
        )
        agreement = await service.get_agreement(ag_id)
        assert agreement.org_name == "Get Test"
        assert agreement.ba_name == "Get BA"

    @pytest.mark.asyncio
    async def test_list_agreements_works(self):
        """list_agreements should return a list (possibly empty)."""
        service = BAAService()
        summaries = await service.list_agreements()
        assert isinstance(summaries, list)

    # ── Behavioral feature tests ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_template_returns_markdown(self):
        """generate_template should return valid markdown string."""
        service = BAAService()
        result = await service.generate_template(
            org_name="Test Clinic",
            ba_name="Test BA",
            effective_date="2026-08-01",
        )
        assert isinstance(result, str)
        assert "# BUSINESS ASSOCIATE AGREEMENT" in result
        assert "Test Clinic" in result
        assert "Test BA" in result
        assert "2026-08-01" in result

    @pytest.mark.asyncio
    async def test_generate_pdf_returns_valid_pdf(self):
        """generate_pdf should return bytes that look like a PDF."""
        service = BAAService()
        ag_id = await service.store_agreement(
            org_name="PDF Test",
            ba_name="PDF BA",
            signed_by="pdf@test.com",
        )
        pdf_bytes = await service.generate_pdf(agreement_id=ag_id)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_store_and_get_agreement_round_trip(self):
        """store_agreement then get_agreement should return matching record."""
        service = BAAService()
        ag_id = await service.store_agreement(
            org_name="Test Clinic",
            ba_name="Test BA",
            signed_by="admin@clinic.com",
        )
        agreement = await service.get_agreement(ag_id)
        assert agreement.org_name == "Test Clinic"
        assert agreement.ba_name == "Test BA"
        assert agreement.signed_by == "admin@clinic.com"
        assert agreement.status == "active"

    @pytest.mark.asyncio
    async def test_list_agreements_returns_list(self):
        """list_agreements should return a list of summaries."""
        service = BAAService()
        # Store an agreement so the list is non-empty
        await service.store_agreement(
            org_name="List Test",
            ba_name="List BA",
            signed_by="admin@list.com",
        )
        summaries = await service.list_agreements()
        assert isinstance(summaries, list)
        assert len(summaries) > 0
        assert isinstance(summaries[0], BAAgreementSummary)

    def test_agreement_immutable_after_store(self):
        """Once stored, an agreement should not be updatable (no update method)."""
        assert not hasattr(BAAService, "update_agreement")
        assert not hasattr(BAAService, "modify_agreement")


# ── S7 regression tests — persistence + Jinja sandbox ─────────────────────────


class TestBAAPersistence:
    """S7: store_agreement/list_agreements survive service re-instantiation."""

    @pytest.mark.asyncio
    async def test_store_and_list_survive_reinstantiation(self, tmp_path):
        """Agreements persisted via store_path outlive the service instance."""
        store = tmp_path / "baa_agreements.json"
        svc1 = BAAService(store_path=store)
        ag_id = await svc1.store_agreement(
            org_name="Persistence Clinic",
            ba_name="Persist BA",
            signed_by="admin@persist.com",
        )

        svc2 = BAAService(store_path=store)
        summaries = await svc2.list_agreements()
        assert any(s.id == ag_id for s in summaries)

        agreement = await svc2.get_agreement(ag_id)
        assert agreement.org_name == "Persistence Clinic"
        assert agreement.ba_name == "Persist BA"
        assert agreement.status == "active"

    @pytest.mark.asyncio
    async def test_store_file_is_0600(self, tmp_path):
        """The persisted store is written with 0600 permissions."""
        import stat

        store = tmp_path / "baa_agreements.json"
        svc = BAAService(store_path=store)
        await svc.store_agreement(
            org_name="Perm Clinic", ba_name="Perm BA", signed_by="signer@x.com"
        )
        assert store.exists()
        assert stat.S_IMODE(store.stat().st_mode) == 0o600

    @pytest.mark.asyncio
    async def test_db_factory_supplies_store_path(self, tmp_path):
        """db_factory is used to resolve the persistence store."""
        store = tmp_path / "via_factory.json"
        svc1 = BAAService(db_factory=lambda: store)
        ag_id = await svc1.store_agreement(
            org_name="Factory Clinic", ba_name="Factory BA", signed_by="f@x.com"
        )

        svc2 = BAAService(db_factory=lambda: store)
        assert any(s.id == ag_id for s in await svc2.list_agreements())

    @pytest.mark.asyncio
    async def test_bare_service_stays_in_memory(self):
        """Without a store path the service must not persist (backward compat)."""
        svc1 = BAAService()
        ag_id = await svc1.store_agreement(
            org_name="Mem Clinic", ba_name="Mem BA", signed_by="m@x.com"
        )

        svc2 = BAAService()
        assert not any(s.id == ag_id for s in await svc2.list_agreements())


class TestBAASandbox:
    """S7: Jinja environment is sandboxed and user input is escaped."""

    @pytest.mark.asyncio
    async def test_jinja_environment_is_sandboxed(self, tmp_path):
        """Dangerous template attribute access raises SecurityError."""
        from jinja2.exceptions import SecurityError

        from meeting_notes_ai.hipaa.config import HIPAAConfig

        tpl = tmp_path / "evil.md.jinja"
        tpl.write_text("Covered Entity: {{ org_name }} {{ ''.__class__.__mro__ }}")
        svc = BAAService(config=HIPAAConfig(baa_template_path=str(tpl)))
        with pytest.raises(SecurityError):
            await svc.generate_template("Clinic", "BA", "2026-08-01")

    @pytest.mark.asyncio
    async def test_template_escapes_user_input(self, tmp_path):
        """org_name/ba_name are HTML-escaped in the rendered output."""
        from meeting_notes_ai.hipaa.config import HIPAAConfig

        tpl = tmp_path / "escape.md.jinja"
        tpl.write_text("Covered Entity: {{ org_name }} / BA: {{ ba_name }}")
        svc = BAAService(config=HIPAAConfig(baa_template_path=str(tpl)))
        out = await svc.generate_template(
            '<script>alert("x")</script>', "A & B", "2026-08-01"
        )
        assert "<script>" not in out
        assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in out
        assert "A &amp; B" in out
