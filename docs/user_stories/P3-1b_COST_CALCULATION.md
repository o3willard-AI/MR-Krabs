# Story P3-1b: Unified Cost Calculation Utilities

**Priority:** P1 (High — foundation for cost-aware routing and accurate budget enforcement)
**Estimate:** 3 days
**Phase:** Phase 1 — Week 3

---

## User Story

As a **developer** using MR-Krabs,
I want unified cost calculation that accurately predicts and tracks spending across all providers
So that budget enforcement is consistent regardless of which model ultimately handles the request.

---

## Acceptance Criteria

### AC1: Forked Cost Utilities
- [ ] Fork cost calculation logic from LiteLLM into `src/adapters/cost_calculator.py`
- [ ] Implement as `CostCalculator` (not an adapter — a utility class used by routing and metrics adapters)
- [ ] Support these pricing models:
  - Per-token pricing (input + output tokens, different rates)
  - Per-request flat fee
  - Per-character pricing (for non-tokenized providers)
  - Tiered volume discounts (if provider offers them)

### AC2: Provider Pricing Registry
- [ ] Maintain pricing data in `src/adapters/provider_pricing.json` (or TOML):
  ```toml
  [providers.openai]
  gpt-4o = { input_per_1k = 0.00250, output_per_1k = 0.01000 }
  gpt-4o-mini = { input_per_1k = 0.00015, output_per_1k = 0.00060 }

  [providers.anthropic]
  claude-sonnet-4-20250514 = { input_per_1k = 0.00300, output_per_1k = 0.01500 }
  ```
- [ ] Pricing file has a `last_updated` timestamp and source URL for each provider
- [ ] `CostCalculator` caches pricing in memory, refreshes on config reload
- [ ] Unknown models default to the provider's median price with a `[WARN]` log

### AC3: Pre-Request Cost Estimation
- [ ] `estimate_cost(model: str, estimated_tokens: int) -> CostEstimate` returns:
  - `min_cost`: float — best case (short response)
  - `max_cost`: float — worst case (max token limit)
  - `expected_cost`: float — median based on historical ratios
- [ ] Used by budget enforcer BEFORE making the API call
- [ ] Request blocked if `min_cost > budget_remaining`

### AC4: Post-Request Cost Reconciliation
- [ ] `calculate_actual_cost(model: str, response: LLMResponse) -> float`
- [ ] Extracts actual token usage from provider response metadata
- [ ] Compares against estimate, logs variance for accuracy tracking:
  - `[COST] gpt-4o: estimated $0.042, actual $0.038 (variance: -9.5%)`
- [ ] Updates Prometheus `mrkrabs_cost_dollars_total` counter

### AC5: Vault Integration
- [ ] Cost calculator reads provider API costs from vault when `cost_source = "vault"`:
  - Vault entry: `/providers/openai/cost_config`
  - Fallback chain: vault → pricing file → hardcoded defaults → MEDIAN_GUESS
- [ ] Cost calculations never log full API keys — only last 4 chars if needed for debugging

### AC6: Accuracy Tracking
- [ ] Track estimation accuracy per model: `mrkrabs_cost_estimation_accuracy{model}` — Gauge, ratio actual/estimated
- [ ] Weekly accuracy report: models with >20% variance flagged for pricing review
- [ ] Acceptance: estimation accuracy within ±15% for 90% of requests after 1 week of production data

---

## Technical Notes

- Token counting: use `tiktoken` for OpenAI models, provider-specific tokenizers where available, character-count fallback otherwise
- Pricing file format should support comments (TOML) for source URLs
- Cost values stored as `Decimal` (not float) internally to avoid floating-point accumulation errors
- Reference: LiteLLM's `litellm/cost_calculator.py` and model price JSON files

---

## Definition of Done

- [ ] `src/adapters/cost_calculator.py` implemented
- [ ] `src/adapters/provider_pricing.toml` populated for all currently supported providers
- [ ] `estimate_cost()` and `calculate_actual_cost()` both functional
- [ ] Vault integration tested with mock vault
- [ ] Tests: `pytest tests/integration_litellm/phase_1/test_cost_utils.py -v`
- [ ] Estimation accuracy baseline established and logged
