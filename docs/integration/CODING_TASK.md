# MR-Krabs Integration Test — 2-Week Coding Task

**Task:** Build a multi-tenant API rate-limiting gateway
**Estimated:** 10 working days (2 weeks)
**Complexity:** Moderate — spans API design, middleware, persistence, testing, and deployment

---

## Task Description

Build `ThrottleProxy` — a lightweight API gateway that sits in front of LLM providers and enforces per-tenant rate limits with configurable policies. Think "nginx rate-limiting meets LLM cost control."

### Core Features (Week 1)

1. **Tenant-aware rate limiting** — Sliding window counters per tenant (identified by API key). Configurable: requests/minute, tokens/minute, concurrent requests.
2. **Policy engine** — YAML/TOML-driven policies. Gold tier: 1000 req/min. Silver: 100 req/min. Bronze: 10 req/min. Per-endpoint overrides.
3. **Proxy pass-through** — Transparently forward requests to upstream LLM providers (OpenAI, Anthropic). Preserve headers, streaming, error codes.
4. **Admin API** — CRUD for tenants, policies. GET /admin/tenants, POST /admin/policies, GET /admin/metrics/{tenant}.

### Advanced Features (Week 2)

5. **Distributed counters** — Redis-backed counters for multi-replica deployments. Fallback to in-memory when Redis unavailable.
6. **Cost tracking** — Track estimated spend per tenant per window. Fire webhook when tenant exceeds budget.
7. **Circuit breaker integration** — If upstream provider returns 5xx > threshold, temporarily route to backup provider.
8. **CLI tool** — `throttlectl` for tenant management, policy updates, metrics inspection.

### Technical Requirements

- **Language:** Python 3.11+
- **Framework:** FastAPI (matching MR-Krabs stack)
- **Persistence:** SQLite for tenant/policy storage (Redis optional for counters)
- **Testing:** pytest, 80%+ coverage, integration tests with mock upstream
- **Deployment:** Docker + docker-compose. Single binary entrypoint.
- **Documentation:** README with quickstart, API docs (FastAPI auto-generates /docs)

### Deliverables

```
throttle-proxy/
├── src/
│   ├── gateway.py          # Main proxy server
│   ├── limiter.py          # Rate limiting engine
│   ├── policies.py         # Policy parser and evaluator
│   ├── tenant_store.py     # SQLite tenant CRUD
│   ├── admin_api.py        # Admin endpoints
│   ├── proxy.py            # Upstream forwarding
│   ├── circuit.py          # Circuit breaker
│   ├── cost_tracker.py     # Spend tracking
│   └── cli.py              # throttlectl CLI
├── tests/
│   ├── test_limiter.py
│   ├── test_gateway.py
│   ├── test_policies.py
│   ├── test_tenant_store.py
│   ├── test_admin_api.py
│   ├── test_proxy.py
│   ├── test_circuit.py
│   └── test_integration.py
├── policies/
│   └── default.yaml        # Default policy tiers
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Estimated Effort

| Day | Focus | Output |
|-----|-------|--------|
| 1-2 | Core rate limiter + sliding window | limiter.py, test_limiter.py |
| 3-4 | Tenant store + admin API | tenant_store.py, admin_api.py, tests |
| 5 | Policy engine + YAML config | policies.py, test_policies.py |
| 6 | Proxy pass-through + streaming | proxy.py, test_proxy.py |
| 7 | Integration test + docker-compose | test_integration.py, compose file |
| 8 | Circuit breaker + cost tracking | circuit.py, cost_tracker.py |
| 9 | CLI tool | cli.py |
| 10 | Documentation, polish, final tests | README, cleanup |

### Success Criteria

- [ ] All 10 source files implemented with passing tests
- [ ] Admin API functional: create tenant, assign policy, query metrics
- [ ] Rate limiter correctly throttles requests above policy limits
- [ ] Proxy forwards requests and preserves streaming responses
- [ ] Circuit breaker trips on upstream 5xx and routes to backup
- [ ] CLI tool can create/list/delete tenants and policies
- [ ] Docker compose brings up full stack with `docker-compose up`
- [ ] 80%+ test coverage
