# Story P3-4c: Rate Limit Handling Utilities

**Priority:** P1 (High — reliability improvement for multi-provider operations)
**Estimate:** 2 days
**Phase:** Phase 4 — Week 9

---

## User Story

As a **developer** running high-throughput workloads through MR-Krabs,
I want sophisticated rate limit handling with exponential backoff and automatic provider rotation
So that rate-limited requests recover without manual intervention and without wasting retries.

---

## Acceptance Criteria

### AC1: Rate Limit Detection
- [ ] Implement `src/adapters/rate_limit.py` → `RateLimitHandler`
- [ ] Detect rate limits from provider responses:
  - HTTP 429 status code
  - `Retry-After` header (seconds or HTTP-date)
  - Provider-specific rate limit headers:
    - OpenAI: `x-ratelimit-remaining-requests`, `x-ratelimit-reset-requests`
    - Anthropic: `anthropic-ratelimit-requests-remaining`, `anthropic-ratelimit-requests-reset`
    - Google: `x-ratelimit-*` or `RetryInfo` in error detail
- [ ] Fallback: if no `Retry-After` header, use exponential backoff starting at 1s

### AC2: Backoff Strategy
- [ ] Implement exponential backoff with jitter:
  - Base delay: value from `Retry-After` header, or 1s
  - Multiplier: 2× per retry (1s → 2s → 4s → 8s → 16s)
  - Jitter: ±25% random to prevent thundering herd
  - Max delay: 60s (configurable)
  - Max retries: 5 (configurable per provider)
- [ ] Backoff respects `Retry-After` when provided (no stale retries)
- [ ] Per-provider backoff state — retrying `openai` doesn't delay `anthropic` requests

### AC3: Provider Rotation on Rate Limit
- [ ] When provider returns 429 and `Retry-After > 10s`:
  - Immediately rotate to next-best provider via SmartRouter (from P3-2a)
  - Log: `[RATE LIMIT] openai/gpt-4o rotation → anthropic/claude-sonnet-4 (retry-after: 45s, saved: ~$0.01 by not waiting)`
- [ ] Rotation is transparent to caller — they get a response, not a retry loop
- [ ] Original provider temporarily deprioritized for `Retry-After` duration
- [ ] Rotation respects budget constraints: won't rotate to a provider 10× more expensive

### AC4: Token Bucket Rate Limiter (Client-Side)
- [ ] Implement client-side token bucket to avoid hitting provider limits:
  ```toml
  [providers.openai.rate_limit]
  client_side_enabled = true
  requests_per_minute = 500
  tokens_per_minute = 200000
  ```
- [ ] Token bucket refills at configured rate, bursts up to bucket capacity
- [ ] Requests queued when bucket empty, not rejected (configurable max queue depth)
- [ ] Queue metrics: `mrkrabs_rate_limit_queue_depth{provider}`, `mrkrabs_rate_limit_queue_wait_seconds`

### AC5: Rate Limit Observability
- [ ] Prometheus metrics:
  - `mrkrabs_rate_limits_hit_total{provider, model}` — Counter
  - `mrkrabs_rate_limit_retries_total{provider, model, attempt}` — Counter
  - `mrkrabs_rate_limit_rotations_total{from_provider, to_provider}` — Counter
  - `mrkrabs_rate_limit_backoff_seconds{provider, model}` — Histogram
- [ ] Grafana panel: rate limit heatmap (providers × time, color by hit frequency)
- [ ] MCP analytics tool: `get_rate_limit_stats()` → per-provider hit rates, avg backoff, rotation frequency

### AC6: Rate Limit Budget Awareness
- [ ] When budget is low (<15%), adjust rate limit strategy:
  - Skip client-side queuing (don't burn budget waiting)
  - Rotate immediately on 429, don't retry at all
  - Log: `[BUDGET-AWARE RATE LIMIT] Skipping retry for openai (budget at 12%)`
- [ ] Configurable budget threshold: `rate_limit_budget_threshold_pct = 15`
- [ ] When budget is critical (<5%): block all requests to rate-limited providers entirely

### AC7: Provider-Specific Tuning
- [ ] Per-provider rate limit config:
  ```toml
  [providers.anthropic.rate_limit]
  requests_per_minute = 50        # Anthropic's free tier is tight
  max_retries = 3
  respect_retry_after = true
  
  [providers.openai.rate_limit]  
  requests_per_minute = 500       # OpenAI is generous
  max_retries = 5
  ```
- [ ] Default: sensible per-tier defaults from provider docs
- [ ] Override at runtime via MCP tool: `set_rate_limit("openai", rpm=1000)`

---

## Technical Notes

- Token bucket implementation: `asyncio` + `time.monotonic()` for thread-safe refill timing
- Rate limit headers are provider-specific — parse via adapter's `parse_rate_limit_headers()` method
- Jitter formula: `delay * (0.75 + random.random() * 0.5)` → range of 0.75–1.25× the base delay
- Client-side rate limiter is a soft limiter — doesn't guarantee provider won't still return 429
- Reference: AWS SDK exponential backoff, Stripe's rate limit handling patterns

---

## Definition of Done

- [ ] `RateLimitHandler` implemented with exponential backoff + jitter
- [ ] Provider rotation on long `Retry-After` working
- [ ] Client-side token bucket implemented
- [ ] Budget-aware rate limit adjustments working
- [ ] Prometheus metrics + Grafana panel for rate limits
- [ ] Tests: `pytest tests/integration_litellm/phase_4/test_rate_limits.py -v`
- [ ] Test scenarios: 429 with Retry-After, 429 without, budget-aware skip, provider rotation, token bucket fill/drain
