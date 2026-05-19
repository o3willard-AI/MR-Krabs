"""Phase 2: Routing strategy tests."""

import pytest
from decimal import Decimal
from src.adapters.routing_strategies.base import (
    RoutingStrategy, CostAwareStrategy, LatencyAwareStrategy,
    SmartWeightedStrategy, RoundRobinStrategy, TaskContext,
    StrategyConstraints, get_strategy, apply_constraints,
)
from src.adapters.routing_strategies.smart_router import ProviderCandidate


@pytest.fixture
def candidates():
    """Sample candidates for strategy testing."""
    return [
        ProviderCandidate("openai", "gpt-4o-mini", "L0", Decimal("0.001"), 800.0, 0.5),
        ProviderCandidate("openai", "gpt-4o", "L1", Decimal("0.010"), 1200.0, 0.7),
        ProviderCandidate("anthropic", "claude-haiku", "L0", Decimal("0.002"), 600.0, 0.5),
        ProviderCandidate("lmstudio", "local-model", "L0", Decimal("0"), 100.0, 0.3),
    ]


class TestCostAwareStrategy:
    def test_selects_cheapest(self, candidates):
        result = CostAwareStrategy().score(candidates.copy())
        assert result[0].provider == "lmstudio"  # Free
    
    def test_tie_breaks_by_latency(self):
        a = ProviderCandidate("a", "m1", "L0", Decimal("0.001"), 500.0, 0.5)
        b = ProviderCandidate("b", "m2", "L0", Decimal("0.001"), 300.0, 0.5)
        result = CostAwareStrategy().score([a, b])
        assert result[0].provider == "b"  # Same cost, lower latency
    
    def test_is_deterministic(self):
        assert CostAwareStrategy().is_deterministic is True


class TestLatencyAwareStrategy:
    def test_selects_fastest(self, candidates):
        result = LatencyAwareStrategy().score(candidates.copy())
        assert result[0].provider == "lmstudio"  # 100ms
    
    def test_tie_breaks_by_cost(self):
        a = ProviderCandidate("a", "m1", "L0", Decimal("0.005"), 300.0, 0.5)
        b = ProviderCandidate("b", "m2", "L0", Decimal("0.001"), 300.0, 0.5)
        result = LatencyAwareStrategy().score([a, b])
        assert result[0].provider == "b"  # Same latency, lower cost
    
    def test_is_deterministic(self):
        assert LatencyAwareStrategy().is_deterministic is True


class TestSmartWeightedStrategy:
    def test_default_weights(self, candidates):
        result = SmartWeightedStrategy().score(candidates.copy())
        assert len(result) == 4
        # Best should have high score
        assert result[0].capability_score > 0
    
    def test_custom_weights(self, candidates):
        strategy = SmartWeightedStrategy(weights={"cost": 0.1, "latency": 0.8, "capability": 0.1})
        result = strategy.score(candidates.copy())
        assert len(result) == 4
    
    def test_strategy_name(self):
        assert SmartWeightedStrategy().name == "smart"
    
    def test_empty_candidates_returns_empty(self):
        strategy = SmartWeightedStrategy()
        result = strategy.score([])
        assert result == []
    
    def test_is_deterministic(self):
        assert SmartWeightedStrategy().is_deterministic is True


class TestRoundRobinStrategy:
    def test_cycles_through_providers(self):
        strategy = RoundRobinStrategy()
        providers = [
            ProviderCandidate("a", "m1", "L0", Decimal("0"), 100, 0.5),
            ProviderCandidate("b", "m2", "L0", Decimal("0"), 100, 0.5),
            ProviderCandidate("c", "m3", "L0", Decimal("0"), 100, 0.5),
        ]
        r1 = strategy.score(providers.copy())
        r2 = strategy.score(providers.copy())
        r3 = strategy.score(providers.copy())
        r4 = strategy.score(providers.copy())
        assert r1[0].provider == "a"
        assert r2[0].provider == "b"
        assert r3[0].provider == "c"
        assert r4[0].provider == "a"
    
    def test_not_deterministic(self):
        assert RoundRobinStrategy().is_deterministic is False
    
    def test_empty_candidates_returns_empty(self):
        strategy = RoundRobinStrategy()
        result = strategy.score([])
        assert result == []


class TestGetStrategy:
    def test_get_cost_aware(self):
        s = get_strategy("cost_aware")
        assert s.name == "cost_aware"
        assert isinstance(s, CostAwareStrategy)
    
    def test_get_latency_aware(self):
        s = get_strategy("latency_aware")
        assert s.name == "latency_aware"
        assert isinstance(s, LatencyAwareStrategy)
    
    def test_get_smart_with_weights(self):
        config = {"smart_weights": {"cost": 0.1, "latency": 0.5, "capability": 0.4}}
        s = get_strategy("smart", config=config)
        assert isinstance(s, SmartWeightedStrategy)
    
    def test_get_round_robin(self):
        s = get_strategy("round_robin")
        assert s.name == "round_robin"
        assert isinstance(s, RoundRobinStrategy)
    
    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown routing strategy"):
            get_strategy("nonexistent")


