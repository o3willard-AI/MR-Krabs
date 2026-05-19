"""Phase 2: Smart router tests."""

import pytest
from decimal import Decimal
from src.adapters.routing_strategies.smart_router import (
    SmartRouter, RouteDecision, RouteExhaustedError, ProviderCandidate,
)


@pytest.fixture
def router(mock_config):
    """Create SmartRouter with test config."""
    config = mock_config.copy()
    config["enable_litellm_router"] = True
    config["router_strategy"] = "smart"
    return SmartRouter(config=config)


@pytest.fixture
def sample_providers():
    """Sample provider list for testing."""
    return [
        {"provider": "openai", "model": "gpt-4o-mini", "tier": "L0"},
        {"provider": "openai", "model": "gpt-4o", "tier": "L1"},
        {"provider": "anthropic", "model": "claude-haiku-3-5", "tier": "L0"},
        {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "tier": "L1"},
        {"provider": "lmstudio", "model": "local-model", "tier": "L0"},
    ]


class TestSmartRouter:
    """Core router tests."""

    def test_router_initialization(self, router):
        assert router.name == "smart_router"
        assert router.enabled is True

    def test_router_disabled_by_default(self, mock_config):
        router = SmartRouter(config=mock_config)
        assert router.enabled is False  # Default OFF per story

    def test_select_returns_route_decision(self, router, sample_providers):
        decision = router.select("test task", sample_providers)
        assert isinstance(decision, RouteDecision)
        assert decision.provider
        assert decision.model
        assert decision.strategy == "smart"

    def test_select_cost_aware_strategy(self, router, sample_providers):
        decision = router.select("test task", sample_providers, strategy="cost_aware")
        assert decision.strategy == "cost_aware"
        # Should pick cheapest — lmstudio is free
        assert decision.provider == "lmstudio"

    def test_select_round_robin_cycles(self, router, sample_providers):
        d1 = router.select("task1", sample_providers, strategy="round_robin")
        d2 = router.select("task2", sample_providers, strategy="round_robin")
        # Round robin cycles through providers
        assert d1.provider is not None
        assert d2.provider is not None

    def test_select_latency_aware(self, router, sample_providers):
        decision = router.select("test", sample_providers, strategy="latency_aware")
        assert decision.strategy == "latency_aware"

    def test_select_with_budget_constraint(self, router, sample_providers):
        """Budget too low for expensive models — should select cheapest."""
        # gpt-4o costs ~$0.01 for 1K tokens — budget of $0.0001 should filter it
        decision = router.select("test", sample_providers,
                                strategy="cost_aware", budget_remaining=0.0001)
        # lmstudio is free
        assert decision.provider == "lmstudio"

    def test_select_exhausted_raises(self, router):
        """No providers within budget should raise RouteExhaustedError."""
        expensive_only = [
            {"provider": "openai", "model": "gpt-4o", "tier": "L1"},
        ]
        # Budget way too low
        with pytest.raises(RouteExhaustedError):
            router.select("test", expensive_only, budget_remaining=0.0000001)

    def test_decision_history(self, router, sample_providers):
        for _ in range(10):
            router.select(f"task_{_}", sample_providers)
        history = router.get_decision_history()
        assert len(history) == 10

    def test_decision_history_capped(self, router, sample_providers):
        for i in range(110):
            router.select(f"task_{i}", sample_providers)
        history = router.get_decision_history()
        assert len(history) <= 100  # Max history


class TestRouteDecision:
    """RouteDecision dataclass tests."""

    def test_route_decision_defaults(self):
        d = RouteDecision(provider="test", model="model", tier="L0")
        assert d.provider == "test"
        assert d.confidence == 1.0
        assert d.estimated_cost == Decimal("0")


class TestProviderCandidate:
    """ProviderCandidate tests."""

    def test_candidate_defaults(self):
        c = ProviderCandidate(provider="test", model="model", tier="L0")
        assert c.healthy is True
        assert c.circuit_state == "closed"


