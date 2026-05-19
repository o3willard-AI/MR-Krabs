# Story P3-4b: Five New Provider Adapters (Anthropic, Vertex, Mistral, DeepSeek, Groq)

**Priority:** P1 (High — dramatically expands market reach)
**Estimate:** 5 days
**Phase:** Phase 4 — Weeks 8–9

---

## User Story

As a **developer** using MR-Krabs,
I want native support for Anthropic, Google Vertex AI, Mistral, DeepSeek, and Groq providers
So that I can use the best model for each task without leaving the MR-Krabs cost optimization framework.

---

## Acceptance Criteria

### AC1: Anthropic Adapter
- [ ] Implement `src/adapters/providers/anthropic.py` → `AnthropicAdapter(OpenAICompatibleAdapter)`
- [ ] Note: Anthropic's API is NOT OpenAI-compatible — needs custom `complete()` implementation
- [ ] Supported models: `claude-sonnet-4-20250514`, `claude-opus-4-20250514`, `claude-haiku-3-5`
- [ ] Handles Anthropic-specific:
  - Messages API format (system prompt as top-level field, not message)
  - Streaming via SSE with `data:` prefix
  - Token counting via Anthropic's `usage` response field
  - Rate limit headers: `anthropic-ratelimit-*`
- [ ] API key from env var `ANTHROPIC_API_KEY` or vault entry `/providers/anthropic/api_key`

### AC2: Google Vertex AI Adapter
- [ ] Implement `src/adapters/providers/vertex.py` → `VertexAdapter(BaseProviderAdapter)`
- [ ] Not OpenAI-compatible — uses Google Cloud authentication (service account JSON)
- [ ] Supported models: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`
- [ ] Authentication: service account JSON from `GOOGLE_APPLICATION_CREDENTIALS` env var or vault
- [ ] Project ID and region configurable: `VERTEX_PROJECT`, `VERTEX_REGION` (default: `us-central1`)
- [ ] Handles Vertex-specific:
  - REST API endpoint: `https://{region}-aiplatform.googleapis.com/v1/...`
  - Safety filter configuration (opt-out of content filtering via TOML)
  - Token counting via `usageMetadata` in response
- [ ] Pricing reads from Vertex pricing API or configured manually in provider_pricing.toml

### AC3: Mistral Adapter
- [ ] Implement `src/adapters/providers/mistral.py` → `MistralAdapter(BaseProviderAdapter)`
- [ ] Mistral has its own API — similar to OpenAI but with differences (custom adapter needed)
- [ ] Supported models: `mistral-large-latest`, `mistral-medium-latest`, `mistral-small-latest`
- [ ] Available via both:
  - Mistral's API (`api.mistral.ai`) — `MISTRAL_API_KEY` env var
  - Azure deployment (optional) — `AZURE_MISTRAL_ENDPOINT` + `AZURE_MISTRAL_KEY`
- [ ] Handles Mistral-specific: native function calling format, `safe_prompt` flag for moderation
- [ ] Token counting via `usage` in response

### AC4: DeepSeek Adapter
- [ ] Implement `src/adapters/providers/deepseek.py` → `DeepSeekAdapter(OpenAICompatibleAdapter)`
- [ ] DeepSeek API IS OpenAI-compatible — minimal custom code needed
- [ ] Supported models: `deepseek-chat`, `deepseek-reasoner` (DeepSeek-R1)
- [ ] Endpoint: `https://api.deepseek.com/v1`
- [ ] Handles DeepSeek-specific:
  - Reasoner model returns `reasoning_content` in addition to `content` (preserve both in `LLMResponse`)
  - Large context window (128K tokens) — pass through accurately
- [ ] API key from `DEEPSEEK_API_KEY` env var

### AC5: Groq Adapter
- [ ] Implement `src/adapters/providers/groq.py` → `GroqAdapter(OpenAICompatibleAdapter)`
- [ ] Groq API IS OpenAI-compatible — very thin adapter
- [ ] Supported models: `llama-4-scout-17b-16e`, `llama-4-maverick-17b-128e`, `mixtral-8x7b-32768`
- [ ] Endpoint: `https://api.groq.com/openai/v1`
- [ ] Known quirk: Groq doesn't support `logprobs` or `n > 1` — adapter must strip these params
- [ ] API key from `GROQ_API_KEY` env var

### AC6: Cross-Provider Testing
- [ ] Every adapter passes base provider test suite (from P3-4a AC6)
- [ ] Provider-specific tests for unique features:
  - Anthropic: system prompt handling, streaming format
  - Vertex: service account auth, safety filter bypass
  - Mistral: function calling, Azure fallback
  - DeepSeek: reasoning_content preservation
  - Groq: unsupported parameter stripping
- [ ] Integration test via `ask()`: each provider's cheapest model tested with simple prompt
- [ ] Cost tracking verified: actual spend matches estimated within 15%
- [ ] All 5 providers appear in `mrkrabs_providers_available` metric

### AC7: Documentation
- [ ] Each provider has a one-page doc in `docs/providers/`:
  - Setup: env vars needed, API key acquisition link
  - Supported models with pricing
  - Known limitations / quirks
  - Example: `ask("hello", provider="mistral")`

---

## Technical Notes

- API key precedence: function parameter → vault entry → env var → error
- All adapters handle rate limiting gracefully: respect `Retry-After` headers from providers
- Provider-specific error mapping: translate provider error codes to MR-Krabs error types
- DeepSeek and Groq are trivial (OpenAI-compatible) — Anthropic and Vertex are the heavy lifts
- Test API keys use GitHub Environments secrets at CI time, never committed

---

## Definition of Done

- [ ] All 5 adapters implemented and passing base test suite
- [ ] All 5 adapters working through `ask()` with cost tracking
- [ ] Rate limit handling tested (mock 429 responses)
- [ ] Provider docs complete for all 5
- [ ] Tests: `pytest tests/integration_litellm/phase_4/test_providers.py -v -m external`
- [ ] Provider matrix: 60+ tests across adapters + edge cases
