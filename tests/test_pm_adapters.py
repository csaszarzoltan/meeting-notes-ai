"""Pre-development tests for PM adapters and sync endpoint.

Tests follow the three-layer structure:
  1. Import/class-existence tests — verify module loads, classes exist
  2. Signature/interface tests — verify method signatures, parameters
  3. Behavioral "future" tests — assert NotImplementedError (RED phase)

Stub adapters raise NotImplementedError so interface tests pass immediately
and behavioral tests fail clearly until implementation.

Run: .venv/bin/python -m pytest tests/test_pm_adapters.py -v
"""

from __future__ import annotations

import inspect
from dataclasses import is_dataclass
from typing import Any

import pytest

from meeting_notes_ai.services.integrations import (
    PM_PROVIDERS,
    PROVIDER_REGISTRY,
    Adapter,
    AdapterAuth,
    AdapterAuthError,
    AdapterConnection,
    AdapterNotFoundError,
    AdapterTaskResult,
    AdapterUnavailableError,
    AdapterValidationError,
    AsanaAdapter,
    JiraAdapter,
    LinearAdapter,
    TodoistAdapter,
    get_adapter,
)

pytestmark = pytest.mark.quick


# ── Sample action dict for behavioral tests ─────────────────────────────────────

SAMPLE_ACTION: dict[str, Any] = {
    "id": "action-abc",
    "title": "Ship the Q3 report",
    "owner": "Maya",
    "due": "2026-08-12",
    "meeting_id": "meeting-123",
    "meeting": "Q3 planning",
    "timestamp": "00:00",
    "status": "confirmed",
    "destination": "Jira",
    "external_id": None,
}

SAMPLE_AUTH_JIRA = AdapterAuth(
    provider="jira",
    token="jira-oauth-token-xxx",
    site_url="https://acme.atlassian.net",
    email="maya@acme.com",
    default_project="ACME",
)

SAMPLE_AUTH_LINEAR = AdapterAuth(
    provider="linear",
    token="lin_api_xxx",
    workspace_url="https://acme.linear.app",
    default_project="team-uuid-001",
)

SAMPLE_AUTH_ASANA = AdapterAuth(
    provider="asana",
    token="1/xxxxx:yyyyy",
    default_project="workspace-gid-001",
)

SAMPLE_AUTH_TODOIST = AdapterAuth(
    provider="todoist",
    token="abcdef1234567890",
)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: Interface tests (should PASS immediately against stubs)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdapterDataclasses:
    """Verify AdapterAuth, AdapterConnection, AdapterTaskResult are frozen dataclasses."""

    def test_adapter_auth_is_dataclass(self):
        assert is_dataclass(AdapterAuth)

    def test_adapter_auth_frozen(self):
        auth = AdapterAuth(provider="jira", token="tok")
        with pytest.raises(AttributeError):
            auth.token = "changed"  # type: ignore[misc]

    def test_adapter_auth_fields(self):
        sig = inspect.signature(AdapterAuth)
        assert "provider" in sig.parameters
        assert "token" in sig.parameters
        assert "site_url" in sig.parameters
        assert "email" in sig.parameters
        assert "workspace_url" in sig.parameters
        assert "default_project" in sig.parameters

    def test_adapter_auth_defaults(self):
        auth = AdapterAuth(provider="jira", token="tok")
        assert auth.site_url == ""
        assert auth.email == ""
        assert auth.workspace_url == ""
        assert auth.default_project == ""

    def test_adapter_connection_is_dataclass(self):
        assert is_dataclass(AdapterConnection)

    def test_adapter_connection_fields(self):
        sig = inspect.signature(AdapterConnection)
        assert "account_email" in sig.parameters
        assert "account_url" in sig.parameters
        assert "token_expires_at" in sig.parameters

    def test_adapter_connection_defaults(self):
        conn = AdapterConnection(account_email="a@b.com", account_url="https://b.com")
        assert conn.token_expires_at is None

    def test_adapter_task_result_is_dataclass(self):
        assert is_dataclass(AdapterTaskResult)

    def test_adapter_task_result_fields(self):
        sig = inspect.signature(AdapterTaskResult)
        assert "external_id" in sig.parameters
        assert "external_url" in sig.parameters
        assert "raw" in sig.parameters

    def test_adapter_task_result_raw_default(self):
        result = AdapterTaskResult(external_id="EXT-1", external_url="https://x.com/1")
        assert result.raw == {}


