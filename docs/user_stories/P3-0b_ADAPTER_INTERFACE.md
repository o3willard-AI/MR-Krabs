# Story P3-0b: Adapter Interface Specification

**Priority:** P0 (Critical — foundation for all forked components)
**Estimate:** 4 days
**Phase:** Phase 0 — Week 1

---

## User Story

As a **developer** integrating LiteLLM components,
I want a clean, versioned adapter interface specification
So that every forked component plugs into MR-Krabs consistently, without coupling to LiteLLM internals.

---

## Acceptance Criteria

### AC1: Interface Specification Document
- [ ] Produce `docs/integration/adapter_interface_spec.md` covering:
  - **Base Adapter abstract class** — methods every forked component must implement
  - **Configuration contract** — how adapters consume MR-Krabs config (TOML) and expose their own
  - **Error boundary** — what exceptions adapters may raise, how core handles them
  - **Lifecycle hooks** — `init()`, `health_check()`, `shutdown()` signatures
  - **Metrics contract** — how adapters emit metrics for Prometheus collection
  - **Feature-flag interface** — how adapters respect opt-in/opt-out `[features]` toggles

### AC2: Base Adapter Implementation
- [ ] Implement `src/adapters/base_adapter.py` with:
  - Abstract class `LiteLLMAdapter(ABC)`
  - `__init__(self, config: MrKrabsConfig)` — receives typed config, not raw dict
  - `@abstractmethod initialize(self) -> bool` — setup, return success
  - `@abstractmethod health_check(self) -> HealthStatus` — returns enum: HEALTHY/DEGRADED/DOWN
  - `@abstractmethod shutdown(self) -> None` — cleanup
  - `@property enabled(self) -> bool` — reads feature flag from config
  - `@property name(self) -> str` — human-readable adapter identifier
- [ ] All concrete adapter classes across all phases inherit from this base

### AC3: Configuration Priority Enforcement
- [ ] Adapters must follow priority: MR-Krabs `[litellm.*]` config section → LiteLLM default → env var fallback
- [ ] Implement `config.get_with_fallback(key, litellm_default, env_var=None)` helper in base adapter
- [ ] Unit tests proving priority order for each level
- [ ] Example TOML section documented:

```toml
[litellm.metrics]
prometheus_enabled = true
prometheus_port = 9090
collect_interval_s = 15

[litellm.router]
strategy = "smart"          # "smart" | "cost_aware" | "latency_aware" | "round_robin"
failover_enabled = true

[litellm.helm]
namespace = "mrkrabs"
replicas = 2
```

### AC4: Backward Compatibility Guarantee
- [ ] Existing `ask()` API surface unchanged
- [ ] All adapters are opt-in via `[features]` flags — default OFF for routing, auth, helm
- [ ] If `enable_litellm_router = false`, SmartRouter is never instantiated (zero overhead)
- [ ] Acceptance test: run full existing test suite with all feature flags OFF — 100% pass

### AC5: Adapter Registration System
- [ ] Create adapter registry: `AdapterRegistry` singleton in `src/adapters/registry.py`
- [ ] `register(adapter: LiteLLMAdapter)` — idempotent, no duplicates
- [ ] `get(name: str) -> LiteLLMAdapter` — raises `AdapterNotFound` if missing
- [ ] `get_all() -> list[LiteLLMAdapter]`
- [ ] `health_check_all() -> dict[str, HealthStatus]`

---

## Technical Notes

- Study `litellm/llms/base_llm.py` for the adapter pattern reference — adapt, don't copy
- The adapter interface is a **contract**, not a wrapper — no LiteLLM code imported in the base
- Exception hierarchy: `AdapterError` (base) → `AdapterInitError`, `AdapterHealthError`, `AdapterConfigError`
- Feature flag names: `enable_litellm_router`, `enable_prometheus_metrics`, `enable_helm_deployment`, `enable_bearer_auth`, `enable_tracing`, `enable_cache`

---

## Definition of Done

- [ ] `docs/integration/adapter_interface_spec.md` committed and reviewed
- [ ] `src/adapters/base_adapter.py` implemented with full docstrings
- [ ] `src/adapters/registry.py` implemented
- [ ] Unit tests: 95%+ coverage on base adapter + registry
- [ ] Existing MR-Krabs test suite passes with all feature flags OFF
