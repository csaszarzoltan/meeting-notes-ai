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

import httpx
import pytest
import respx

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
# ── respx mock helpers (transport-level mocking for behavioral tests) ─────────

def mock_jira_connect(router: respx.Router, auth: AdapterAuth) -> None:
    """Mock a successful Jira GET /rest/api/3/myself."""
    router.get(f"{auth.site_url.rstrip('/')}/rest/api/3/myself").mock(
        return_value=httpx.Response(
            200,
            json={
                "accountId": "12345",
                "emailAddress": auth.email,
                "displayName": "Maya",
                "active": True,
            },
        )
    )


def mock_jira_create_task(router: respx.Router, auth: AdapterAuth) -> None:
    """Mock a successful Jira POST /rest/api/3/issue."""
    router.post(f"{auth.site_url.rstrip('/')}/rest/api/3/issue").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "10001",
                "key": "ACME-123",
                "self": f"{auth.site_url.rstrip('/')}/rest/api/3/issue/10001",
            },
        )
    )


def mock_linear_connect(router: respx.Router, auth: AdapterAuth) -> None:
    """Mock a successful Linear GraphQL viewer query.

    Uses a side-effect dispatcher so the single route answers both the
    viewer query (connect) and the issueCreate mutation (create_task)
    correctly — both hit the same GraphQL endpoint.
    """
    url_key = auth.workspace_url.replace("https://", "").replace(".linear.app", "")

    def _dispatch(request):
        try:
            query = _parse_graphql_query(request)
        except Exception:
            query = ""
        if "ViewerInfo" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "viewer": {"id": "linear-user-123", "name": "Maya", "email": auth.email},
                        "organization": {"urlKey": url_key},
                    }
                },
            )
        return _linear_create_response()

    router.post("https://api.linear.app/graphql").mock(side_effect=_dispatch)


def _parse_graphql_query(request) -> str:
    """Extract the GraphQL ``query``/``mutation`` name from a request body."""
    import json as _json

    try:
        payload = _json.loads(request.content)
    except Exception:
        return ""
    if isinstance(payload, dict):
        return payload.get("query", "")
    return ""


def _linear_create_response() -> httpx.Response:
    """A successful Linear issueCreate mutation payload."""
    return httpx.Response(
        200,
        json={
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "linear-issue-123",
                        "identifier": "TEAM-123",
                        "url": "https://linear.app/team/issue/linear-issue-123",
                    },
                }
            }
        },
    )


def mock_linear_create_task(router: respx.Router) -> None:
    """Mock a successful Linear GraphQL issueCreate mutation.

    Same dispatcher as ``mock_linear_connect`` so connect() + create_task()
    each receive the correct GraphQL payload.
    """

    def _dispatch(request):
        try:
            query = _parse_graphql_query(request)
        except Exception:
            query = ""
        if "ViewerInfo" in query:
            # connect() was called first — return the viewer payload
            return httpx.Response(
                200,
                json={
                    "data": {
                        "viewer": {
                            "id": "linear-user-123",
                            "name": "Maya",
                            "email": "maya@acme.com",
                        },
                        "organization": {"urlKey": "acme"},
                    }
                },
            )
        return _linear_create_response()

    router.post("https://api.linear.app/graphql").mock(side_effect=_dispatch)


def mock_asana_connect(router: respx.Router, auth: AdapterAuth) -> None:
    """Mock successful Asana GET /users/me and GET /workspaces."""
    router.get("https://app.asana.com/api/1.0/users/me").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"gid": "12345", "email": auth.email, "name": "Maya"}},
        )
    )
    router.get("https://app.asana.com/api/1.0/workspaces").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": auth.default_project,
                        "name": "Test Workspace",
                        "permalink_url": "https://app.asana.com/0/12345/list",
                    }
                ]
            },
        )
    )


def mock_asana_create_task(router: respx.Router) -> None:
    """Mock a successful Asana POST /tasks."""
    router.post("https://app.asana.com/api/1.0/tasks").mock(
        return_value=httpx.Response(
            201,
            json={
                "data": {
                    "gid": "asana-task-123",
                    "name": "Ship the Q3 report",
                    "permalink_url": "https://app.asana.com/0/12345/asana-task-123",
                }
            },
        )
    )