class TestAdapterExceptionHierarchy:
    """Verify exception classes exist and inherit from PMAdapterError."""

    def test_pm_adapter_error_is_exception(self):
        from meeting_notes_ai.services.integrations.base import PMAdapterError
        assert issubclass(PMAdapterError, Exception)

    def test_auth_error_inherits(self):
        from meeting_notes_ai.services.integrations.base import PMAdapterError
        assert issubclass(AdapterAuthError, PMAdapterError)

    def test_unavailable_error_inherits(self):
        from meeting_notes_ai.services.integrations.base import PMAdapterError
        assert issubclass(AdapterUnavailableError, PMAdapterError)

    def test_validation_error_inherits(self):
        from meeting_notes_ai.services.integrations.base import PMAdapterError
        assert issubclass(AdapterValidationError, PMAdapterError)

    def test_not_found_error_inherits(self):
        from meeting_notes_ai.services.integrations.base import PMAdapterError
        assert issubclass(AdapterNotFoundError, PMAdapterError)


class TestAdapterABC:
    """Verify Adapter ABC exists with correct class variables and abstract methods."""

    def test_adapter_is_abstract(self):
        from abc import ABC as _ABC
        assert issubclass(Adapter, _ABC)
        with pytest.raises(TypeError):
            Adapter()  # type: ignore[abstract]

    def test_adapter_has_class_variables(self):
        # With `from __future__ import annotations`, ClassVar without a default
        # only exists in __annotations__, not as an attribute. Only connect_timeout
        # has a default value, so it's a real attribute.
        assert "provider" in Adapter.__annotations__
        assert "display_name" in Adapter.__annotations__
        assert "auth_type" in Adapter.__annotations__
        assert hasattr(Adapter, "connect_timeout")

    def test_adapter_has_healthcheck_default(self):
        assert hasattr(Adapter, "healthcheck")


class TestJiraAdapterInterface:
    """Verify JiraAdapter class exists with correct interface."""

    def test_exists(self):
        assert JiraAdapter is not None

    def test_inherits_adapter(self):
        assert issubclass(JiraAdapter, Adapter)

    def test_class_variables(self):
        assert JiraAdapter.provider == "jira"
        assert JiraAdapter.display_name == "Jira"
        assert JiraAdapter.auth_type == "oauth2"

    def test_connect_signature(self):
        sig = inspect.signature(JiraAdapter.connect)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "auth" in params
        assert sig.parameters["auth"].annotation in (AdapterAuth, "AdapterAuth")

    def test_connect_return_annotation(self):
        sig = inspect.signature(JiraAdapter.connect)
        ret = sig.return_annotation
        assert ret == AdapterConnection or ret == "AdapterConnection"

    def test_create_task_signature(self):
        sig = inspect.signature(JiraAdapter.create_task)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "action" in params
        assert "project" in params
        assert "idempotency_key" in params

    def test_create_task_action_annotation(self):
        sig = inspect.signature(JiraAdapter.create_task)
        annotation = sig.parameters["action"].annotation
        assert annotation == dict[str, Any] or annotation == "dict[str, Any]"

    def test_create_task_project_default(self):
        sig = inspect.signature(JiraAdapter.create_task)
        assert sig.parameters["project"].default is None

    def test_create_task_idempotency_key_default(self):
        sig = inspect.signature(JiraAdapter.create_task)
        assert sig.parameters["idempotency_key"].default is None

    def test_create_task_return_annotation(self):
        sig = inspect.signature(JiraAdapter.create_task)
        ret = sig.return_annotation
        assert ret == AdapterTaskResult or ret == "AdapterTaskResult"

    def test_instantiation(self):
        adapter = JiraAdapter()
        assert isinstance(adapter, Adapter)


