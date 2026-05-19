# Story P3-5a: OpenTelemetry Distributed Tracing

**Priority:** P2 (Medium — observability maturity, not a launch blocker)
**Estimate:** 4 days
**Phase:** Phase 5 — Weeks 10–12

---

## User Story

As a **platform engineer** debugging complex multi-agent workflows,
I want distributed tracing across every MR-Krabs request — from agent to provider to response
So that I can pinpoint exactly where latency, errors, or cost anomalies originate in long-running task chains.

---

## Acceptance Criteria

### AC1: Forked Tracing Utilities
- [ ] Fork `litellm/middleware/tracing_utils.py` into `src/metrics/tracing.py`
- [ ] Implement OpenTelemetry integration via `opentelemetry-api` and `opentelemetry-sdk`
- [ ] Configurable exporter: OTLP (gRPC or HTTP), Jaeger, Zipkin, or console (debug)
- [ ] Implement as `TracingAdapter(LiteLLMAdapter)` — opt-in via `[litellm.tracing].enabled = true`

### AC2: Span Coverage
- [ ] Every `ask()` call creates a root span: `mrkrabs.ask`
  - Attributes: `task_id`, `task_summary` (truncated to 200 chars), `budget_remaining`
- [ ] Child spans for each phase:
  - `mrkrabs.route.select` — provider/model selection, strategy used, candidates evaluated
  - `mrkrabs.provider.complete` — provider name, model, token count, cost, latency
  - `mrkrabs.tier.escalate` — from_tier, to_tier, reason
  - `mrkrabs.vault.read` — entry path (not value), cache hit/miss
- [ ] Span events for significant moments:
  - Budget warning fired, circuit breaker tripped, rate limit hit, provider rotation
- [ ] Error spans: full stack trace as span event on exception

### AC3: Trace Context Propagation
- [ ] W3C Trace Context headers propagated to provider API calls:
  - `traceparent: 00-{trace_id}-{span_id}-01`
  - `tracestate: mrkrabs={task_id}`
- [ ] If incoming request already has trace context, MR-Krabs continues the trace (doesn't create new root)
- [ ] Trace IDs included in log output: `[trace=abc123][span=def456] Starting ask()...`

### AC4: Configuration
- [ ] TOML config:
  ```toml
  [litellm.tracing]
  enabled = false                    # default OFF
  exporter = "otlp_grpc"            # "otlp_grpc" | "otlp_http" | "jaeger" | "zipkin" | "console"
  endpoint = "http://jaeger:4317"   # collector endpoint
  sample_rate = 1.0                 # 1.0 = all traces, 0.1 = 10%
  sensitive_fields = ["api_key", "vault_key", "token"]  # stripped from span attributes
  max_attribute_length = 1000       # truncate long values
  ```
- [ ] Environment variable overrides: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME=mrkrabs`
- [ ] When `enabled = false`: zero overhead — no spans created, no exporter initialized

### AC5: Grafana Trace Viewer
- [ ] Create `docs/dashboards/mrkrabs-traces.json` — Grafana dashboard with trace viewer
- [ ] Trace search: by task_id, provider, error status, latency > threshold
- [ ] Trace waterfall view: span timeline for a single `ask()` call
- [ ] Trace analytics: top 10 slowest providers, most-escalated task types, error hotspots
- [ ] Screenshot of trace waterfall in `docs/dashboards/README.md`

### AC6: Performance Budget
- [ ] Tracing overhead: <1% increase in `ask()` latency when enabled
- [ ] Sampled (10%) mode: <0.1% overhead
- [ ] Memory: span data flushed to exporter within 5s — no unbounded memory growth
- [ ] Benchmark: 1000 `ask()` calls with tracing ON vs OFF, publish variance

---

## Technical Notes

- Use `opentelemetry-instrumentation-fastapi` for automatic FastAPI span instrumentation
- Manual instrumentation for provider calls (not auto-instrumented)
- Batch span processor: batch spans every 5s or 512 spans, whichever comes first
- Sensitive field redaction: configurable list, applied at span creation time (before export)
- Reference: OpenTelemetry Python SDK, LiteLLM's `LiteLLMLogging` callback pattern

---

## Definition of Done

- [ ] `TracingAdapter` implemented with OTLP gRPC and console exporters
- [ ] Root + child spans for all phases (route, provider, tier, vault)
- [ ] W3C trace context propagated to provider calls
- [ ] Trace IDs in log output
- [ ] Grafana trace viewer dashboard functional
- [ ] Performance benchmark: <1% overhead verified
- [ ] Tests: `pytest tests/integration_litellm/phase_5/test_tracing.py -v`
