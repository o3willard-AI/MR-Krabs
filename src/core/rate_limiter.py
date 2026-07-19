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

    DEFAULT_RATES: dict[str, float] = {
        "openrouter": 10.0,
        "openai": 50.0,
        "anthropic": 50.0,
        "lmstudio": 100.0,
    }

    def __init__(self, rates: dict[str, float] | None = None):
        self._buckets: dict[str, TokenBucket] = {}
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


class ConnectionLimiter:
    """Limits concurrent connections to backend servers.

    Unlike TokenBucket (which limits request rate), this limits the number
    of in-flight HTTP connections. Local llama.cpp servers crash when too
    many concurrent inference requests exhaust VRAM or thread pools.

    Uses a semaphore — callers acquire before connecting and release after.
    """

    # Conservative defaults for local llama.cpp servers.
    # 2 concurrent connections is safe for most 2-GPU setups.
    DEFAULT_LIMITS: dict[str, int] = {
        "localhost": 1,
        "192.168.101.23": 2,   # 2× RTX 3060 12GB = 24GB, Qwen3-Coder-30B
        "192.168.101.21": 1,   # 1× RTX 3060 12GB, Qwen2.5-Coder-7B
        "192.168.101.17": 1,
    }

    def __init__(self, limits: dict[str, int] | None = None):
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()
        self._limits = limits or dict(self.DEFAULT_LIMITS)
        self._active: dict[str, int] = {}  # For monitoring

    def _get_semaphore(self, host: str) -> threading.BoundedSemaphore:
        """Get or create a semaphore for a host."""
        if host not in self._semaphores:
            with self._lock:
                if host not in self._semaphores:
                    limit = self._limits.get(host, 1)
                    self._semaphores[host] = threading.BoundedSemaphore(limit)
                    self._active[host] = 0
        return self._semaphores[host]

    def acquire(self, host: str, timeout: float = 120.0) -> bool:
        """Try to acquire a connection slot. Blocks until available or timeout.

        Returns True if slot acquired, False on timeout.
        """
        sem = self._get_semaphore(host)
        acquired = sem.acquire(timeout=timeout)
        if acquired:
            with self._lock:
                self._active[host] = self._active.get(host, 0) + 1
        return acquired

    def release(self, host: str):
        """Release a connection slot back to the pool."""
        sem = self._semaphores.get(host)
        if sem:
            sem.release()
            with self._lock:
                self._active[host] = max(0, self._active.get(host, 1) - 1)

    def active(self, host: str) -> int:
        """Return the number of currently active connections for a host."""
        return self._active.get(host, 0)

    def set_limit(self, host: str, limit: int):
        """Update the connection limit for a host."""
        with self._lock:
            self._limits[host] = limit
            if host in self._semaphores:
                # Recreate semaphore with new limit — existing waiters may
                # need to re-acquire, but this is rare (only on config change)
                old = self._semaphores[host]
                self._semaphores[host] = threading.BoundedSemaphore(limit)
                # Drain old semaphore so no one is waiting on it
                while old.acquire(blocking=False):
                    self._semaphores[host].acquire(blocking=False)


# ── Global instances ──────────────────────────────────────────────

# Singleton rate limiter shared across the orchestrator
_rate_limiter: RateLimiter | None = None

def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter

# Singleton connection limiter shared across the orchestrator  
_connection_limiter: ConnectionLimiter | None = None

def get_connection_limiter() -> ConnectionLimiter:
    global _connection_limiter
    if _connection_limiter is None:
        _connection_limiter = ConnectionLimiter()
    return _connection_limiter