class TestLinearAdapterInterface:
    """Verify LinearAdapter class exists with correct interface."""

    def test_exists(self):
        assert LinearAdapter is not None

    def test_inherits_adapter(self):
        assert issubclass(LinearAdapter, Adapter)

    def test_class_variables(self):
        assert LinearAdapter.provider == "linear"
        assert LinearAdapter.display_name == "Linear"
        assert LinearAdapter.auth_type == "api_key"

    def test_connect_signature(self):
        sig = inspect.signature(LinearAdapter.connect)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "auth" in params
        assert sig.parameters["auth"].annotation in (AdapterAuth, "AdapterAuth")

    def test_connect_return_annotation(self):
        sig = inspect.signature(LinearAdapter.connect)
        ret = sig.return_annotation
        assert ret == AdapterConnection or ret == "AdapterConnection"

    def test_create_task_signature(self):
        sig = inspect.signature(LinearAdapter.create_task)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "action" in params
        assert "project" in params
        assert "idempotency_key" in params

    def test_create_task_project_default(self):
        sig = inspect.signature(LinearAdapter.create_task)
        assert sig.parameters["project"].default is None

    def test_create_task_return_annotation(self):
        sig = inspect.signature(LinearAdapter.create_task)
        ret = sig.return_annotation
        assert ret == AdapterTaskResult or ret == "AdapterTaskResult"

    def test_instantiation(self):
        adapter = LinearAdapter()
        assert isinstance(adapter, Adapter)


class TestAsanaAdapterInterface:
    """Verify AsanaAdapter class exists with correct interface."""

    def test_exists(self):
        assert AsanaAdapter is not None

    def test_inherits_adapter(self):
        assert issubclass(AsanaAdapter, Adapter)

    def test_class_variables(self):
        assert AsanaAdapter.provider == "asana"
        assert AsanaAdapter.display_name == "Asana"
        assert AsanaAdapter.auth_type == "pat"

    def test_connect_signature(self):
        sig = inspect.signature(AsanaAdapter.connect)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "auth" in params
        assert sig.parameters["auth"].annotation in (AdapterAuth, "AdapterAuth")

    def test_connect_return_annotation(self):
        sig = inspect.signature(AsanaAdapter.connect)
        ret = sig.return_annotation
        assert ret == AdapterConnection or ret == "AdapterConnection"

    def test_create_task_signature(self):
        sig = inspect.signature(AsanaAdapter.create_task)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "action" in params
        assert "project" in params
        assert "idempotency_key" in params

    def test_create_task_project_default(self):
        sig = inspect.signature(AsanaAdapter.create_task)
        assert sig.parameters["project"].default is None

    def test_create_task_return_annotation(self):
        sig = inspect.signature(AsanaAdapter.create_task)
        ret = sig.return_annotation
        assert ret == AdapterTaskResult or ret == "AdapterTaskResult"

    def test_instantiation(self):
        adapter = AsanaAdapter()
        assert isinstance(adapter, Adapter)


class TestTodoistAdapterInterface:
    """Verify TodoistAdapter class exists with correct interface."""

    def test_exists(self):
        assert TodoistAdapter is not None

    def test_inherits_adapter(self):
        assert issubclass(TodoistAdapter, Adapter)

    def test_class_variables(self):
        assert TodoistAdapter.provider == "todoist"
        assert TodoistAdapter.display_name == "Todoist"
        assert TodoistAdapter.auth_type == "rest_token"

    def test_connect_signature(self):
        sig = inspect.signature(TodoistAdapter.connect)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "auth" in params
        assert sig.parameters["auth"].annotation in (AdapterAuth, "AdapterAuth")

    def test_connect_return_annotation(self):
        sig = inspect.signature(TodoistAdapter.connect)
        ret = sig.return_annotation
        assert ret == AdapterConnection or ret == "AdapterConnection"

    def test_create_task_signature(self):
        sig = inspect.signature(TodoistAdapter.create_task)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "action" in params
        assert "project" in params
        assert "idempotency_key" in params

    def test_create_task_project_default(self):
        sig = inspect.signature(TodoistAdapter.create_task)
        assert sig.parameters["project"].default is None

    def test_create_task_return_annotation(self):
        sig = inspect.signature(TodoistAdapter.create_task)
        ret = sig.return_annotation
        assert ret == AdapterTaskResult or ret == "AdapterTaskResult"

    def test_instantiation(self):
        adapter = TodoistAdapter()
        assert isinstance(adapter, Adapter)


