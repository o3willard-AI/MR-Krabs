# Adapter Interface Specification

**Version:** 1.0
**Status:** Implemented
**Last Updated:** May 2026

---

## Overview

This document defines the standard interface contract for all LiteLLM-forked components integrated into MR-Krabs. Every component — metrics collection, routing, caching, tracing, authentication — inherits from `LiteLLMAdapter` and follows the lifecycle, configuration, and error contracts defined here.

**Core principle:** Adapters are plugins. They extend MR-Krabs without modifying core code. Each adapter is independently enabled/disabled via feature flags.

---

## Base Adapter (`LiteLLMAdapter`)

Location: `src/adapters/base_adapter.py`

### Abstract Methods (must implement)

| Method | Returns | Purpose |
|--------|---------|---------|
| `initialize()` | `bool` | Setup resources. Called once at startup. Return `True` on success. |
| `health_check()` | `HealthStatus` | Check if adapter is functioning. One of: `HEALTHY`, `DEGRADED`, `DOWN`. |
| `shutdown()` | `None` | Cleanup resources. Called on graceful shutdown. |

### Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | `str` | Class name | Human-readable adapter identifier |
| `enabled` | `bool` | `True` | Whether adapter is active via feature flag. Override per adapter. |
| `initialized` | `bool` | `False` | Whether `initialize()` has been called successfully |

### Configuration Resolution

All adapters use `get_config(key, default, litellm_default, env_var)` with this priority order:

1. **MR-Krabs config** (`[litellm.<section>]` in TOML) — highest priority
2. **LiteLLM default** — the value LiteLLM ships with
3. **Environment variable** — OS env var fallback
4. **Function default** — ultimate fallback

```python
# Example: Prometheus adapter resolving its port
port = self.get_config(
    "prometheus_port",
    default=9090,                    # ultimate fallback
    litellm_default=8001,            # LiteLLM's default
    env_var="MRKRABS_METRICS_PORT"   # env var override
)
```

---

## Error Hierarchy

```
AdapterError (base)
├── AdapterInitError      # initialize() failed
├── AdapterHealthError    # health_check() returned DOWN
├── AdapterConfigError    # invalid configuration
└── AdapterNotFound       # registry lookup failed
```

All adapter errors inherit from `AdapterError`. Core MR-Krabs code catches `AdapterError` for graceful degradation — a failed adapter does not crash the system.

---

## Lifecycle Hooks

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  Created  │───→│ initialize() │───→│ health_check()│───→│ shutdown()│
│           │    │              │    │  (periodic)  │    │          │
└──────────┘    └──────────────┘    └──────────────┘    └──────────┘
     │               │                      │                  │
     │          On failure:            On DOWN:           Best-effort
     │          AdapterInitError     AdapterHealthError   cleanup
     │          → adapter disabled   → circuit breaker    → mark uninitialized
```

1. **Created**: Constructor called with config. No resources allocated yet.
2. **initialize()**: Setup resources (HTTP clients, connections, file handles). Return `True` on success.
3. **health_check()**: Called periodically (every 30s by default). Returns `HEALTHY`, `DEGRADED`, or `DOWN`.
4. **shutdown()**: Called on process exit. Best-effort cleanup.

---

## Feature Flag Contract

Adapters respect opt-in/opt-out via the `enabled` property. Each adapter overrides this to check a specific feature flag:

| Adapter | Feature Flag | Default |
|---------|-------------|---------|
| `PrometheusMetricsAdapter` | `enable_prometheus_metrics` | `true` |
| `SmartRouter` | `enable_litellm_router` | `false` |
| `HelmChartAdapter` | `enable_helm_deployment` | `false` |
| `AuthenticationMiddleware` | `enable_bearer_auth` | `false` |
| `TracingAdapter` | `enable_tracing` | `false` |
| `CachingAdapter` | `enable_cache` | `false` |

When `enabled = False`:
- `initialize()` is never called
- The adapter does not consume any resources
- `health_check()` returns `HEALTHY` (disabled is not broken)
- `shutdown()` is a no-op

This ensures backward compatibility: existing MR-Krabs installations continue working unchanged with all new feature flags set to `false`.

---

## Metrics Contract

Adapters that produce metrics must register them via the Prometheus `CollectorRegistry`. Key requirements:

1. **Prefix**: All metrics use the `mrkrabs_` prefix
2. **Labels**: Never include unbounded values (task IDs, prompt text, API keys)
3. **Cardinality guard**: Reject labels with unbounded cardinality
4. **Sensitive data**: Provider names only exposed if `expose_provider_names = true`

---

## Registry (`AdapterRegistry`)

Location: `src/adapters/registry.py`

Singleton managing all adapters. Key operations:

```python
registry = AdapterRegistry()
registry.register(adapter)           # idempotent registration
registry.get("prometheus")            # lookup by name
registry.get_all()                    # all adapters
registry.health_check_all()           # {"prometheus": HEALTHY, "router": DOWN}
registry.initialize_all()             # init all enabled adapters, returns success map
registry.shutdown_all()               # best-effort cleanup
```

---

## Example: Creating a New Adapter

```python
from src.adapters import LiteLLMAdapter, HealthStatus

class PrometheusMetricsAdapter(LiteLLMAdapter):
    @property
    def enabled(self) -> bool:
        return self.get_config("enable_prometheus_metrics", default=True)
    
    def initialize(self) -> bool:
        port = self.get_config("prometheus_port", default=8001)
        # Start Prometheus HTTP server on port
        self._initialized = True
        return True
    
    def health_check(self) -> HealthStatus:
        try:
            # Check if metrics endpoint is responding
            return HealthStatus.HEALTHY
        except Exception:
            return HealthStatus.DOWN
    
    def shutdown(self) -> None:
        # Stop Prometheus HTTP server
        self._initialized = False
```

---

## Architecture Decision Record: Adapter Pattern vs Direct Integration

**Decision:** Use adapter pattern (fork `base_llm.py` concepts)

**Why:**
- Preserves MR-Krabs' clean architecture
- Allows swapping providers without changing core logic
- Each component independently enabled/disabled
- No forced dependencies between components

**Rejected alternative:** Direct integration would couple LiteLLM internals to MR-Krabs, making future LiteLLM upgrades or MR-Krabs refactors risky.

---

## Backward Compatibility

- `ask()` API signature unchanged
- Existing config files load with warnings, not errors
- All adapters opt-in via feature flags
- If all flags are `false`: zero overhead, identical behavior to pre-integration MR-Krabs
