# Story P3-2a: Smart Router & Load Balancer

**Priority:** P0 (Critical — core value proposition of the integration)
**Estimate:** 5 days
**Phase:** Phase 2 — Weeks 4–5

---

## User Story

As a **developer** using MR-Krabs,
I want intelligent multi-dimensional routing that selects the optimal provider+model for each request
So that I get the best balance of cost, latency, and capability without manual provider selection.

---

## Acceptance Criteria

### AC1: Forked Load Balancer Logic
- [ ] Fork `litellm/proxy/routers/load_balancer.py` into `src/adapters/routing_strategies/smart_router.py`
- [ ] Implement as `SmartRouter(LiteLLMAdapter)`
- [ ] Core architecture:
  ```
  ask(task) → SmartRouter.select(task, context)
       ├── CostCalculator.estimate_cost(model)        (from P3-1b)
       ├── ProviderHealthRegistry.get_status(provider) (from P3-2c)
       ├── LatencyTracker.get_p95(provider, model)     (from P3-1a metrics)
       └── TierManager.get_capable_tiers(task)         (existing MR-Krabs core)
  ```
- [ ] Router returns `RouteDecision` with: `provider`, `model`, `estimated_cost`, `estimated_latency`, `confidence`

### AC2: Routing Strategies
- [ ] Implement 4 routing strategies, selectable via config:
  - **`cost_aware`**: Always pick the cheapest capable model. Tie-break by latency.
  - **`latency_aware`**: Pick the fastest model within budget. Tie-break by cost.
  - **`smart`** (default): Weighted multi-factor scoring:
    ```
    score = (0.5 × cost_score) + (0.3 × latency_score) + (0.2 × capability_score)
    ```
    Weights configurable in TOML.
  - **`round_robin`**: Cycle through available providers. Used for load distribution testing.
- [ ] Strategy set per-request via `ask(task, strategy="cost_aware")` or globally via `[litellm.router].strategy`
- [ ] Per-request override takes precedence over global config

### AC3: Provider Selection Logic
- [ ] Filter: exclude providers where `health_status != HEALTHY`
- [ ] Filter: exclude models where `estimated_cost > remaining_budget`
- [ ] Filter: exclude tiers below task capability requirements
- [ ] Score remaining candidates by the active routing strategy
- [ ] Return top-scored candidate
- [ ] If zero candidates after filtering: escalate tier (existing MR-Krabs behavior) and re-evaluate
- [ ] If zero candidates across all tiers: return `RouteExhaustedError`

### AC4: Configuration
- [ ] TOML config section:
  ```toml
  [litellm.router]
  strategy = "smart"                    # "smart" | "cost_aware" | "latency_aware" | "round_robin"
  smart_weights = { cost = 0.5, latency = 0.3, capability = 0.2 }
  max_providers_per_request = 5
  sticky_sessions = false               # route same task_id to same provider
  ```
- [ ] Hot-reload: config changes take effect on next `ask()` call without restart

### AC5: Observability
- [ ] Every route decision logged at DEBUG:
  ```
  [ROUTE] task=abc123 → gpt-4o-mini (cost=$0.00015/1K, p95=0.8s, score=0.87, strategy=smart)
  ```
- [ ] Prometheus metrics:
  - `mrkrabs_route_decisions_total{strategy, provider, model}` — Counter
  - `mrkrabs_route_decision_duration_seconds` — Histogram (how long selection takes)
  - `mrkrabs_route_candidates_available` — Gauge (how many healthy options exist)
- [ ] Route decision history queryable via MCP analytics tool: last 100 decisions

### AC6: Integration with Existing Tier Escalation
- [ ] SmartRouter wraps (does not replace) TierManager
- [ ] Flow: `SmartRouter.select()` → if no candidates → `TierManager.escalate()` → `SmartRouter.select()` again
- [ ] Preserve existing `tier_used` tracking in `ask()` response
- [ ] Track which tier+provider was selected for each attempt

---

## Technical Notes

- LiteLLM's load balancer is designed for the proxy gateway pattern — adapt to MR-Krabs' library-call pattern
- Scoring normalization: all scores normalized 0.0–1.0 before weighting
- Latency data: use rolling window of last 100 requests per provider (from Prometheus metrics)
- Capability scoring: model capability estimated from provider metadata (context window, known benchmarks)
- Backward compatibility: if `enable_litellm_router = false`, use existing TierManager directly (same as today)

---

## Definition of Done

- [ ] `SmartRouter` adapter implemented in `src/adapters/routing_strategies/smart_router.py`
- [ ] All 4 strategies functional and tested
- [ ] Integrates with existing TierManager without breaking changes
- [ ] Config hot-reload working
- [ ] Route decision logging and Prometheus metrics operational
- [ ] Tests: `pytest tests/integration_litellm/phase_2/test_smart_router.py -v --cov-fail-under=90`
- [ ] Verify: <5% performance degradation in `ask()` latency (per strategy doc budget)
