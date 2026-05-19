"""Smart multi-dimensional LLM provider router.

Selects optimal provider+model using configurable routing strategies.
Integrates with CircuitBreaker, CostCalculator, TierManager, and Prometheus.
"""

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..base_adapter import LiteLLMAdapter, HealthStatus
from ..cost_calculator import CostCalculator, CostEstimate
from .circuit_breaker import get_circuit_breaker_registry, CircuitState

log = logging.getLogger(__name__) if __name__ != "__main__" else logging.getLogger("smart_router")


@dataclass
class ProviderCandidate:
    """A candidate provider+model for routing."""
    provider: str
    model: str
    tier: str
    estimated_cost: Decimal = Decimal("0")
    p95_latency_ms: float = 0.0
    capability_score: float = 0.5
    healthy: bool = True
    circuit_state: str = "closed"


@dataclass
class RouteDecision:
    """Result of routing decision."""
    provider: str
    model: str
    tier: str
    estimated_cost: Decimal = Decimal("0")
    estimated_latency_ms: float = 0.0
    confidence: float = 1.0
    strategy: str = "smart"
    candidates_considered: int = 0


class RouteExhaustedError(Exception):
    """No healthy providers available at any tier."""
    pass


class SmartRouter(LiteLLMAdapter):
    """Multi-dimensional intelligent router for LLM provider selection.
    
    Implements 4 routing strategies:
    - cost_aware: Cheapest capable model
    - latency_aware: Fastest model within budget
    - smart: Weighted multi-factor scoring (default)
    - round_robin: Cycle through providers
    """
    
    def __init__(self, config=None, name: str = "smart_router"):
        super().__init__(config or {}, name)
        self._cost_calculator = CostCalculator()
        self._circuit_breaker = get_circuit_breaker_registry()
        self._round_robin_counters: Dict[str, int] = {}
        self._decision_history: List[RouteDecision] = []
        self._max_history = 100
    
    @property
    def enabled(self) -> bool:
        return self.get_config("enable_litellm_router", default=False)
    
    def initialize(self) -> bool:
        self._initialized = True
        return True
    
    def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY
    
    def shutdown(self) -> None:
        self._initialized = False
    
    def select(self, task: str, providers: List[Dict[str, Any]],
               strategy: Optional[str] = None, budget_remaining: float = 10.00,
               tier: str = "L0") -> RouteDecision:
        """Select the best provider+model for a task.
        
        Args:
            task: Task description for capability matching.
            providers: List of available providers with keys: provider, model, tier.
            strategy: Routing strategy override (cost_aware|latency_aware|smart|round_robin).
            budget_remaining: Current budget in USD.
            tier: Current tier level for escalation tracking.
        
        Returns:
            RouteDecision with selected provider/model/cost.
        
        Raises:
            RouteExhaustedError: If no providers can handle the request.
        """
        strategy_name = strategy or self.get_config("router_strategy", default="smart")
        
        # Step 1: Build candidate list
        candidates = self._build_candidates(providers, budget_remaining)
        
        if not candidates:
            raise RouteExhaustedError(f"No healthy providers available at tier {tier}")
        
        # Step 2: Filter by health and budget
        candidates = [c for c in candidates if c.healthy and c.estimated_cost <= Decimal(str(budget_remaining))]
        
        if not candidates:
            raise RouteExhaustedError(f"No providers within budget ({budget_remaining}) at tier {tier}")
        
        # Step 3: Score and rank
        if strategy_name == "cost_aware":
            candidates.sort(key=lambda c: (c.estimated_cost, c.p95_latency_ms))
        elif strategy_name == "latency_aware":
            candidates.sort(key=lambda c: (c.p95_latency_ms, c.estimated_cost))
        elif strategy_name == "round_robin":
            return self._round_robin_select(candidates, strategy_name)
        else:  # smart (default)
            candidates = self._smart_score(candidates)
        
        best = candidates[0]
        
        decision = RouteDecision(
            provider=best.provider,
            model=best.model,
            tier=best.tier,
            estimated_cost=best.estimated_cost,
            estimated_latency_ms=best.p95_latency_ms,
            confidence=self._calculate_confidence(candidates),
            strategy=strategy_name,
            candidates_considered=len(candidates),
        )
        
        # Log and track
        log.debug(
            "[ROUTE] task=%s → %s/%s (cost=$%.6f/1K, p95=%.1fms, score=%.2f, strategy=%s)",
            task[:30] if task else "?", best.provider, best.model,
            float(best.estimated_cost), best.p95_latency_ms, 
            best.capability_score, strategy_name,
        )
        
        self._decision_history.append(decision)
        if len(self._decision_history) > self._max_history:
            self._decision_history.pop(0)
        
        return decision
    
    def _build_candidates(self, providers: List[Dict[str, Any]], budget: float) -> List[ProviderCandidate]:
        """Build candidate list from provider configs, checking circuit breaker and cost."""
        candidates = []
        for p in providers:
            provider_name = p.get("provider", "unknown")
            model_name = p.get("model", "unknown")
            tier_name = p.get("tier", "L0")
            
            # Check circuit breaker
            cb_state = "closed"
            healthy = True
            try:
                if self._circuit_breaker.is_open(provider_name, model_name):
                    cb_state = "open"
                    healthy = False
            except Exception:
                pass  # Circuit breaker check is best-effort
            
            # Estimate cost for a typical request
            try:
                est = self._cost_calculator.estimate_cost(provider_name, model_name,
                                                          input_tokens=500, estimated_output_tokens=500)
                cost = est.expected_cost
            except Exception:
                cost = Decimal("0.001")  # Fallback estimate
            
            candidates.append(ProviderCandidate(
                provider=provider_name,
                model=model_name,
                tier=tier_name,
                estimated_cost=cost,
                p95_latency_ms=1000.0,  # Default 1s; updated by metrics adapter
                capability_score=0.5,
                healthy=healthy,
                circuit_state=cb_state,
            ))
        return candidates
    
    def _smart_score(self, candidates: List[ProviderCandidate]) -> List[ProviderCandidate]:
        """Score candidates using weighted multi-factor scoring."""
        if not candidates:
            return candidates
        
        weights = self.get_config("smart_weights", default={"cost": 0.5, "latency": 0.3, "capability": 0.2})
        
        # Normalize costs and latencies to 0-1
        max_cost = max(float(c.estimated_cost) for c in candidates) or 0.001
        max_latency = max(c.p95_latency_ms for c in candidates) or 1000.0
        
        for c in candidates:
            cost_score = 1.0 - (float(c.estimated_cost) / max_cost) if max_cost > 0 else 1.0
            latency_score = 1.0 - (c.p95_latency_ms / max_latency) if max_latency > 0 else 1.0
            cap_score = c.capability_score
            
            score = (weights.get("cost", 0.5) * cost_score +
                    weights.get("latency", 0.3) * latency_score +
                    weights.get("capability", 0.2) * cap_score)
            c.capability_score = score  # Reuse field for composite score
        
        candidates.sort(key=lambda c: c.capability_score, reverse=True)
        return candidates
    
    def _round_robin_select(self, candidates: List[ProviderCandidate], strategy: str) -> RouteDecision:
        """Select using round-robin cycling."""
        key = "default"
        idx = self._round_robin_counters.get(key, 0) % len(candidates)
        self._round_robin_counters[key] = idx + 1
        
        c = candidates[idx]
        return RouteDecision(
            provider=c.provider, model=c.model, tier=c.tier,
            estimated_cost=c.estimated_cost, estimated_latency_ms=c.p95_latency_ms,
            confidence=1.0, strategy=strategy, candidates_considered=len(candidates),
        )
    
    def _calculate_confidence(self, candidates: List[ProviderCandidate]) -> float:
        """Calculate confidence based on candidate diversity and health."""
        if len(candidates) >= 3:
            return 0.9
        elif len(candidates) == 2:
            return 0.7
        else:
            return 0.5
    
    def get_decision_history(self, limit: int = 100) -> List[Dict]:
        """Return recent routing decisions for analytics."""
        return [
            {"provider": d.provider, "model": d.model, "tier": d.tier,
             "cost": float(d.estimated_cost), "strategy": d.strategy,
             "confidence": d.confidence}
            for d in self._decision_history[-limit:]
        ]
