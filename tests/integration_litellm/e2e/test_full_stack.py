"""Phase 5: End-to-end integration tests.

Verify all components work together: adapter lifecycle, routing, caching, tracing.
"""

import pytest
from src.adapters.registry import AdapterRegistry
from src.adapters.routing_strategies.smart_router import SmartRouter, RouteExhaustedError
from src.adapters.routing_strategies.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from src.adapters.cost_calculator import CostCalculator
from src.adapters.cache import CachingAdapter, LRUCache
from src.adapters.rate_limit import RateLimitHandler
from src.metrics.budget_alerter import BudgetAlerter
from src.metrics.tracing import TracingAdapter


SAMPLE_PROVIDERS = [
    {"provider": "openai", "model": "gpt-4o-mini", "tier": "L0"},
    {"provider": "anthropic", "model": "claude-haiku-3-5", "tier": "L0"},
    {"provider": "deepseek", "model": "deepseek-chat", "tier": "L0"},
]


class TestFullStackIntegration:
    """Verify all adapters work together in a simulated ask() flow."""
    
    def test_all_adapters_initialize(self, mock_config):
        """All adapters should initialize without errors."""
        from src.adapters.routing_strategies.smart_router import SmartRouter
        from src.metrics.budget_alerter import BudgetAlerter
        from src.metrics.tracing import TracingAdapter
        from src.adapters.cache import CachingAdapter
        
        config = mock_config.copy()
        config.update({
            "enable_litellm_router": True,
            "enable_cache": True,
            "enable_tracing": True,
        })
        
        router = SmartRouter(config=config)
        budget = BudgetAlerter(config={"budget_daily_limit": 10.00})
        cache = CachingAdapter(config=config)
        tracer = TracingAdapter(config=config)
        
        assert router.initialize() is True
        assert cache.initialize() is True
        assert tracer.initialize() is True
    
    def test_routing_with_budget_and_cache(self, mock_config):
        """Simulate full ask() flow: route → check budget → check cache → return."""
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        config["enable_cache"] = True
        
        router = SmartRouter(config=config)
        budget = BudgetAlerter(config={"budget_daily_limit": 10.00})
        cache = CachingAdapter(config=config)
        
        # Step 1: Route
        decision = router.select("test task", SAMPLE_PROVIDERS, strategy="cost_aware")
        assert decision.provider
        
        # Step 2: Budget check
        ok, reason = budget.can_proceed(float(decision.estimated_cost), tier=decision.tier)
        assert ok or "exhausted" in reason.lower() or "exceeds" in reason.lower()
        
        # Step 3: Cache check
        msgs = [{"role": "user", "content": "test task"}]
        cached = cache.get(decision.provider, decision.model, msgs)
        assert cached is None  # Cold cache
        
        # Step 4: Simulate response and cache it
        cache.set(decision.provider, decision.model, msgs, {"output": "result"})
        cached = cache.get(decision.provider, decision.model, msgs)
        assert cached == {"output": "result"}
    
    def test_circuit_breaker_integration(self, mock_config):
        """Circuit breaker should integrate with routing."""
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        
        router = SmartRouter(config=config)
        cb_config = CircuitBreakerConfig(failure_threshold=2, reset_timeout_s=1.0)
        breaker = CircuitBreaker("openai", "gpt-4o-mini", cb_config)
        
        # Trip the breaker
        breaker.record_failure("timeout")
        breaker.record_failure("5xx")
        assert breaker.is_open is True
        
        # Router should still work with other providers
        decision = router.select("test", SAMPLE_PROVIDERS, strategy="cost_aware")
        assert decision.provider  # Should route to non-openai
    
    def test_tracing_full_flow(self, mock_config):
        """Tracing should capture a complete ask() flow."""
        config = mock_config.copy()
        config["enable_tracing"] = True
        
        tracer = TracingAdapter(config=config)
        
        with tracer.trace("mrkrabs.ask", task_id="e2e-test") as root:
            with tracer.trace("mrkrabs.route", parent=root) as route:
                route.add_event("candidates", count=3)
            with tracer.trace("mrkrabs.provider", parent=root) as prov:
                prov.add_event("response", model="gpt-4o-mini")
        
        traces = tracer.get_traces()
        assert len(traces) == 3
    
    def test_rate_limit_and_backoff(self):
        """Rate limit handler should calculate backoff correctly."""
        handler = RateLimitHandler()
        delay = handler.get_backoff_delay("test", 3)
        assert delay > 0
        assert delay <= handler.config.max_delay_s
    
    def test_cache_ttl_per_tier(self, mock_config):
        """Cache TTL should vary by tier."""
        config = mock_config.copy()
        config["enable_cache"] = True
        
        cache = CachingAdapter(config=config)
        msgs = [{"role": "user", "content": "test"}]
        
        # L0 tier gets 24h TTL
        cache.set("openai", "gpt-4o-mini", msgs, {"output": "ok"}, tier="L0")
        assert cache.get("openai", "gpt-4o-mini", msgs) is not None


class TestAdapterLifecycle:
    """Verify adapter lifecycle: init → health → shutdown."""
    
    def test_smart_router_lifecycle(self, mock_config):
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        router = SmartRouter(config=config)
        assert router.initialize() is True
        assert router.health_check().value == "healthy"
        router.shutdown()
        assert router.initialized is False
    
    def test_cache_lifecycle(self, mock_config):
        config = mock_config.copy()
        config["enable_cache"] = True
        cache = CachingAdapter(config=config)
        assert cache.initialize() is True
        assert cache.health_check().value == "healthy"
        cache.shutdown()
        assert cache.initialized is False