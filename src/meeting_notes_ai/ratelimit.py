"""Thread-safe in-memory token bucket rate limiting."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    capacity: int = 100
    fill_rate: float = 100 / 86_400

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be positive")
        if self.fill_rate <= 0:
            raise ValueError("fill_rate must be positive")


class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 100, fill_rate: float = 100 / 86_400) -> None:
        self.capacity = capacity
        self.fill_rate = fill_rate
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _refill(self, key: str, now: float) -> float:
        tokens, last = self._buckets.get(key, (float(self.capacity), now))
        return min(float(self.capacity), tokens + max(0.0, now - last) * self.fill_rate)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens = self._refill(key, now)
            allowed = tokens >= 1.0
            self._buckets[key] = (tokens - 1.0 if allowed else tokens, now)
            return allowed

    def get_remaining(self, key: str) -> tuple[int, float]:
        now = time.monotonic()
        with self._lock:
            tokens = self._refill(key, now)
            self._buckets[key] = (tokens, now)
            seconds_until_full = max(0.0, (self.capacity - tokens) / self.fill_rate)
            return max(0, math.floor(tokens)), seconds_until_full

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            tokens = self._refill(key, now)
            return max(1, math.ceil(max(0.0, 1.0 - tokens) / self.fill_rate))

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)
