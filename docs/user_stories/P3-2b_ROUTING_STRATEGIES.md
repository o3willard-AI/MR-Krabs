# Story P3-2b: Configurable Routing Strategy System

**Priority:** P1 (High — enables users to tune routing to their workload)
**Estimate:** 3 days
**Phase:** Phase 2 — Week 5

---

## User Story

As an **operator** running MR-Krabs with diverse workloads,
I want to configure routing strategies per-task-type via TOML and define custom strategy plugins
So that my research workloads prioritize capability while my batch workloads minimize cost.

---

## Acceptance Criteria

### AC1: Strategy Plugin Architecture
- [ ] Define `RoutingStrategy` abstract base class in `src/adapters/routing_strategies/base.py`:
  ```python
  class RoutingStrategy(ABC):
      @abstractmethod
      def score(self, candidates: list[ProviderInfo], context: TaskContext) -> list[RouteScore]:
          """Score and rank provider candidates. Returns sorted list (best first)."""
      
      @property
      @abstractmethod  
      def name(self) -> str: ...
      
      @property
      def is_deterministic(self) -> bool: ...  # for round_robin
  ```
- [ ] Built-in strategies implement this interface: `CostAware`, `LatencyAware`, `SmartWeighted`, `RoundRobin`
- [ ] Custom strategies: any class implementing `RoutingStrategy` and registered in `src/adapters/routing_strategies/plugins/` is auto-discovered

### AC2: Per-Task-Type Routing Profiles
- [ ] TOML config supports named routing profiles:
  ```toml
  [litellm.router.profiles.default]
  strategy = "smart"
  smart_weights = { cost = 0.5, latency = 0.3, capability = 0.2 }
  
  [litellm.router.profiles.batch_processing]
  strategy = "cost_aware"
  max_latency_ms = 5000

  [litellm.router.profiles.research]
  strategy = "smart"
  smart_weights = { cost = 0.1, latency = 0.1, capability = 0.8 }
  max_cost_per_request = 1.00
  ```
- [ ] Profile selected via `ask(task, profile="batch_processing")` or via task metadata
- [ ] Falls back to `default` profile if named profile not found

### AC3: Strategy-Specific Constraints
- [ ] Each strategy supports optional constraints:
  - `max_latency_ms`: reject candidates above this P95 latency
  - `max_cost_per_request`: reject candidates above this estimated cost
  - `preferred_providers`: boost score for these providers
  - `excluded_providers`: remove these from consideration
  - `required_capabilities`: only consider models meeting minimum context/features
- [ ] Constraints enforced BEFORE scoring for efficiency

### AC4: Strategy Weight Tuning
- [ ] Smart strategy weights validated at config load: must sum to 1.0
- [ ] Rejection of invalid weights with clear error message:
  ```
  [CONFIG ERROR] smart_weights sum to 1.3, expected 1.0
  ```
- [ ] Dynamic weight adjustment: if latency spikes, temporarily boost cost weight by 20% (opt-in via `auto_tune_weights = true`)

### AC5: Strategy Observability
- [ ] Each route decision logs which profile was active
- [ ] `mrkrabs_route_decisions_total` includes `profile` label
- [ ] MCP analytics tool: `get_route_stats(profile="batch_processing")` returns:
  - Average cost per request, P50/P95 latency, provider distribution, success rate
- [ ] Strategy comparison tool: `compare_strategies("cost_aware", "smart", tasks=sample_tasks)` — runs both strategies on same inputs, reports differences

---

## Technical Notes

- Plugin discovery: scan `src/adapters/routing_strategies/plugins/` for classes inheriting `RoutingStrategy`
- Strategy instances are stateless — `score()` is pure function of candidates + context
- Except `RoundRobin` which maintains a per-provider counter (thread-safe)
- Config parsing uses existing MR-Krabs TOML parser — no new dependency
- Strategy plugins loaded at adapter `initialize()` time, not at import time (avoids circular imports)

---

## Definition of Done

- [ ] `RoutingStrategy` base class + 4 built-in implementations
- [ ] Per-profile routing config functional
- [ ] Strategy constraints enforced correctly
- [ ] Plugin auto-discovery working (test with a custom strategy in plugins/)
- [ ] Strategy comparison tool functional
- [ ] Tests: `pytest tests/integration_litellm/phase_2/test_strategies.py -v`
- [ ] Documentation: each strategy documented with recommended use cases
