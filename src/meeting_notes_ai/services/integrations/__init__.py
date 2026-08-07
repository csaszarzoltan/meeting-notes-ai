"""PM tool adapters for Jira, Linear, Asana, and Todoist."""

from meeting_notes_ai.services.integrations.asana import AsanaAdapter
from meeting_notes_ai.services.integrations.base import (
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
    PMAdapterError,
    get_adapter,
)
from meeting_notes_ai.services.integrations.jira import JiraAdapter
from meeting_notes_ai.services.integrations.linear import LinearAdapter
from meeting_notes_ai.services.integrations.todoist import TodoistAdapter

__all__ = [
    "Adapter",
    "AdapterAuth",
    "AdapterConnection",
    "AdapterTaskResult",
    "PMAdapterError",
    "AdapterAuthError",
    "AdapterUnavailableError",
    "AdapterValidationError",
    "AdapterNotFoundError",
    "PM_PROVIDERS",
    "PROVIDER_REGISTRY",
    "get_adapter",
    "JiraAdapter",
    "LinearAdapter",
    "AsanaAdapter",
    "TodoistAdapter",
]
