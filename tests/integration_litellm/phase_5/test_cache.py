"""Phase 5: Caching adapter tests."""

import pytest
import time
from src.adapters.cache import CachingAdapter, LRUCache, CacheEntry


@pytest.fixture
def cache(mock_config):
    config = mock_config.copy()
    config["enable_cache"] = True
    return CachingAdapter(config=config)


class TestLRUCache:
    def test_set_and_get(self):
        c = LRUCache(max_entries=10)
        c.set("key1", {"output": "hello"})
        assert c.get("key1") == {"output": "hello"}
    
    def test_miss_returns_none(self):
        c = LRUCache(max_entries=10)
        assert c.get("nonexistent") is None
    
    def test_expiry(self):
        c = LRUCache(max_entries=10)
        c.set("key1", {"output": "hello"}, ttl_seconds=0.01)
        time.sleep(0.02)
        assert c.get("key1") is None
    
    def test_lru_eviction(self):
        c = LRUCache(max_entries=3)
        c.set("a", {"output": "1"})
        c.set("b", {"output": "2"})
        c.set("c", {"output": "3"})
        c.set("d", {"output": "4"})  # Evicts "a"
        assert c.get("a") is None
        assert c.get("d") == {"output": "4"}
    
    def test_invalidate_all(self):
        c = LRUCache(max_entries=10)
        c.set("a", {"output": "1"})
        c.set("b", {"output": "2"})
        c.invalidate()
        assert c.size == 0
    
    def test_hit_rate(self):
        c = LRUCache(max_entries=10)
        c.set("a", {"output": "1"})
        c.get("a")
        c.get("a")
        c.get("b")  # miss
        assert c.hit_rate == 2/3


class TestCachingAdapter:
    def test_disabled_by_default(self, mock_config):
        c = CachingAdapter(config=mock_config)
        assert c.enabled is False
    
    def test_cache_hit(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        cache.set("openai", "gpt-4o", msgs, {"output": "hi there"})
        result = cache.get("openai", "gpt-4o", msgs)
        assert result == {"output": "hi there"}
    
    def test_cache_miss(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        result = cache.get("openai", "gpt-4o", msgs)
        assert result is None
    
    def test_different_messages_different_keys(self, cache):
        msgs1 = [{"role": "user", "content": "hello"}]
        msgs2 = [{"role": "user", "content": "goodbye"}]
        cache.set("openai", "gpt-4o", msgs1, {"output": "hi"})
        result = cache.get("openai", "gpt-4o", msgs2)
        assert result is None
    
    def test_temperature_gt_zero_not_cached(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        key = cache.make_key("openai", "gpt-4o", msgs, temperature=0.7)
        assert key == ""
    
    def test_get_stats(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        cache.set("openai", "gpt-4o", msgs, {"output": "hi"})
        stats = cache.get_stats()
        assert stats["size"] >= 1
        assert "hit_rate" in stats
    
    def test_invalidate(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        cache.set("openai", "gpt-4o", msgs, {"output": "hi"})
        cache.invalidate()
        result = cache.get("openai", "gpt-4o", msgs)
        assert result is None
    
    def test_tier_ttl(self, cache):
        msgs = [{"role": "user", "content": "test"}]
        cache.set("openai", "gpt-4o", msgs, {"output": "ok"}, tier="L2")
        stats = cache.get_stats()
        assert stats["size"] == 1
    
    def test_disabled_cache_always_misses(self, mock_config):
        c = CachingAdapter(config=mock_config)
        msgs = [{"role": "user", "content": "hello"}]
        c.set("openai", "gpt-4o", msgs, {"output": "hi"})
        result = c.get("openai", "gpt-4o", msgs)
        assert result is None


class TestCacheKeyGeneration:
    def test_same_input_same_key(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        k1 = cache.make_key("openai", "gpt-4o", msgs)
        k2 = cache.make_key("openai", "gpt-4o", msgs)
        assert k1 == k2
    
    def test_different_provider_different_key(self, cache):
        msgs = [{"role": "user", "content": "hello"}]
        k1 = cache.make_key("openai", "gpt-4o", msgs)
        k2 = cache.make_key("anthropic", "gpt-4o", msgs)
        assert k1 != k2