class TestRegistryInterface:
    """Verify PROVIDER_REGISTRY and get_adapter work correctly."""

    def test_pm_providers_is_frozen_set(self):
        assert isinstance(PM_PROVIDERS, frozenset)
        assert PM_PROVIDERS == frozenset({"jira", "linear", "asana", "todoist"})

    def test_provider_registry_has_all_providers(self):
        assert "jira" in PROVIDER_REGISTRY
        assert "linear" in PROVIDER_REGISTRY
        assert "asana" in PROVIDER_REGISTRY
        assert "todoist" in PROVIDER_REGISTRY

    def test_get_adapter_jira(self):
        cls = get_adapter("jira")
        assert cls is JiraAdapter

    def test_get_adapter_linear(self):
        cls = get_adapter("linear")
        assert cls is LinearAdapter

    def test_get_adapter_asana(self):
        cls = get_adapter("asana")
        assert cls is AsanaAdapter

    def test_get_adapter_todoist(self):
        cls = get_adapter("todoist")
        assert cls is TodoistAdapter

    def test_get_adapter_unknown_raises(self):
        with pytest.raises(AdapterNotFoundError):
            get_adapter("unknown")

    def test_get_adapter_returns_subclass_of_adapter(self):
        for name in PM_PROVIDERS:
            cls = get_adapter(name)
            assert issubclass(cls, Adapter)


class TestQueueRouteWired:
    """Verify the queue route exists on the workspace router."""

    def test_queue_route_exists(self):
        from meeting_notes_ai.routes.workspace import router
        route_paths = [getattr(r, "path", None) for r in router.routes]
        assert "/api/v1/workspace/actions/{action_id}/queue" in route_paths

    def test_integrations_route_exists(self):
        from meeting_notes_ai.routes.workspace import router
        route_paths = [getattr(r, "path", None) for r in router.routes]
        assert "/api/v1/workspace/integrations" in route_paths


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Behavioral tests (should FAIL with NotImplementedError)
# ═══════════════════════════════════════════════════════════════════════════════


class TestJiraAdapterBehavior:
    """Behavioral tests for JiraAdapter — all should raise NotImplementedError."""

    def test_connect_raises_not_implemented(self):
        adapter = JiraAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.connect(SAMPLE_AUTH_JIRA))

    def test_create_task_raises_not_implemented(self):
        adapter = JiraAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.create_task(SAMPLE_ACTION))

    def test_connect_raises_not_implemented_explicit_auth(self):
        adapter = JiraAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.connect(SAMPLE_AUTH_JIRA))


class TestLinearAdapterBehavior:
    """Behavioral tests for LinearAdapter — all should raise NotImplementedError."""

    def test_connect_raises_not_implemented(self):
        adapter = LinearAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))

    def test_create_task_raises_not_implemented(self):
        adapter = LinearAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.create_task(SAMPLE_ACTION))


class TestAsanaAdapterBehavior:
    """Behavioral tests for AsanaAdapter — all should raise NotImplementedError."""

    def test_connect_raises_not_implemented(self):
        adapter = AsanaAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.connect(SAMPLE_AUTH_ASANA))

    def test_create_task_raises_not_implemented(self):
        adapter = AsanaAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.create_task(SAMPLE_ACTION))


class TestTodoistAdapterBehavior:
    """Behavioral tests for TodoistAdapter — all should raise NotImplementedError."""

    def test_connect_raises_not_implemented(self):
        adapter = TodoistAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.connect(SAMPLE_AUTH_TODOIST))

    def test_create_task_raises_not_implemented(self):
        adapter = TodoistAdapter()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.create_task(SAMPLE_ACTION))
