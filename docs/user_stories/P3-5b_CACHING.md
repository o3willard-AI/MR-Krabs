# Story P3-5b: Intelligent Caching Middleware

**Priority:** P2 (Medium — cost savings potential, not launch-critical)
**Estimate:** 3 days
**Phase:** Phase 5 — Week 11

---

## User Story

As a **developer** running repeated or similar queries through MR-Krabs,
I want an intelligent caching layer that serves cached responses for identical or semantically similar requests
So that I reduce LLM costs by up to 30% without degrading output quality.

---

## Acceptance Criteria

### AC1: Forked Caching Middleware
- [ ] Fork caching patterns from LiteLLM into `src/adapters/cache.py`
- [ ] Implement as `CachingAdapter(LiteLLMAdapter)` — opt-in via `[litellm.cache].enabled = true`
- [ ] Cache sits between `SmartRouter` and `BaseProviderAdapter.complete()`:
  ```
  ask() → SmartRouter → Cache.check() → HIT: return cached → MISS: provider.complete() → Cache.store()
  ```

### AC2: Cache Strategies
- [ ] **Exact Match** (default):
  - Cache key: `hash(provider + model + messages + temperature + max_tokens)`
  - Deterministic, zero false positives
  - Use case: repeated unit tests, CI pipelines, development loops
- [ ] **Semantic Match** (opt-in, experimental):
  - Cache key: embedding of prompt text (via cheap embedding model)
  - Cosine similarity > 0.95 → cache hit
  - Use case: similar user queries across sessions ("summarize this article")
  - Flagged `[BETA]` in config, warns on enable
- [ ] **TTL-Based**:
  - Configurable TTL per model tier: L0=24h, L1=12h, L2=1h, L3=0 (never cache premium)
  - Configurable per endpoint: `/ask` caches, `/analyze` does not

### AC3: Cache Backend
- [ ] In-memory LRU cache (default):
  - Configurable max size: `max_entries: 1000`
  - Thread-safe, zero external dependencies
  - Lost on restart — acceptable for development use
- [ ] Redis backend (production):
  - `backend = "redis"`, `redis_url = "redis://localhost:6379/0"`
  - Shared across MR-Krabs replicas
  - Configurable key prefix: `mrkrabs:cache:`
- [ ] Backend interface: `CacheBackend(ABC)` with `get(key)`, `set(key, value, ttl)`, `invalidate(pattern)`

### AC4: Cache Safety
- [ ] **Never cache**: requests with `temperature > 0` OR `stream = true` OR `n > 1`
- [ ] **Never cache** error responses (4xx, 5xx)
- [ ] Cache-busting headers: if provider response includes `no-cache` directive, don't store
- [ ] Manual invalidation: `mrkrabs cache clear --provider openai` or `--all`
- [ ] Cache hit log at DEBUG: `[CACHE HIT] task=abc123, saved=$0.042, cache_size=847/1000`
- [ ] Prometheus metrics:
  - `mrkrabs_cache_hits_total`, `mrkrabs_cache_misses_total` — Counters
  - `mrkrabs_cache_size_entries` — Gauge
  - `mrkrabs_cache_savings_dollars_total` — Counter (estimated cost saved)

### AC5: Cost Savings Analysis
- [ ] Dashboard panel: cumulative cache savings vs. provider spend
- [ ] Projected savings: extrapolate current hit rate to monthly estimate
- [ ] Cache analytics queryable via MCP tool: `get_cache_stats()` returns:
  - Hit rate, miss rate, total savings, top cached models, avg TTL remaining
- [ ] Savings report: `[CACHE] This session: 42 hits, $1.87 saved, 31% of requests served from cache`

### AC6: Cache Warming (Optional / Future)
- [ ] Design for cache warming (Phase 6+): pre-populate cache with common queries
- [ ] TOML placeholder:
  ```toml
  [litellm.cache.warming]
  enabled = false    # future
  queries_file = "cache_warmup_queries.json"
  ```

---

## Technical Notes

- LRU implementation: `collections.OrderedDict` for O(1) get/set/evict
- Redis backend: use `redis` or `redis-py` (already a dependency if Redis backend chosen)
- Semantic matching requires `sentence-transformers` or similar — make it an optional dependency (`pip install mrkrabs[cache-semantic]`)
- Cache key must include model name — different models produce different output for same prompt
- Budget tracking: cached responses count as $0 cost (already paid for) but are tracked separately from new API calls

---

## Definition of Done

- [ ] `CachingAdapter` implemented with exact-match LRU and Redis backends
- [ ] TTL-based expiry working per tier
- [ ] Safety rules enforced (no cache for temperature>0, streams, errors)
- [ ] Cache invalidation CLI working
- [ ] Prometheus metrics + Grafana savings panel
- [ ] Tests: `pytest tests/integration_litellm/phase_5/test_cache.py -v`
- [ ] Test scenarios: cache hit, cache miss, TTL expiry, LRU eviction, Redis shared cache, manual invalidation
