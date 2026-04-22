#!/usr/bin/env python3
"""Rate limiter for provider API calls.

Uses a token bucket algorithm to enforce configurable requests-per-second
limits per provider, preventing the orchestrator from becoming a DDoS tool
against providers under high concurrency.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class TokenBucket:
    """Token bucket rate limiter for a single provider."""

    rate: float  # tokens per second
    capacity: float  # max burst size
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens. Returns True if successful, False if rate limited."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_for_token(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """Block until tokens are available or timeout is reached."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire(tokens):
                return True
            time.sleep(0.01)
        return False

    def _refill(self):
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now


class RateLimiter:
    """Manages rate limits for multiple providers.

    Each provider gets its own token bucket. Default limits are conservative
    and should be tuned based on provider documentation.
    """

    DEFAULT_RATES: Dict[str, float] = {
        "openrouter": 10.0,
        "openai": 50.0,
        "anthropic": 50.0,
        "lmstudio": 100.0,
    }

    def __init__(self, rates: Optional[Dict[str, float]] = None):
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._rates = rates or dict(self.DEFAULT_RATES)

    def get_bucket(self, provider: str) -> TokenBucket:
        """Get or create a token bucket for a provider."""
        if provider not in self._buckets:
            with self._lock:
                if provider not in self._buckets:
                    rate = self._rates.get(provider, 10.0)
                    self._buckets[provider] = TokenBucket(rate=rate, capacity=rate * 2)
        return self._buckets[provider]

    def set_rate(self, provider: str, rate: float) -> None:
        """Update the rate limit for a provider."""
        with self._lock:
            self._rates[provider] = rate
            if provider in self._buckets:
                self._buckets[provider].rate = rate
                self._buckets[provider].capacity = rate * 2

    def acquire(self, provider: str) -> bool:
        """Try to acquire a request slot. Returns False if rate limited."""
        bucket = self.get_bucket(provider)
        return bucket.acquire()

    def wait(self, provider: str, timeout: float = 30.0) -> bool:
        """Wait for a request slot. Returns False on timeout."""
        bucket = self.get_bucket(provider)
        return bucket.wait_for_token(timeout=timeout)