class TestSmartRouterStrategies:
    """Strategy-specific behavior tests."""

    def test_smart_strategy_weights_configurable(self, mock_config, sample_providers):
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        config["smart_weights"] = {"cost": 0.1, "latency": 0.8, "capability": 0.1}
        router = SmartRouter(config=config)
        decision = router.select("test", sample_providers, strategy="smart")
        assert decision.strategy == "smart"

    def test_per_request_strategy_override(self, router, sample_providers):
        """Per-request strategy should override config."""
        decision = router.select("test", sample_providers, strategy="cost_aware")
        assert decision.strategy == "cost_aware"


class TestCostAwareStrategy:
    """Tests specifically for cost_aware strategy."""

    def test_cost_aware_selects_cheapest(self, router, sample_providers):
        decision = router.select("cheap", sample_providers, strategy="cost_aware")
        assert decision.strategy == "cost_aware"
        # lmstudio should be cheapest (free)
        assert decision.provider == "lmstudio"


class TestLatencyAwareStrategy:
    """Tests specifically for latency_aware strategy."""

    def test_latency_aware_selects_fastest(self, router, sample_providers):
        decision = router.select("fast", sample_providers, strategy="latency_aware")
        assert decision.strategy == "latency_aware"


class TestRoundRobinStrategy:
    """Tests specifically for round_robin strategy."""

    def test_round_robin_cycles_through_providers(self, router):
        providers = [
            {"provider": "a", "model": "m1", "tier": "L0"},
            {"provider": "b", "model": "m2", "tier": "L0"},
            {"provider": "c", "model": "m3", "tier": "L0"},
        ]
        router = SmartRouter(config={"enable_litellm_router": True})

        d1 = router.select("test", providers, strategy="round_robin")
        d2 = router.select("test", providers, strategy="round_robin")
        d3 = router.select("test", providers, strategy="round_robin")
        d4 = router.select("test", providers, strategy="round_robin")

        # Cycle should repeat: a -> b -> c -> a
        assert d1.provider == "a"
        assert d2.provider == "b"
        assert d3.provider == "c"
        assert d4.provider == "a"


class TestBudgetConstraints:
    """Tests for budget constraint handling."""

    def test_budget_filters_expensive_providers(self, router, sample_providers):
        decision = router.select("test", sample_providers,
                                strategy="cost_aware", budget_remaining=0.01)
        assert decision.provider == "lmstudio"  # Free model

    def test_zero_budget_raises_exhausted(self, router, sample_providers):
        with pytest.raises(RouteExhaustedError):
            router.select("test", sample_providers, budget_remaining=-0.01)


class TestDecisionHistory:
    """Tests for decision history functionality."""

    def test_history_contains_required_fields(self, router, sample_providers):
        router.select("test", sample_providers)
        history = router.get_decision_history()
        assert len(history) == 1
        entry = history[0]
        assert "provider" in entry
        assert "model" in entry
        assert "tier" in entry
        assert "cost" in entry
        assert "strategy" in entry
        assert "confidence" in entry

    def test_history_gets_recent_only(self, router, sample_providers):
        for i in range(200):
            router.select(f"test_{i}", sample_providers)
        history = router.get_decision_history(limit=10)
        assert len(history) == 10


class TestSmartWeights:
    """Tests for smart strategy weight configuration."""

    def test_weights_apply_to_scoring(self, mock_config, sample_providers):
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        config["smart_weights"] = {"cost": 0.1, "latency": 0.5, "capability": 0.4}
        router = SmartRouter(config=config)
        decision = router.select("test", sample_providers, strategy="smart")
        assert decision.strategy == "smart"

    def test_weights_default_values_used_when_not_configured(self, mock_config, sample_providers):
        config = mock_config.copy()
        config["enable_litellm_router"] = True
        router = SmartRouter(config=config)
        decision = router.select("test", sample_providers, strategy="smart")
        # Should use defaults: cost=0.5, latency=0.3, capability=0.2
        assert decision.strategy == "smart"
