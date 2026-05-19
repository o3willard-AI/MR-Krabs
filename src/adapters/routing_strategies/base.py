"""Routing strategy abstract base class and built-in implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TaskContext:
    """Context for a routing decision."""
    task_summary: str = ""
    estimated_input_tokens: int = 500
    estimated_output_tokens: int = 500
    budget_remaining: float = 10.00
    preferred_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class StrategyConstraints:
    """Optional constraints applied before scoring."""
    max_latency_ms: Optional[float] = None
    max_cost_per_request: Optional[float] = None
    preferred_providers: List[str] = field(default_factory=list)
    excluded_providers: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)


class RoutingStrategy(ABC):
    """Abstract base for routing strategies.
    
    Custom strategies: subclass and implement score(), then place in
    src/adapters/routing_strategies/plugins/ for auto-discovery.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...
    
    @abstractmethod
    def score(self, candidates: List, context: TaskContext) -> List:
        """Score and rank provider candidates. Returns sorted list (best first).
        
        Args:
            candidates: List of ProviderCandidate objects.
            context: TaskContext with budget, token estimates, etc.
        
        Returns:
            Sorted list of ProviderCandidate, best first.
        """
        ...
    
    @property
    def is_deterministic(self) -> bool:
        """Whether this strategy always produces the same result for same inputs."""
        return True


class CostAwareStrategy(RoutingStrategy):
    """Select the cheapest capable model. Tie-break by latency."""
    
    @property
    def name(self) -> str:
        return "cost_aware"
    
    def score(self, candidates: List, context: TaskContext = None) -> List:
        candidates.sort(key=lambda c: (c.estimated_cost, c.p95_latency_ms))
        return candidates


class LatencyAwareStrategy(RoutingStrategy):
    """Select the fastest model within budget. Tie-break by cost."""
    
    @property
    def name(self) -> str:
        return "latency_aware"
    
    def score(self, candidates: List, context: TaskContext = None) -> List:
        candidates.sort(key=lambda c: (c.p95_latency_ms, c.estimated_cost))
        return candidates


class SmartWeightedStrategy(RoutingStrategy):
    """Weighted multi-factor scoring (cost + latency + capability)."""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self._weights = weights or {"cost": 0.5, "latency": 0.3, "capability": 0.2}
    
    @property
    def name(self) -> str:
        return "smart"
    
    def score(self, candidates: List, context: TaskContext = None) -> List:
        if not candidates:
            return candidates
        
        max_cost = max(float(c.estimated_cost) for c in candidates) or Decimal("0.001")
        max_latency = max(c.p95_latency_ms for c in candidates) or 1000.0
        
        for c in candidates:
            cost_score = 1.0 - (float(c.estimated_cost) / float(max_cost)) if float(max_cost) > 0 else 1.0
            latency_score = 1.0 - (c.p95_latency_ms / max_latency) if max_latency > 0 else 1.0
            cap_score = c.capability_score
            
            # Store composite score in capability_score field (reused)
            c.capability_score = (
                self._weights.get("cost", 0.5) * cost_score +
                self._weights.get("latency", 0.3) * latency_score +
                self._weights.get("capability", 0.2) * cap_score
            )
        
        candidates.sort(key=lambda c: c.capability_score, reverse=True)
        return candidates


class RoundRobinStrategy(RoutingStrategy):
    """Cycle through available providers in order."""
    
    def __init__(self):
        self._counter: int = 0
    
    @property
    def name(self) -> str:
        return "round_robin"
    
    @property
    def is_deterministic(self) -> bool:
        return False  # Stateful — advances counter each call
    
    def score(self, candidates: List, context: TaskContext = None) -> List:
        if not candidates:
            return candidates
        idx = self._counter % len(candidates)
        self._counter += 1
        # Return list with selected candidate first
        result = candidates.copy()
        result.insert(0, result.pop(idx))
        return result


# Registry of built-in strategies
_BUILTIN_STRATEGIES: Dict[str, RoutingStrategy] = {}


def get_strategy(name: str, config: Optional[Dict] = None) -> RoutingStrategy:
    """Get a strategy by name. Searches built-ins and plugins directory."""
    global _BUILTIN_STRATEGIES
    
    # Check built-ins
    if name in _BUILTIN_STRATEGIES:
        return _BUILTIN_STRATEGIES[name]
    
    # Map names to classes
    strategy_map = {
        "cost_aware": CostAwareStrategy,
        "latency_aware": LatencyAwareStrategy,
        "smart": SmartWeightedStrategy,
        "round_robin": RoundRobinStrategy,
    }
    
    if name in strategy_map:
        if name == "smart" and config:
            weights = config.get("smart_weights", {"cost": 0.5, "latency": 0.3, "capability": 0.2})
            strategy = SmartWeightedStrategy(weights=weights)
        else:
            strategy = strategy_map[name]()
        _BUILTIN_STRATEGIES[name] = strategy
        return strategy
    
    # Try plugins directory
    try:
        import importlib, os, pkgutil
        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
        if os.path.isdir(plugins_dir):
            for _, module_name, _ in pkgutil.iter_modules([plugins_dir]):
                if module_name.startswith("_"):
                    continue
                module = importlib.import_module(f".plugins.{module_name}", package=__package__)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, RoutingStrategy) and 
                        attr not in strategy_map.values()):
                        instance = attr()
                        if instance.name == name:
                            return instance
    except Exception:
        pass
    
    raise ValueError(f"Unknown routing strategy: {name}")


def apply_constraints(candidates: List, constraints: StrategyConstraints) -> List:
    """Filter candidates by strategy constraints BEFORE scoring."""
    result = []
    for c in candidates:
        if constraints.max_latency_ms and c.p95_latency_ms > constraints.max_latency_ms:
            continue
        if constraints.max_cost_per_request and float(c.estimated_cost) > constraints.max_cost_per_request:
            continue
        if constraints.excluded_providers and c.provider in constraints.excluded_providers:
            continue
        result.append(c)
    
    # Boost preferred providers
    if constraints.preferred_providers:
        for c in result:
            if c.provider in constraints.preferred_providers:
                c.capability_score = min(1.0, c.capability_score + 0.1)
    
    return result
