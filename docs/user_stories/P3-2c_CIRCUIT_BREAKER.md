# Story P3-2c: Circuit Breaker & Failover Logic

**Priority:** P0 (Critical — resilience for multi-provider operations)
**Estimate:** 3 days
**Phase:** Phase 2 — Week 5

---

## User Story

As an **operator** running MR-Krabs against multiple providers,
I want automatic circuit breaking and failover when a provider becomes unhealthy
So that transient provider outages don't cascade into task failures or budget waste.

---

## Acceptance Criteria

### AC1: Circuit Breaker Pattern Implementation
- [ ] Implement `CircuitBreaker` in `src/adapters/routing_strategies/circuit_breaker.py`
- [ ] Three states per provider:
  - **CLOSED** (normal): requests flow through. Track failures.
  - **OPEN** (tripped): requests immediately rejected. No API calls made.
  - **HALF_OPEN** (testing): allow 1 probe request. Success → CLOSED, failure → OPEN.
- [ ] State transitions:
  ```
  CLOSED ── failure_threshold reached ──→ OPEN
  OPEN   ── reset_timeout elapsed   ──→ HALF_OPEN
  HALF_OPEN ── probe succeeds        ──→ CLOSED
  HALF_OPEN ── probe fails           ──→ OPEN (reset timeout restarts)
  ```
- [ ] Per-provider+model granularity: `openai/gpt-4o` can be OPEN while `openai/gpt-4o-mini` is CLOSED

### AC2: Circuit Breaker Configuration
- [ ] TOML config:
  ```toml
  [litellm.router.circuit_breaker]
  enabled = true
  failure_threshold = 5              # consecutive failures to trip
  failure_window_s = 60              # sliding window for failure counting
  reset_timeout_s = 30               # time before HALF_OPEN probe
  half_open_max_probes = 1           # max probes before re-opening
  success_threshold = 2              # consecutive successes to close
  ```
- [ ] Per-provider overrides:
  ```toml
  [litellm.router.circuit_breaker.provider_overrides.anthropic]
  failure_threshold = 3              # anthropic is flakier, trip faster
  reset_timeout_s = 60               # give it more recovery time
  ```

### AC3: Failure Classification
- [ ] Only these error types count toward circuit breaker threshold:
  - Connection errors (timeout, DNS failure, connection refused)
  - 5xx server errors from provider
  - 429 rate limit errors (counts as 1, but treated as transient)
- [ ] These errors do NOT count:
  - 4xx client errors (bad request, auth failure — not provider's fault)
  - Budget exhaustion (MR-Krabs internal, not provider issue)
  - Validation errors (MR-Krabs internal)
- [ ] Classification configurable if providers have non-standard error behavior

### AC4: Failover Integration
- [ ] When SmartRouter encounters an OPEN circuit:
  - Skip that provider+model in candidate list
  - Log: `[CIRCUIT BREAKER] openai/gpt-4o skipped (OPEN, 4 consecutive failures, retry in 23s)`
  - Increment `mrkrabs_circuit_breaker_skips_total{provider, model}` counter
- [ ] If all candidates are OPEN:
  - SmartRouter escalates tier → re-evaluates (preserves existing tier escalation)
  - If all providers at all tiers are OPEN: return `AllProvidersUnhealthyError`
- [ ] In HALF_OPEN state, the probe request is a real `ask()` call at lowest cost tier
  - If probe fails: cost is tracked but task is not charged to user's workflow
  - Probe results logged at INFO level

### AC5: Circuit Breaker Observability
- [ ] Prometheus metrics:
  - `mrkrabs_circuit_breaker_state{provider, model}` — Gauge: 0=CLOSED, 1=OPEN, 2=HALF_OPEN
  - `mrkrabs_circuit_breaker_transitions_total{provider, model, from_state, to_state}` — Counter
  - `mrkrabs_circuit_breaker_skips_total{provider, model}` — Counter
  - `mrkrabs_circuit_breaker_probes_total{provider, model, result}` — Counter
- [ ] Grafana panel: circuit breaker status heatmap (providers × models, color by state)
- [ ] MCP analytics tool: `get_circuit_breaker_status()` → dict of all provider states

### AC6: Manual Override
- [ ] CLI command to force state:
  ```bash
  mrkrabs circuit reset openai/gpt-4o     # force CLOSED
  mrkrabs circuit trip anthropic/claude-*  # force OPEN (glob support)
  ```
- [ ] MCP tool `force_circuit_state(provider, model, state)` — requires admin auth
- [ ] Manual overrides expire after configurable TTL (default: 5 min) unless `--permanent` flag

---

## Technical Notes

- Use atomic state transitions (thread-safe) — `asyncio.Lock` per circuit breaker instance
- State persistence: write to JSON file every state change, reload on startup (survives restarts)
- Failure counting: sliding window using `collections.deque` with timestamps
- Reference: Microsoft's Circuit Breaker pattern, Netflix Hystrix, resilience4j
- Not using an external library — self-contained in `src/adapters/` to minimize dependency footprint

---

## Definition of Done

- [ ] `CircuitBreaker` class implemented with all 3 states and transitions
- [ ] Integrated with SmartRouter (filters OPEN circuits from candidates)
- [ ] Per-provider config overrides working
- [ ] Failure classification excludes 4xx client errors
- [ ] Prometheus metrics + Grafana panel functional
- [ ] CLI force-reset/trip commands working
- [ ] Tests: `pytest tests/integration_litellm/phase_2/test_circuit_breaker.py -v`
- [ ] Test scenarios: normal flow, trip on 5 failures, HALF_OPEN probe success, HALF_OPEN probe failure, manual override
