"""Base adapter interface and shared types for PM tool integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class AdapterAuth:
    """Parsed, decrypted credentials handed to an adapter by the route layer.

    Each provider stores exactly one secret string in its credential blob:
      jira    -> access token (OAuth2 Bearer)      | plus site_url, email
      linear  -> API key (Bearer)                  | plus workspace_url
      asana   -> PAT (Bearer)                      | plus default_workspace_gid
      todoist -> REST token (Bearer)               | (account url derived)
    """
    provider: str
    token: str                       # decrypted secret, never persisted again
    site_url: str = ""               # jira: https://<site>.atlassian.net
    email: str = ""                  # jira/linear/asana display account
    workspace_url: str = ""          # linear: https://<workspace>.linear.app
    default_project: str = ""        # optional default project id/gid


@dataclass(frozen=True)
class AdapterConnection:
    """Result of a successful connect() call."""
    account_email: str
    account_url: str
    token_expires_at: str | None = None   # ISO-8601 UTC; None = non-expiring token


@dataclass(frozen=True)
class AdapterTaskResult:
    """Result of a successful create_task() call."""
    # provider's native task id (Jira key, Linear UUID, Asana gid, Todoist id)
    external_id: str
    external_url: str     # https link a human can open
    raw: dict[str, Any] = field(default_factory=dict)  # provider response, for tests/debug


class PMAdapterError(Exception):
    """Base adapter error — message is ALWAYS safe to show to users."""
    pass


class AdapterAuthError(PMAdapterError):
    """401/403 -> HTTP 401 're-authorize'."""
    pass


class AdapterUnavailableError(PMAdapterError):
    """5xx/timeout -> HTTP 502 friendly retry."""
    pass


class AdapterValidationError(PMAdapterError):
    """400/422 (bad project, missing field) -> HTTP 422."""
    pass


class AdapterNotFoundError(PMAdapterError):
    """Unknown provider -> HTTP 404."""
    pass


class Adapter(ABC):
    """Abstract base class for PM tool adapters."""

    provider: ClassVar[str]            # "jira" | "linear" | "asana" | "todoist"
    display_name: ClassVar[str]        # "Jira" | "Linear" | "Asana" | "Todoist"
    auth_type: ClassVar[str]           # "oauth2" | "api_key" | "pat" | "rest_token"
    connect_timeout: ClassVar[float] = 15.0

    @abstractmethod
    async def connect(self, auth: AdapterAuth) -> AdapterConnection:
        """Validate credentials with a lightweight provider call.

        Returns identity + account URL for GET /integrations.
        Raises PMAdapterError on invalid/expired credentials (401/403),
        AdapterUnavailableError on provider outages (5xx/timeouts).
        """

    @abstractmethod
    async def create_task(self, action: dict[str, Any], project: str | None = None,
                          idempotency_key: str | None = None) -> AdapterTaskResult:
        """Create a real task in the provider.

        action: workspace action dict (id, title, owner, due, meeting_id, meeting, ...)
        project: provider project id/key/gid (None -> provider default)
        idempotency_key: "<meeting_id>:<action_id>" (see §7); None = no header
        """

    async def healthcheck(self, auth: AdapterAuth) -> bool:
        """Optional; default True. Implementations may probe /status."""
        return True


# Provider registry
PM_PROVIDERS = frozenset({"jira", "linear", "asana", "todoist"})

PROVIDER_REGISTRY: dict[str, str] = {
    "jira": "JiraAdapter",
    "linear": "LinearAdapter",
    "asana": "AsanaAdapter",
    "todoist": "TodoistAdapter",
}


def get_adapter(provider: str) -> type[Adapter]:
    """Get adapter class by provider slug."""
    if provider not in PM_PROVIDERS:
        raise AdapterNotFoundError(f"Unknown provider: {provider}")
    cls_name = PROVIDER_REGISTRY[provider]
    # Import lazily to avoid circular imports
    module = __import__(
        f"meeting_notes_ai.services.integrations.{provider}",
        fromlist=[cls_name]
    )
    return getattr(module, cls_name)
