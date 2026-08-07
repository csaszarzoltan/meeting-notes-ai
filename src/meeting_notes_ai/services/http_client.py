"""Shared HTTP client factory and provider error type for PM integrations.

Provides a single seam for transport-level mocking (respx/httpx.MockTransport)
and keeps per-call client churn low.
"""

from __future__ import annotations

import httpx

_DEFAULT_TIMEOUT = 15.0


def get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client with sensible defaults.

    Callers should ``await`` the client's context manager or use it directly;
    the client is lightweight enough to create per-request if needed.
    """
    return httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True)


class ProviderHTTPError(Exception):
    """Transport-level error from a provider API call.

    Carries ``status_code``, ``provider`` slug, and a **sanitized** message
    safe for user display.  Adapters must catch this and re-raise as the
    appropriate ``PMAdapterError`` subclass.
    """

    def __init__(self, status_code: int, provider: str, message: str) -> None:
        self.status_code = status_code
        self.provider = provider
        self.message = message
        super().__init__(f"{provider}: {status_code} {message}")
