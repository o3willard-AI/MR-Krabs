"""Rate limit handling with exponential backoff and jitter.

Handles provider rate limits (HTTP 429) with configurable retry strategies,
provider rotation, and client-side token bucket rate limiting.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RateLimitConfig:
    """Configuration for rate limit handling."""
    max_retries: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    jitter_factor: float = 0.25
    requests_per_minute: int = 500
    tokens_per_minute: int = 200000
    budget_threshold_pct: float = 15.0


class TokenBucket:
    """Token bucket rate limiter for client-side throttling."""
    
    def __init__(self, rate_per_second: float, capacity: int):
        self.rate = rate_per_second
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        async with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def wait_and_consume(self, tokens: int = 1) -> None:
        """Wait until tokens are available, then consume."""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
            await asyncio.sleep(0.1)
    
    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now


class RateLimitHandler:
    """Handles rate limit responses with exponential backoff and jitter.
    
    Features:
    - Exponential backoff with jitter
    - Respects Retry-After headers
    - Provider rotation on long delays
    - Budget-aware adjustment
    - Per-provider backoff state
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._provider_backoff: Dict[str, float] = {}
        self._provider_buckets: Dict[str, TokenBucket] = {}
    
    def get_backoff_delay(self, provider: str, retry_count: int, 
                          retry_after: Optional[float] = None) -> float:
        """Calculate backoff delay for a retry.
        
        Args:
            provider: Provider name for per-provider tracking.
            retry_count: Current retry attempt (0-indexed).
            retry_after: Seconds from Retry-After header, if provided.
        
        Returns:
            Delay in seconds before next retry.
        """
        # If Retry-After header provided, use it directly
        if retry_after is not None:
            delay = min(retry_after, self.config.max_delay_s)
        else:
            # Exponential backoff: base * 2^attempt
            delay = self.config.base_delay_s * (2 ** retry_count)
        
        # Apply jitter: ±25%
        jitter = delay * self.config.jitter_factor
        delay = delay + random.uniform(-jitter, jitter)
        delay = max(0, min(delay, self.config.max_delay_s))
        
        # Track per-provider
        self._provider_backoff[provider] = time.monotonic() + delay
        
        return delay
    
    def should_rotate(self, provider: str, retry_after: Optional[float] = None) -> bool:
        """Check if we should rotate to a different provider instead of retrying."""
        if retry_after and retry_after > 10:
            return True
        if provider in self._provider_backoff:
            if time.monotonic() < self._provider_backoff[provider]:
                return True
        return False
    
    def get_token_bucket(self, provider: str) -> TokenBucket:
        """Get or create a token bucket for a provider."""
        if provider not in self._provider_buckets:
            rate = self.config.tokens_per_minute / 60.0
            capacity = self.config.tokens_per_minute
            self._provider_buckets[provider] = TokenBucket(rate, capacity)
        return self._provider_buckets[provider]
    
    def should_throttle(self, provider: str, budget_percent: float) -> bool:
        """Check if we should throttle/block due to budget constraints."""
        if budget_percent <= self.config.budget_threshold_pct:
            return True  # Block all
        return False
    
    def get_retry_after(self, headers: Dict[str, str]) -> Optional[float]:
        """Parse Retry-After from response headers."""
        retry_after = headers.get("retry-after", "")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        
        # Provider-specific headers
        reset = headers.get("x-ratelimit-reset-requests", "")
        if reset:
            try:
                return float(reset)
            except ValueError:
                pass
        
        return None


# Default singleton
_default_handler: Optional[RateLimitHandler] = None

def get_rate_limit_handler() -> RateLimitHandler:
    global _default_handler
    if _default_handler is None:
        _default_handler = RateLimitHandler()
    return _default_handler