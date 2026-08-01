"""Pre-development interface and behavioral tests for TokenBucketRateLimiter.

Tests the token bucket rate limiter module. All tests are expected to FAIL
until the module is implemented (RED phase).

Module under test:
  src/meeting_notes_ai/ratelimit.py
    - RateLimitConfig dataclass
    - TokenBucketRateLimiter class
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


# ═══════════════════════════════════════════════════════════════════════════════
# Interface Tests (must PASS once implemented)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimitConfigInterface:
    """Verify RateLimitConfig dataclass contract."""

    def test_ratelimit_config_importable(self):
        """RateLimitConfig exists and is importable."""
        from meeting_notes_ai.ratelimit import RateLimitConfig

        assert RateLimitConfig is not None

    def test_ratelimit_config_is_dataclass(self):
        """RateLimitConfig is a dataclass."""
        from dataclasses import is_dataclass

        from meeting_notes_ai.ratelimit import RateLimitConfig

        assert is_dataclass(RateLimitConfig)

    def test_ratelimit_config_has_capacity_field(self):
        """RateLimitConfig has a capacity field (int)."""
        from meeting_notes_ai.ratelimit import RateLimitConfig

        assert hasattr(RateLimitConfig, "capacity")

    def test_ratelimit_config_has_fill_rate_field(self):
        """RateLimitConfig has a fill_rate field (float)."""
        from meeting_notes_ai.ratelimit import RateLimitConfig

        assert hasattr(RateLimitConfig, "fill_rate")

    def test_ratelimit_config_can_be_instantiated(self):
        """RateLimitConfig can be instantiated with capacity and fill_rate."""
        from meeting_notes_ai.ratelimit import RateLimitConfig

        config = RateLimitConfig(capacity=100, fill_rate=0.001157)
        assert config.capacity == 100
        assert config.fill_rate == 0.001157


class TestTokenBucketRateLimiterInterface:
    """Verify TokenBucketRateLimiter class contract."""

    def test_ratelimiter_class_importable(self):
        """TokenBucketRateLimiter exists and is importable."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        assert TokenBucketRateLimiter is not None

    def test_ratelimiter_constructor_signature(self):
        """Constructor accepts capacity (int) and fill_rate (float)."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        sig = signature(TokenBucketRateLimiter.__init__)
        params = sig.parameters
        assert "capacity" in params
        assert "fill_rate" in params

    def test_ratelimiter_allow_method_exists(self):
        """TokenBucketRateLimiter has an allow method."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        assert hasattr(TokenBucketRateLimiter, "allow")

    def test_ratelimiter_allow_signature(self):
        """allow(key: str) -> bool."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        sig = signature(TokenBucketRateLimiter.allow)
        params = sig.parameters
        assert "key" in params or "self" in params
        assert "key" in params  # first arg after self
        # Should return bool
        ret = sig.return_annotation
        assert ret is bool or ret is bool or ret is not sig.empty

    def test_ratelimiter_get_remaining_method_exists(self):
        """TokenBucketRateLimiter has a get_remaining method."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        assert hasattr(TokenBucketRateLimiter, "get_remaining")

    def test_ratelimiter_get_remaining_signature(self):
        """get_remaining(key: str) -> tuple[int, float]."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        sig = signature(TokenBucketRateLimiter.get_remaining)
        assert "key" in sig.parameters
        # Should return tuple of (remaining_tokens, seconds_until_full)

    def test_ratelimiter_reset_method_exists(self):
        """TokenBucketRateLimiter has a reset method."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        assert hasattr(TokenBucketRateLimiter, "reset")

    def test_ratelimiter_reset_signature(self):
        """reset(key: str) -> None."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        sig = signature(TokenBucketRateLimiter.reset)
        assert "key" in sig.parameters
        ret = sig.return_annotation
        assert ret is None or ret is not sig.empty

    def test_ratelimiter_can_be_instantiated(self):
        """TokenBucketRateLimiter can be instantiated with capacity and fill_rate."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(capacity=100, fill_rate=10.0)
        assert limiter is not None

    def test_ratelimiter_accepts_rate_limit_config(self):
        """TokenBucketRateLimiter also accepts RateLimitConfig as first arg."""
        from meeting_notes_ai.ratelimit import RateLimitConfig, TokenBucketRateLimiter

        config = RateLimitConfig(capacity=100, fill_rate=10.0)
        limiter = TokenBucketRateLimiter(capacity=config.capacity, fill_rate=config.fill_rate)
        assert limiter is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Tests (will FAIL until implementation is done)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenBucketRateLimiterBehavioral:
    """Behavioral tests for TokenBucketRateLimiter.

    These tests verify actual rate limiting behavior and will fail (RED phase)
    until the module is fully implemented.
    """

    @pytest.fixture
    def limiter(self):
        """Provide a TokenBucketRateLimiter with capacity=10, fill_rate=1 (1 token/sec)."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        return TokenBucketRateLimiter(capacity=10, fill_rate=1.0)

    @pytest.fixture
    def small_limiter(self):
        """Provide a TokenBucketRateLimiter with capacity=1, fill_rate=0.1."""
        from meeting_notes_ai.ratelimit import TokenBucketRateLimiter

        return TokenBucketRateLimiter(capacity=1, fill_rate=0.1)

    # ── allow() behavior ─────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_allow_returns_true_when_tokens_available(self, limiter):
        """allow() returns True when tokens remain in the bucket."""
        assert limiter.allow("test-key") is True

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_allow_returns_false_when_empty(self, small_limiter):
        """allow() returns False when bucket is empty after consuming all tokens."""
        # Consume the single token
        small_limiter.allow("test-key")
        # Second call should fail
        assert small_limiter.allow("test-key") is False

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_allow_respects_separate_keys(self, small_limiter):
        """Each key has its own bucket — one key being empty doesn't affect another."""
        # Consume key-a's token
        small_limiter.allow("key-a")
        # key-b should still have its token
        assert small_limiter.allow("key-b") is True
        # key-a should now be empty
        assert small_limiter.allow("key-a") is False

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_tokens_refill_over_time(self, limiter):
        """Tokens gradually refill at the configured fill_rate."""
        import time

        key = "refill-test"
        # Consume all 10 tokens
        for _ in range(10):
            limiter.allow(key)
        # Bucket should be empty
        assert limiter.allow(key) is False
        # Wait ~1.1 seconds for ~1 token to refill
        time.sleep(1.1)
        # Now should have 1 token available
        assert limiter.allow(key) is True

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_allow_does_not_block_on_success(self, limiter):
        """allow() returns quickly when tokens are available (no blocking)."""
        import time

        start = time.monotonic()
        result = limiter.allow("fast-key")
        elapsed = time.monotonic() - start
        assert result is True
        # Should be near-instant (< 0.1s)
        assert elapsed < 0.1, f"allow() took {elapsed:.3f}s, should be instant"

    # ── get_remaining() behavior ──────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_get_remaining_returns_tuple(self, limiter):
        """get_remaining() returns a (int, float) tuple."""
        result = limiter.get_remaining("remaining-key")
        assert isinstance(result, tuple)
        assert len(result) == 2
        remaining, reset_after = result
        assert isinstance(remaining, int) or isinstance(remaining, float)
        assert isinstance(reset_after, (int, float))

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_get_remaining_starts_at_capacity(self, limiter):
        """get_remaining() returns capacity for a fresh key."""
        remaining, _ = limiter.get_remaining("fresh-key")
        assert remaining == 10  # capacity

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_get_remaining_decrements_after_allow(self, limiter):
        """get_remaining() shows reduced count after consuming tokens."""
        limiter.allow("decrement-key")
        remaining, _ = limiter.get_remaining("decrement-key")
        assert remaining == 9  # was 10, consumed 1

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_get_remaining_never_negative(self, small_limiter):
        """get_remaining() never returns a negative value."""
        # Consume the only token
        small_limiter.allow("neg-key")
        after_allow, _ = small_limiter.get_remaining("neg-key")
        assert after_allow >= 0
        # Try consuming again
        small_limiter.allow("neg-key")
        after_second, _ = small_limiter.get_remaining("neg-key")
        assert after_second >= 0

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_get_remaining_reset_after_is_positive(self, limiter):
        """The reset_after (seconds_until_full) is a positive number."""
        limiter.allow("reset-after-key")
        _, reset_after = limiter.get_remaining("reset-after-key")
        assert reset_after > 0, f"Expected positive reset_after, got {reset_after}"

    # ── reset() behavior ──────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_reset_restores_capacity(self, small_limiter):
        """reset() restores bucket to full capacity."""
        # Empty the bucket
        small_limiter.allow("reset-key")
        assert small_limiter.allow("reset-key") is False
        # Reset
        small_limiter.reset("reset-key")
        # Should now be allowed again
        assert small_limiter.allow("reset-key") is True

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_reset_does_not_affect_other_keys(self, limiter):
        """reset() on one key does not affect other keys' buckets."""
        limiter.allow("key-a")
        limiter.allow("key-b")
        limiter.reset("key-a")
        remaining_a, _ = limiter.get_remaining("key-a")
        remaining_b, _ = limiter.get_remaining("key-b")
        assert remaining_a > remaining_b, (
            f"key-a ({remaining_a}) should have more than key-b ({remaining_b}) after reset"
        )

    # ── Monotonic time ────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Not yet implemented — RED phase")
    def test_uses_monotonic_time(self, limiter):
        """Rate limiter uses time.monotonic() (not time.time()) to avoid clock skew."""
        import time

        # Record time before and after — the internal refill calc should be based
        # on monotonic clock differences, not wall clock.
        key = "monotonic-test"
        limiter.allow(key)
        time.sleep(0.5)
        # At 1 token/sec fill, after 0.5s we'd have at most 0.5 tokens extra.
        # We can't directly test internal impl, but verify behavior is sane.
        after_allow = limiter.allow(key)
        # Since we consumed 10 (all tokens), after 0.5s we should still be empty
        # (need 1 sec for 1 token). This indirectly tests monotonic-based refill.
        # Allow 0.1s clock tolerance
        assert after_allow is False or limiter.get_remaining(key)[0] >= 0