def mock_todoist_connect(router: respx.Router) -> None:
    """Mock a successful Todoist GET /projects."""
    router.get("https://api.todoist.com/rest/v2/projects").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "12345", "name": "Test Project", "url": "https://todoist.com/project/12345"}],
        )
    )


def mock_todoist_create_task(router: respx.Router) -> None:
    """Mock a successful Todoist POST /tasks."""
    router.post("https://api.todoist.com/rest/v2/tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "todoist-task-123",
                "content": "Ship the Q3 report",
                "url": "https://todoist.com/showTask?id=todoist-task-123",
            },
        )
    )


# PART 2: Behavioral tests (should FAIL with NotImplementedError)
# ═══════════════════════════════════════════════════════════════════════════════


class TestJiraAdapterBehavior:
    """Behavioral tests for JiraAdapter — verified against mocked transport."""

    def test_connect_returns_connection(self, respx_mock: respx.Router) -> None:
        mock_jira_connect(respx_mock, SAMPLE_AUTH_JIRA)
        adapter = JiraAdapter()
        import asyncio
        conn = asyncio.run(adapter.connect(SAMPLE_AUTH_JIRA))
        assert isinstance(conn, AdapterConnection)
        assert conn.account_email == SAMPLE_AUTH_JIRA.email
        assert conn.account_url == SAMPLE_AUTH_JIRA.site_url.rstrip("/")

    def test_create_task_returns_result(self, respx_mock: respx.Router) -> None:
        mock_jira_connect(respx_mock, SAMPLE_AUTH_JIRA)
        mock_jira_create_task(respx_mock, SAMPLE_AUTH_JIRA)
        adapter = JiraAdapter()
        import asyncio
        asyncio.run(adapter.connect(SAMPLE_AUTH_JIRA))
        result = asyncio.run(adapter.create_task(SAMPLE_ACTION))
        assert isinstance(result, AdapterTaskResult)
        assert result.external_id == "ACME-123"
        assert "browse/ACME-123" in result.external_url

    def test_connect_returns_connection_explicit_auth(self, respx_mock: respx.Router) -> None:
        mock_jira_connect(respx_mock, SAMPLE_AUTH_JIRA)
        adapter = JiraAdapter()
        import asyncio
        conn = asyncio.run(adapter.connect(SAMPLE_AUTH_JIRA))
        assert isinstance(conn, AdapterConnection)
        assert conn.account_url == "https://acme.atlassian.net"


