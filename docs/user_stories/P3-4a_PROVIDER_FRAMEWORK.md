# Story P3-4a: Provider Adapter Framework

**Priority:** P0 (Critical — foundation for all future provider support)
**Estimate:** 4 days
**Phase:** Phase 4 — Weeks 8–9

---

## User Story

As a **developer** extending MR-Krabs to support new LLM providers,
I want a standardized provider adapter framework following LiteLLM's battle-tested patterns
So that adding a new provider requires ~100 lines of code instead of a custom integration each time.

---

## Acceptance Criteria

### AC1: Provider Adapter Base Class
- [ ] Implement `src/adapters/providers/base_provider.py`:
  ```python
  class BaseProviderAdapter(LiteLLMAdapter, ABC):
      """Standard interface for all LLM provider integrations."""
      
      @abstractmethod
      async def complete(self, messages: list[dict], **kwargs) -> LLMResponse: ...
      
      @abstractmethod
      async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...
      
      @abstractmethod
      def list_models(self) -> list[ModelInfo]: ...
      
      @abstractmethod
      def validate_config(self) -> bool: ...
      
      def supports_feature(self, feature: str) -> bool: ...  # vision, function_calling, json_mode
      def token_count(self, messages: list[dict]) -> int: ...
      def cost_estimate(self, model: str, token_count: int) -> CostEstimate: ...
  ```
- [ ] Standardized request/response objects:
  - `LLMResponse`: content, model, tokens_used, cost, finish_reason, latency_ms, raw_response
  - `ModelInfo`: name, context_window, max_output_tokens, pricing, capabilities, status
  - `CostEstimate`: min_cost, max_cost, expected_cost

### AC2: Adapter Registration & Discovery
- [ ] Provider adapter auto-discovery in `src/adapters/providers/`:
  - Any class inheriting `BaseProviderAdapter` in this directory is auto-registered
  - Registration pattern uses `__init_subclass__` hook — no manual registry calls
- [ ] Provider registration metadata:
  ```python
  class AnthropicAdapter(BaseProviderAdapter):
      provider_name = "anthropic"
      display_name = "Anthropic"
      default_model = "claude-sonnet-4-20250514"
      env_var = "ANTHROPIC_API_KEY"
      docs_url = "https://docs.anthropic.com/en/api"
  ```
- [ ] `ProviderRegistry.get("anthropic")` returns the adapter instance

### AC3: OpenAI-Compatible Adapter Base
- [ ] Create `src/adapters/providers/openai_compatible.py` — base class for any OpenAI-compatible API:
  ```python
  class OpenAICompatibleAdapter(BaseProviderAdapter):
      """For providers that expose an OpenAI-compatible chat completions endpoint.
      Subclass and set: provider_name, base_url, default_model, env_var."""
      
      async def complete(self, messages, **kwargs):
          # Standard OpenAI chat completions call against self.base_url
      async def stream(self, messages, **kwargs):
          # Standard SSE streaming
  ```
- [ ] Any provider with an OpenAI-compatible endpoint can be supported by subclassing this
- [ ] This is how we'll add most of the 80+ providers — not writing custom adapters for each

### AC4: Configuration-Driven Providers
- [ ] Providers configurable entirely via TOML (no code change needed for OpenAI-compatible providers):
  ```toml
  [providers.custom_provider]
  type = "openai_compatible"
  name = "my-custom-endpoint"
  base_url = "https://my-llm.internal/v1"
  api_key_env = "MY_LLM_KEY"
  models = ["my-model-v1", "my-model-v2"]
  pricing = { input_per_1k = 0.001, output_per_1k = 0.002 }
  ```
- [ ] Custom providers loaded at startup, available alongside built-in adapters
- [ ] Validation: `validate_config()` checks base_url is reachable, api_key is set

### AC5: Provider Capability Detection
- [ ] Each adapter declares capabilities via `supports_feature()`:
  - `vision`: image input supported
  - `function_calling`: tool use / function calling
  - `json_mode`: structured JSON output
  - `streaming`: SSE streaming
  - `system_message`: system prompt support
- [ ] Capabilities used by TierManager to route tasks to appropriate tiers
- [ ] Capabilities queried via MCP tool: `get_provider_capabilities("anthropic")`

### AC6: Testing Infrastructure
- [ ] Base provider test class for adapter authors:
  ```python
  class BaseProviderTest(unittest.TestCase):
      """Subclass and set: provider_name, test_model, requires_api_key"""
      
      def test_complete_returns_valid_response(self): ...
      def test_stream_yields_chunks(self): ...
      def test_list_models_returns_models(self): ...
      def test_cost_estimate_is_positive(self): ...
      def test_token_count_is_reasonable(self): ...
  ```
- [ ] All new provider adapters must pass this base test suite

---

## Technical Notes

- Fork provider registry patterns from `litellm/llms/base.py` — not the actual code, just the interface design
- `BaseProviderAdapter` extends `LiteLLMAdapter` (from P3-0b) — two-level adapter hierarchy
- Token counting: use provider-specific tokenizers when available, `tiktoken` fallback for OpenAI-compatible
- The OpenAI-compatible path handles ~70 of the 80+ providers — only ~10 need custom adapters
- Async-first: all `complete()` and `stream()` methods are `async` — consistent with FastAPI MCP server

---

## Definition of Done

- [ ] `BaseProviderAdapter` implemented with full abstract interface
- [ ] `OpenAICompatibleAdapter` implemented as reusable base class
- [ ] Provider auto-discovery via `__init_subclass__` working
- [ ] Configuration-driven custom providers functional (test with mock endpoint)
- [ ] `BaseProviderTest` mixin available for adapter authors
- [ ] Tests: `pytest tests/integration_litellm/phase_4/test_provider_framework.py -v`
- [ ] Documentation: `docs/providers/WRITING_ADAPTERS.md` — how to add a new provider
