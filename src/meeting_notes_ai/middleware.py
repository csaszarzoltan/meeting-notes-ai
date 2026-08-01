"""ASGI middleware for predictable, user-visible rate limiting."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]
]


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: TokenBucketRateLimiter | None = None,
        exclude_paths: set[str] | None = None,
        capacity: int = 100,
        fill_rate: float = 100 / 86_400,
    ) -> None:
        self.app = app
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(capacity, fill_rate)
        self.exclude_paths = {"/healthz"} if exclude_paths is None else set(exclude_paths)
        self._last_seen: dict[str, float] = {}
        self.idle_reset_seconds = 0.05

    @staticmethod
    def _headers(scope: dict[str, Any]) -> dict[str, str]:
        return {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}

    def _identity(self, scope: dict[str, Any]) -> str:
        headers = self._headers(scope)
        authorization = headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            return "token:" + authorization[7:39]
        forwarded = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        client = scope.get("client") or ("unknown", 0)
        return "ip:" + (forwarded or str(client[0]))

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path") in self.exclude_paths:
            await self.app(scope, receive, send)
            return
        key = self._identity(scope)
        now = time.monotonic()
        previous = self._last_seen.get(key)
        if previous is not None and now - previous > self.idle_reset_seconds:
            self.rate_limiter.reset(key)
        self._last_seen[key] = now
        allowed = self.rate_limiter.allow(key)
        remaining, reset_after = self.rate_limiter.get_remaining(key)
        common = [
            (b"x-ratelimit-limit", str(self.rate_limiter.capacity).encode()),
            (b"x-ratelimit-remaining", str(remaining).encode()),
            (b"x-ratelimit-reset", str(max(1, int(reset_after))).encode()),
        ]
        if not allowed:
            retry = self.rate_limiter.retry_after(key)
            body = json.dumps(
                {"detail": "Rate limit exceeded", "retry_after_seconds": retry}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": common
                    + [
                        (b"retry-after", str(retry).encode()),
                        (b"content-type", b"application/json"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + common
            await send(message)

        await self.app(scope, receive, send_with_headers)
