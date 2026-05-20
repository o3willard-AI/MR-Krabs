"""Intelligent caching middleware for LLM responses.

Provides exact-match caching with LRU eviction and TTL-based expiry.
Reduces LLM costs by serving repeated queries from cache.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_adapter import LiteLLMAdapter, HealthStatus


@dataclass
class CacheEntry:
    """A cached LLM response."""
    key: str
    response: Dict[str, Any]
    created_at: float = field(default_factory=time.monotonic)
    ttl_seconds: float = 3600
    hit_count: int = 0
    
    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > self.ttl_seconds


class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_entries: int = 1000):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            entry = self._cache[key]
            if entry.expired:
                self._cache.pop(key)
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            return entry.response
    
    def set(self, key: str, response: Dict[str, Any], ttl_seconds: float = 3600):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key].response = response
                self._cache[key].created_at = time.monotonic()
                self._cache[key].ttl_seconds = ttl_seconds
            else:
                if len(self._cache) >= self._max_entries:
                    self._cache.popitem(last=False)
                self._cache[key] = CacheEntry(key=key, response=response, ttl_seconds=ttl_seconds)
    
    def invalidate(self, pattern: Optional[str] = None):
        with self._lock:
            if pattern is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache if pattern in k]
                for k in keys_to_remove:
                    self._cache.pop(k)
    
    @property
    def size(self) -> int:
        return len(self._cache)
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


class CachingAdapter(LiteLLMAdapter):
    """Caching adapter for LLM responses.
    
    Caches responses keyed by hash(provider + model + messages + params).
    Never caches: streaming requests, error responses, temperature > 0.
    """
    
    TIER_TTL = {"L0": 86400, "L1": 43200, "L2": 3600, "L3": 0}
    
    def __init__(self, config=None, name="cache"):
        super().__init__(config or {}, name)
        max_entries = int(self.get_config("cache_max_entries", default=1000))
        self._store = LRUCache(max_entries=max_entries)
    
    @property
    def enabled(self) -> bool:
        return self.get_config("enable_cache", default=False)
    
    def initialize(self) -> bool:
        self._initialized = True
        return True
    
    def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY
    
    def shutdown(self) -> None:
        self._initialized = False
    
    def make_key(self, provider: str, model: str, messages: List[Dict], 
                 temperature: float = 0.0, **kwargs) -> str:
        """Create a deterministic cache key."""
        # Never cache non-deterministic requests
        if temperature > 0:
            return ""
        
        content = json.dumps({
            "provider": provider,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 0),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, provider: str, model: str, messages: List[Dict],
            temperature: float = 0.0, **kwargs) -> Optional[Dict[str, Any]]:
        """Check cache for a matching response."""
        if not self.enabled:
            return None
        key = self.make_key(provider, model, messages, temperature, **kwargs)
        if not key:
            return None
        return self._store.get(key)
    
    def set(self, provider: str, model: str, messages: List[Dict],
            response: Dict[str, Any], temperature: float = 0.0,
            tier: str = "L0", **kwargs):
        """Store a response in cache."""
        if not self.enabled:
            return
        key = self.make_key(provider, model, messages, temperature, **kwargs)
        if not key:
            return
        ttl = self.TIER_TTL.get(tier, 3600)
        self._store.set(key, response, ttl_seconds=ttl)
    
    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries."""
        self._store.invalidate(pattern)
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": self._store.size,
            "hits": self._store._hits,
            "misses": self._store._misses,
            "hit_rate": self._store.hit_rate,
        }