class TestStrategyConstraints:
    def test_max_latency_filters(self, candidates):
        constraints = StrategyConstraints(max_latency_ms=500)
        result = apply_constraints(candidates.copy(), constraints)
        assert all(c.p95_latency_ms <= 500 for c in result)
    
    def test_max_cost_filters(self, candidates):
        constraints = StrategyConstraints(max_cost_per_request=0.002)
        result = apply_constraints(candidates.copy(), constraints)
        assert all(float(c.estimated_cost) <= 0.002 for c in result)
    
    def test_excluded_providers(self, candidates):
        constraints = StrategyConstraints(excluded_providers=["openai"])
        result = apply_constraints(candidates.copy(), constraints)
        assert all(c.provider != "openai" for c in result)
    
    def test_preferred_providers_boosted(self, candidates):
        constraints = StrategyConstraints(preferred_providers=["anthropic"])
        result = apply_constraints(candidates.copy(), constraints)
        # Anthropic candidate should have boosted score
        for c in result:
            if c.provider == "anthropic":
                assert c.capability_score > 0.5  # boosted from 0.5
    
    def test_multiple_excluded_providers(self, candidates):
        constraints = StrategyConstraints(excluded_providers=["openai", "anthropic"])
        result = apply_constraints(candidates.copy(), constraints)
        assert all(c.provider == "lmstudio" for c in result)
    
    def test_constraints_with_none_values_does_not_filter(self, candidates):
        constraints = StrategyConstraints(
            max_latency_ms=None,
            max_cost_per_request=None,
            excluded_providers=[]
        )
        result = apply_constraints(candidates.copy(), constraints)
        assert len(result) == 4
    
    def test_preferred_and_excluded_combined(self, candidates):
        constraints = StrategyConstraints(
            preferred_providers=["anthropic"],
            excluded_providers=["openai"]
        )
        result = apply_constraints(candidates.copy(), constraints)
        # Should only have anthropic and lmstudio with boosted anthropic score
        assert all(c.provider in ["anthropic", "lmstudio"] for c in result)


class TestTaskContext:
    def test_defaults(self):
        ctx = TaskContext()
        assert ctx.budget_remaining == 10.00
        assert ctx.estimated_input_tokens == 500
    
    def test_custom(self):
        ctx = TaskContext(budget_remaining=5.00, preferred_strategy="cost_aware")
        assert ctx.preferred_strategy == "cost_aware"


class TestStrategyProperties:
    def test_most_strategies_are_deterministic(self):
        assert CostAwareStrategy().is_deterministic is True
        assert LatencyAwareStrategy().is_deterministic is True
        assert SmartWeightedStrategy().is_deterministic is True
    
    def test_round_robin_is_not_deterministic(self):
        assert RoundRobinStrategy().is_deterministic is False


class TestApplyConstraintsEdgeCases:
    def test_empty_candidates_with_constraints(self):
        constraints = StrategyConstraints(max_latency_ms=500)
        result = apply_constraints([], constraints)
        assert result == []
    
    def test_all_filtered_result_empty(self, candidates):
        # Filter out everything with very strict latency (50ms excludes all)
        constraints = StrategyConstraints(max_latency_ms=50.0)
        result = apply_constraints(candidates.copy(), constraints)
        assert len(result) == 0  # All candidates have latency > 50ms


class TestProviderCandidateFields:
    def test_candidate_has_all_required_fields(self):
        c = ProviderCandidate("test", "model1", "L0", Decimal("0.001"), 500.0, 0.6)
        assert hasattr(c, 'provider')
        assert hasattr(c, 'model')
        assert hasattr(c, 'tier')
        assert hasattr(c, 'estimated_cost')
        assert hasattr(c, 'p95_latency_ms')
        assert hasattr(c, 'capability_score')


class TestStrategyScoreReturnsList:
    def test_cost_aware_returns_list(self):
        result = CostAwareStrategy().score([ProviderCandidate("a", "m1", "L0", Decimal("0"), 100, 0.5)])
        assert isinstance(result, list)
    
    def test_latency_aware_returns_list(self):
        result = LatencyAwareStrategy().score([])
        assert isinstance(result, list)
    
    def test_smart_returns_list(self):
        result = SmartWeightedStrategy().score([])
        assert isinstance(result, list)
    
    def test_round_robin_returns_list(self):
        result = RoundRobinStrategy().score([])
        assert isinstance(result, list)
