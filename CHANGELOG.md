# Changelog

## [0.2.0] — LiteLLM Integration Release — May 2026

### Phase 0 — Foundation
- Adapter interface system (`LiteLLMAdapter`, `AdapterRegistry`)
- Dependency audit and compatibility report
- Integration test harness (`MockMrKrabsCore`)
- CI/CD pipeline with quality gates

### Phase 1 — Observability
- Prometheus metrics adapter (`PrometheusMetricsAdapter`)
- 7 core metrics: requests, latency, cost, errors, escalations, vault ops, budget
- Grafana dashboard template
- Cost calculator with provider pricing registry
- Budget alerter with tier-blocking thresholds

### Phase 2 — Advanced Routing
- SmartRouter with 4 strategies (cost_aware, latency_aware, smart, round_robin)
- Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN)
- Strategy plugin architecture with auto-discovery
- Per-task-type routing profiles

### Phase 3 — Cloud-Native
- Kubernetes Helm chart
- Bearer token + API key authentication middleware
- Brute force protection
- K8s operator architecture blueprint

### Phase 4 — Provider Ecosystem
- Provider adapter framework (`BaseProviderAdapter`, `OpenAICompatibleAdapter`)
- 5 new providers: Anthropic, DeepSeek, Groq, Mistral, Google Vertex AI
- Rate limit handler with exponential backoff + jitter
- Token bucket client-side throttling

### Phase 5 — Advanced Features
- OpenTelemetry-compatible distributed tracing
- Intelligent caching with LRU eviction and TTL expiry
- Performance benchmark report
- Migration guide for existing users
- End-to-end integration test suite

### Testing
- 271 integration tests across 5 phases
- 764 existing unit tests — zero regressions
- 35 passed E2E scenarios

### Breaking Changes
- None. All features opt-in via feature flags.