#!/usr/bin/env python3
"""Unit tests for rate_limiter.py."""

import threading
import time
from unittest.mock import patch

import pytest

from src.core.rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket:
    """Tests for TokenBucket class."""

    def test_initial_tokens(self):
        """Test bucket starts with capacity tokens."""
        bucket = TokenBucket(rate=10.0, capacity=20.0)
        assert bucket.tokens == 20.0
        assert bucket.capacity == 20.0
        assert bucket.rate == 10.0

    def test_acquire_single_token(self):
        """Test acquiring a single token."""
        bucket = TokenBucket(rate=10.0, capacity=10.0)
        assert bucket.acquire() is True
        assert bucket.tokens == 9.0

    def test_acquire_multiple_tokens(self):
        """Test acquiring multiple tokens."""
        bucket = TokenBucket(rate=10.0, capacity=10.0)
        assert bucket.acquire(3.0) is True
        assert bucket.tokens == 7.0

    def test_acquire_exceeds_capacity(self):
        """Test acquiring more tokens than available."""
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        assert bucket.acquire(10.0) is False
        assert bucket.tokens == 5.0  # No tokens consumed

    def test_acquire_exhausts_tokens(self):
        """Test exhausting all tokens."""
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        assert bucket.acquire(5.0) is True
        assert bucket.tokens == 0.0
        # Should fail to acquire more
        assert bucket.acquire(1.0) is False

    @patch("src.core.rate_limiter.time.monotonic")
    def test_refill_tokens(self, mock_time):
        """Test token refill over time."""
        current_time = [0.0]
        
        def get_time():
            result = current_time[0]
            current_time[0] += 5.0  # Advance by 5 seconds
            return result
        
        mock_time.side_effect = get_time
        
        bucket = TokenBucket(rate=10.0, capacity=100.0)
        bucket.tokens = 50.0
        bucket.last_refill = 0.0
        
        # Manually call _refill (in real code, acquire calls it)
        bucket._refill()
        
        assert bucket.tokens == 100.0  # Capped at capacity

    @patch("src.core.rate_limiter.time.monotonic")
    def test_refill_partial(self, mock_time):
        """Test partial token refill."""
        current_time = [0.0]
        
        def get_time():
            result = current_time[0]
            current_time[0] += 2.0  # Advance by 2 seconds
            return result
        
        mock_time.side_effect = get_time
        
        bucket = TokenBucket(rate=10.0, capacity=100.0)
        bucket.tokens = 50.0
        bucket.last_refill = 0.0
        
        bucket._refill()
        
        assert bucket.tokens == 70.0

    def test_wait_for_token_success(self):
        """Test waiting for token succeeds."""
        bucket = TokenBucket(rate=100.0, capacity=100.0)
        # Consume all tokens
        bucket.acquire(100.0)
        # Should wait and succeed as tokens refill
        result = bucket.wait_for_token(1.0, timeout=1.0)
        assert result is True

    def test_wait_for_token_timeout(self):
        """Test waiting for token times out."""
        bucket = TokenBucket(rate=0.1, capacity=1.0)  # Very slow rate
        bucket.acquire(1.0)
        # Should timeout
        result = bucket.wait_for_token(1.0, timeout=0.1)
        assert result is False

    def test_thread_safety(self):
        """Test thread safety of token acquisition."""
        bucket = TokenBucket(rate=0.0, capacity=100.0)  # No refill during test
        success_count = [0]
        lock = threading.Lock()

        def try_acquire():
            if bucket.acquire():
                with lock:
                    success_count[0] += 1

        # Start many threads trying to acquire
        threads = [threading.Thread(target=try_acquire) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should succeed exactly capacity times (no refill)
        assert success_count[0] == 100


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_default_rates(self):
        """Test default rate limits are set."""
        limiter = RateLimiter()
        # Should have default providers
        assert "openrouter" in limiter._rates
        assert limiter._rates["openrouter"] == 10.0

    def test_custom_rates(self):
        """Test custom rate limits."""
        custom_rates = {"custom_provider": 5.0}
        limiter = RateLimiter(rates=custom_rates)
        assert limiter._rates["custom_provider"] == 5.0

    def test_get_bucket_creates(self):
        """Test get_bucket creates new bucket if doesn't exist."""
        limiter = RateLimiter()
        bucket = limiter.get_bucket("new_provider")
        assert bucket is not None
        assert "new_provider" in limiter._buckets

    def test_get_bucket_reuses(self):
        """Test get_bucket returns existing bucket."""
        limiter = RateLimiter()
        bucket1 = limiter.get_bucket("provider1")
        bucket2 = limiter.get_bucket("provider1")
        assert bucket1 is bucket2

    def test_acquire_success(self):
        """Test successful acquisition."""
        limiter = RateLimiter()
        result = limiter.acquire("openrouter")
        assert result is True

    def test_acquire_default_rate(self):
        """Test acquisition with default rate."""
        limiter = RateLimiter()
        bucket = limiter.get_bucket("openrouter")
        assert bucket.rate == 10.0

    def test_set_rate(self):
        """Test updating rate limit."""
        limiter = RateLimiter()
        limiter.set_rate("openrouter", 20.0)
        bucket = limiter.get_bucket("openrouter")
        assert bucket.rate == 20.0
        assert bucket.capacity == 40.0  # capacity = rate * 2

    def test_set_rate_existing_bucket(self):
        """Test updating rate for existing bucket."""
        limiter = RateLimiter()
        limiter.get_bucket("provider1")
        limiter.set_rate("provider1", 50.0)
        bucket = limiter.get_bucket("provider1")
        assert bucket.rate == 50.0

    def test_wait_success(self):
        """Test waiting for token succeeds."""
        limiter = RateLimiter()
        # Fill up tokens
        bucket = limiter.get_bucket("test")
        bucket.acquire(100.0)
        # Should wait and succeed with high rate
        limiter.set_rate("test", 1000.0)
        result = limiter.wait("test", timeout=0.5)
        assert result is True

    def test_wait_timeout(self):
        """Test waiting for token times out."""
        limiter = RateLimiter()
        bucket = limiter.get_bucket("test")
        bucket.acquire(1.0)
        # Very low rate should timeout
        limiter.set_rate("test", 0.1)
        result = limiter.wait("test", timeout=0.1)
        assert result is False

    def test_multiple_providers(self):
        """Test multiple independent providers."""
        limiter = RateLimiter()
        
        # Acquire all tokens from provider1
        bucket1 = limiter.get_bucket("provider1")
        bucket1.acquire(20.0)  # capacity = 20
        
        # Provider2 should still have tokens
        bucket2 = limiter.get_bucket("provider2")
        assert bucket2.tokens == 20.0  # capacity = 20
        
        # Both should work independently
        assert limiter.acquire("provider1") is False  # exhausted
        assert limiter.acquire("provider2") is True  # has tokens


class TestRateLimiterConcurrency:
    """Tests for rate limiter concurrent access."""

    def test_thread_safe_rate_update(self):
        """Test rate updates are thread-safe."""
        limiter = RateLimiter()
        
        def update_rate():
            for i in range(100):
                limiter.set_rate("test", float(i))
        
        threads = [threading.Thread(target=update_rate) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should not crash and rate should be set
        bucket = limiter.get_bucket("test")
        assert bucket.rate == 99.0

    def test_concurrent_acquire(self):
        """Test concurrent token acquisition."""
        limiter = RateLimiter()
        limiter.set_rate("test", 100.0)
        
        success_count = [0]
        lock = threading.Lock()

        def try_acquire():
            if limiter.wait("test", timeout=1.0):
                with lock:
                    success_count[0] += 1
        
        threads = [threading.Thread(target=try_acquire) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should succeed for all
        assert success_count[0] == 50