class TestLinearAdapterBehavior:
    """Behavioral tests for LinearAdapter — verified against mocked transport."""

    def test_connect_returns_connection(self, respx_mock: respx.Router) -> None:
        mock_linear_connect(respx_mock, SAMPLE_AUTH_LINEAR)
        adapter = LinearAdapter()
        import asyncio
        conn = asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))
        assert isinstance(conn, AdapterConnection)
        assert conn.account_email == SAMPLE_AUTH_LINEAR.email
        assert conn.account_url == "https://acme.linear.app"

    def test_create_task_returns_result(self, respx_mock: respx.Router) -> None:
        mock_linear_connect(respx_mock, SAMPLE_AUTH_LINEAR)
        mock_linear_create_task(respx_mock)
        adapter = LinearAdapter()
        import asyncio
        asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))
        result = asyncio.run(adapter.create_task(SAMPLE_ACTION))
        assert isinstance(result, AdapterTaskResult)
        assert result.external_id == "linear-issue-123"
        assert "linear.app" in result.external_url

    def test_connect_graphql_error_200_raises_auth_error(
        self, respx_mock: respx.Router
    ) -> None:
        """HTTP 200 with an `errors` array must raise AdapterAuthError, not crash."""
        respx_mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Authentication required",
                            "extensions": {"code": "AUTHENTICATION_REQUIRED"},
                        }
                    ]
                },
            )
        )
        adapter = LinearAdapter()
        import asyncio
        with pytest.raises(AdapterAuthError):
            asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))

    def test_connect_graphql_errors_null_viewer_raises_auth_error(
        self, respx_mock: respx.Router
    ) -> None:
        """`data: {"viewer": null}` must raise AdapterAuthError (unauthenticated)."""
        respx_mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"viewer": None, "organization": {"urlKey": "acme"}}},
            )
        )
        adapter = LinearAdapter()
        import asyncio
        with pytest.raises(AdapterAuthError):
            asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))

    def test_connect_graphql_team_error_raises_validation_error(
        self, respx_mock: respx.Router
    ) -> None:
        """A GraphQL team-scoped error surfaces as AdapterValidationError."""
        respx_mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={"errors": [{"message": "Team not found: team-uuid-001"}]},
            )
        )
        adapter = LinearAdapter()
        import asyncio
        with pytest.raises(AdapterValidationError):
            asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))

    def test_connect_graphql_rate_limit_raises_unavailable_error(
        self, respx_mock: respx.Router
    ) -> None:
        """A GraphQL rate-limit error surfaces as AdapterUnavailableError."""
        respx_mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={"errors": [{"message": "Rate limit exceeded, retry later"}]},
            )
        )
        adapter = LinearAdapter()
        import asyncio
        with pytest.raises(AdapterUnavailableError):
            asyncio.run(adapter.connect(SAMPLE_AUTH_LINEAR))

    def test_create_task_graphql_error_200_raises_auth_error(
        self, respx_mock: respx.Router
    ) -> None:
        """create_task must also surface a 200+errors body as a friendly error."""
        respx_mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [
                        {"message": "Invalid API key", "extensions": {"code": "INVALID_API_KEY"}}
                    ]
                },
            )
        )
        adapter = LinearAdapter()
        adapter._auth = SAMPLE_AUTH_LINEAR  # noqa: SLF001 — bypass connect()
        import asyncio
        with pytest.raises(AdapterAuthError):
            asyncio.run(adapter.create_task(SAMPLE_ACTION))


class TestAsanaAdapterBehavior:
    """Behavioral tests for AsanaAdapter — verified against mocked transport."""

    def test_connect_returns_connection(self, respx_mock: respx.Router) -> None:
        mock_asana_connect(respx_mock, SAMPLE_AUTH_ASANA)
        adapter = AsanaAdapter()
        import asyncio
        conn = asyncio.run(adapter.connect(SAMPLE_AUTH_ASANA))
        assert isinstance(conn, AdapterConnection)
        assert conn.account_email == SAMPLE_AUTH_ASANA.email
        assert "app.asana.com" in conn.account_url

    def test_create_task_returns_result(self, respx_mock: respx.Router) -> None:
        mock_asana_connect(respx_mock, SAMPLE_AUTH_ASANA)
        mock_asana_create_task(respx_mock)
        adapter = AsanaAdapter()
        import asyncio
        asyncio.run(adapter.connect(SAMPLE_AUTH_ASANA))
        result = asyncio.run(adapter.create_task(SAMPLE_ACTION))
        assert isinstance(result, AdapterTaskResult)
        assert result.external_id == "asana-task-123"
        assert "asana.com" in result.external_url


class TestTodoistAdapterBehavior:
    """Behavioral tests for TodoistAdapter — verified against mocked transport."""

    def test_connect_returns_connection(self, respx_mock: respx.Router) -> None:
        mock_todoist_connect(respx_mock)
        adapter = TodoistAdapter()
        import asyncio
        conn = asyncio.run(adapter.connect(SAMPLE_AUTH_TODOIST))
        assert isinstance(conn, AdapterConnection)
        assert conn.account_url == "https://todoist.com"

    def test_create_task_returns_result(self, respx_mock: respx.Router) -> None:
        mock_todoist_connect(respx_mock)
        mock_todoist_create_task(respx_mock)
        adapter = TodoistAdapter()
        import asyncio
        asyncio.run(adapter.connect(SAMPLE_AUTH_TODOIST))
        result = asyncio.run(adapter.create_task(SAMPLE_ACTION))
        assert isinstance(result, AdapterTaskResult)
        assert result.external_id == "todoist-task-123"
        assert "todoist.com" in result.external_url
