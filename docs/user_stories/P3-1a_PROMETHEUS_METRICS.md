# Story P3-1a: Prometheus Metrics Integration

**Priority:** P0 (Critical — enterprise observability requirement)
**Estimate:** 5 days
**Phase:** Phase 1 — Weeks 2–3

---

## User Story

As an **operator** running MR-Krabs in production,
I want a Prometheus `/metrics` endpoint exposing request counts, latencies, costs, and error rates
So that I can monitor the system with existing infrastructure without custom instrumentation.

---

## Acceptance Criteria

### AC1: Forked Prometheus Utilities
- [ ] Fork `litellm/metrics/prometheus_utils.py` into `src/metrics/prometheus_utils.py`
- [ ] Adapt naming conventions: `litellm_*` → `mrkrabs_*` metric prefixes
- [ ] Strip LiteLLM-specific imports; keep only the metrics collection instrumentation patterns
- [ ] Implement as a `LiteLLMAdapter` subclass: `PrometheusMetricsAdapter(BaseAdapter)`

### AC2: Core Metrics Exposed
- [ ] `mrkrabs_requests_total{provider, model, tier, status}` — Counter, request lifecycle
- [ ] `mrkrabs_request_duration_seconds{provider, model, tier}` — Histogram, P50/P95/P99
- [ ] `mrkrabs_cost_dollars_total{provider, model}` — Counter, cumulative spend
- [ ] `mrkrabs_errors_total{provider, model, error_type}` — Counter, categorized errors
- [ ] `mrkrabs_tier_escalations_total{from_tier, to_tier}` — Counter, escalation patterns
- [ ] `mrkrabs_vault_operations_total{operation}` — Counter, vault read/write operations
- [ ] `mrkrabs_budget_remaining_dollars` — Gauge, current budget left

### AC3: MCP Server Integration
- [ ] Add `/metrics` endpoint to existing FastAPI MCP server
- [ ] Endpoint returns Prometheus text format (`Content-Type: text/plain`)
- [ ] Configurable port (default: `8001`), independent of main API port
- [ ] Start Prometheus HTTP server on adapter initialization if `[litellm.metrics].prometheus_enabled = true`
- [ ] Graceful shutdown: close metrics HTTP server on `shutdown()`

### AC4: Grafana Dashboard Templates
- [ ] Create `docs/dashboards/mrkrabs-overview.json` — importable Grafana dashboard with:
  - **Cost panel**: daily spend graph, budget remaining gauge, cost-by-model breakdown
  - **Performance panel**: P50/P95/P99 latency per tier, request throughput
  - **Errors panel**: error rate over time, top error types, escalation frequency
  - **Health panel**: vault status, adapter health checks
- [ ] Dashboard auto-populates from `/metrics` endpoint — no manual data source config beyond Prometheus URL
- [ ] Screenshot of populated dashboard in `docs/dashboards/README.md`

### AC5: Metrics Safety
- [ ] Provider names exposed only if `expose_provider_names = true` (default: false)
- [ ] API keys, vault contents, and task content never appear in metric labels
- [ ] Cardinality guard: reject metric labels with unbounded values (task IDs, prompt text)
- [ ] Rate-limit `/metrics` endpoint: max 1 scrape per 15 seconds per IP

---

## Technical Notes

- Use `prometheus_client` library (already in LiteLLM's dependency tree)
- Histogram buckets: `[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]` seconds
- Cost counter: use float with 6 decimal precision for sub-cent accuracy
- Registry pattern: use `CollectorRegistry` per adapter instance to avoid duplicate registration on hot-reload
- Reference: LiteLLM's `litellm/proxy/metric_endpoints.py` for endpoint patterns — note MR-Krabs uses FastAPI not Flask

---

## Definition of Done

- [ ] `src/metrics/prometheus_utils.py` implemented as `PrometheusMetricsAdapter`
- [ ] `/metrics` endpoint live at `http://localhost:8001/metrics` when enabled
- [ ] All 7 core metrics registered and populated with real data from `ask()` calls
- [ ] Grafana dashboard template imports and populates correctly
- [ ] Tests: `pytest tests/integration_litellm/phase_1/test_metrics.py -v --cov-fail-under=85`
- [ ] Security review: no sensitive data in metric labels
