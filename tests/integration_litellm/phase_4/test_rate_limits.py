"""Phase 4: Rate limit handling tests."""

import pytest
import asyncio
import time
from src.adapters.rate_limit import (
    RateLimitHandler, RateLimitConfig, TokenBucket,
    get_rate_limit_handler,
)


@pytest.fixture
def handler():
    return RateLimitHandler()


class TestRateLimitHandler:
    def test_backoff_increases_with_retries(self, handler):
        d1 = handler.get_backoff_delay("test", 0)
        d2 = handler.get_backoff_delay("test", 3)
        assert d2 > d1
    
    def test_backoff_respects_max(self, handler):
        delay = handler.get_backoff_delay("test", 20)
        assert delay <= handler.config.max_delay_s
    
    def test_backoff_respects_retry_after(self, handler):
        delay = handler.get_backoff_delay("test", 0, retry_after=5.0)
        assert delay >= 3.75  # 5.0 - 25% jitter
        assert delay <= 6.25  # 5.0 + 25% jitter
    
    def test_should_rotate_on_long_retry_after(self, handler):
        assert handler.should_rotate("test", retry_after=15.0) is True
    
    def test_should_not_rotate_on_short_retry_after(self, handler):
        assert handler.should_rotate("test", retry_after=3.0) is False
    
    def test_get_retry_after_from_header(self, handler):
        assert handler.get_retry_after({"retry-after": "30"}) == 30.0
    
    def test_get_retry_after_ratelimit_reset(self, handler):
        assert handler.get_retry_after({"x-ratelimit-reset-requests": "45"}) == 45.0
    
    def test_get_retry_after_none(self, handler):
        assert handler.get_retry_after({}) is None
    
    def test_config_defaults(self, handler):
        config = RateLimitConfig()
        assert config.max_retries == 5
        assert config.base_delay_s == 1.0
        assert config.max_delay_s == 60.0
        assert config.jitter_factor == 0.25
        assert config.requests_per_minute == 500
        assert config.tokens_per_minute == 200000
        assert config.budget_threshold_pct == 15.0
    
    def test_provider_backoff_tracking(self, handler):
        # Test that backoff is tracked per provider
        delay1 = handler.get_backoff_delay("provider1", 0)
        delay2 = handler.get_backoff_delay("provider2", 0)
        
        # Both should be different (different providers)
        assert delay1 != delay2
    
    def test_should_throttle_on_critical_budget(self, handler):
        assert handler.should_throttle("test", 3.0) is True
    
    def test_no_throttle_on_healthy_budget(self, handler):
        assert handler.should_throttle("test", 50.0) is False
    
    def test_singleton_returns_same_instance(self):
        h1 = get_rate_limit_handler()
        h2 = get_rate_limit_handler()
        assert h1 is h2


class TestTokenBucket:
    def test_consume_available(self):
        import asyncio
        async def _test():
            bucket = TokenBucket(rate_per_second=100, capacity=10)
            assert await bucket.consume(1) is True
            assert await bucket.consume(9) is True
            assert await bucket.consume(1) is False
        asyncio.run(_test())
    
    def test_refill(self):
        import asyncio
        async def _test():
            bucket = TokenBucket(rate_per_second=1000, capacity=5)
            await bucket.consume(5)
            await asyncio.sleep(0.01)
            assert await bucket.consume(1) is True
        asyncio.run(_test())
    
    def test_consume_with_locking(self):
        import asyncio
        async def _test():
            bucket = TokenBucket(rate_per_second=100, capacity=10)
            assert await bucket.consume(5) is True
            assert await bucket.consume(6) is False
        asyncio.run(_test())
    
    def test_wait_and_consume(self):
        import asyncio, time
        async def _test():
            bucket = TokenBucket(rate_per_second=10, capacity=5)
            await bucket.consume(5)
            start_time = time.monotonic()
            await bucket.wait_and_consume(1)
            end_time = time.monotonic()
            assert end_time - start_time >= 0.01
        asyncio.run(_test())
    
    def test_multiple_concurrent_consumption(self):
        import asyncio
        async def _test():
            bucket = TokenBucket(rate_per_second=100, capacity=10)
            async def consume_tokens():
                return await bucket.consume(1)
            tasks = [consume_tokens() for _ in range(5)]
            results = await asyncio.gather(*tasks)
            assert sum(results) == 5
        asyncio.run(_test())


class TestBudgetAwareness:
    def test_throttle_on_critical_budget(self, handler):
        assert handler.should_throttle("test", 3.0) is True
    
    def test_no_throttle_on_healthy_budget(self, handler):
        assert handler.should_throttle("test", 50.0) is False
    
    def test_throttle_at_threshold(self, handler):
        # Test at the exact threshold
        assert handler.should_throttle("test", 5.0) is True


class TestSingletonHandler:
    def test_singleton_returns_same_instance(self):
        h1 = get_rate_limit_handler()
        h2 = get_rate_limit_handler()
        assert h1 is h2

    def test_multiple_calls_return_same_instance(self):
        handler1 = get_rate_limit_handler()
        handler2 = get_rate_limit_handler()
        handler3 = get_rate_limit_handler()
        
        assert handler1 is handler2 is handler3