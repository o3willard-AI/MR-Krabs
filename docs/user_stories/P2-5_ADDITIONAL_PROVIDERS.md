# P2-5: Additional LLM Providers (OpenAI & Anthropic)

**Priority:** P2 (Nice-to-have)  
**Estimate:** 3 days (Week 15-16)  
**User Story:** As a user, I want to use OpenAI and Anthropic models directly so I'm not limited to just OpenRouter and LM Studio.

## Context
Currently only OpenRouter and LM Studio are supported. We need to add direct support for:
- OpenAI (GPT-4, GPT-3.5, etc.)
- Anthropic (Claude models)

This provides users with more flexibility and potentially better pricing.

## Technical Requirements

### 1. OpenAI Provider Adapter
```python
from cost_orchestrator.providers import OpenAIProvider

provider = OpenAIProvider(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="https://api.openai.com/v1"
)
```

**Supported Models:**
- `gpt-4o` (premium)
- `gpt-4` (premium)
- `gpt-4-turbo` (premium)
- `gpt-3.5-turbo` (cheap)
- `o1-preview` (premium)
- `o1-mini` (medium)

**Pricing:** (per 1K tokens)
- GPT-4o: $2.50 input, $10 output
- GPT-4: $10 input, $30 output
- GPT-3.5: $0.50 input, $1.50 output

### 2. Anthropic Provider Adapter
```python
from cost_orchestrator.providers import AnthropicProvider

provider = AnthropicProvider(
    api_key=os.environ["ANTHROPIC_API_KEY"]
)
```

**Supported Models:**
- `claude-3-5-sonnet-20241022` (premium)
- `claude-3-opus-20240229` (premium)
- `claude-3-sonnet-20240229` (medium)
- `claude-3-haiku-20240307` (cheap)

**Pricing:** (per 1K tokens)
- Claude 3.5 Sonnet: $3 input, $15 output
- Claude 3 Opus: $15 input, $75 output
- Claude 3 Sonnet: $3 input, $15 output
- Claude 3 Haiku: $0.25 input, $1.25 output

### 3. Tier Mapping
Map models to cost tiers:
- **L0 (Free)**: N/A (no free Anthropic/OpenAI models)
- **L1 (Cheap)**: GPT-3.5, Claude Haiku
- **L2 (Medium)**: Claude Sonnet, GPT-4-turbo
- **L3 (Premium)**: GPT-4, Claude Opus, Claude 3.5 Sonnet

### 4. Configuration
```toml
[providers.openai]
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"

[providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"
base_url = "https://api.anthropic.com/v1"
```

## Acceptance Criteria

### Functional Tests (All Must Pass)
1. ✅ OpenAI provider makes successful API calls
2. ✅ Anthropic provider makes successful API calls
3. ✅ Cost calculation uses correct pricing
4. ✅ All supported models accessible
5. ✅ Error handling matches existing providers

### Integration Tests
1. ✅ OpenAI model works with cost tracking
2. ✅ Anthropic model works with cost tracking
3. ✅ Tier mapping works correctly
4. ✅ Budget enforcement works with new providers

### Documentation
1. ✅ README section: "Supported Providers"
2. ✅ Setup guide for OpenAI API key
3. ✅ Setup guide for Anthropic API key
4. ✅ Pricing table included

## Implementation Tasks

### Week 15 (Day 1)
- [ ] Design OpenAI provider adapter
- [ ] Implement OpenAI provider class
- [ ] Unit tests for OpenAI integration

### Week 15 (Day 2)
- [ ] Design Anthropic provider adapter
- [ ] Implement Anthropic provider class
- [ ] Unit tests for Anthropic integration

### Week 16 (Day 1)
- [ ] Integrate with tier manager
- [ ] Add pricing configuration
- [ ] End-to-end testing

### Week 16 (Day 2-3)
- [ ] Documentation completion
- [ ] Example code for both providers
- [ ] Testing with real API keys

## Dependencies
- OpenAI Python SDK
- Anthropic Python SDK
- API keys for testing

## Risks & Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| Provider API changes | Medium | Abstract provider interface |
| Pricing changes | Low | Configurable pricing, user override |
| Rate limiting | Medium | Implement retries, backoff |

## Success Metrics
- ✅ Both providers tested and working
- ✅ Cost tracking accurate for both
- ✅ Documentation complete
- ✅ Users can add providers without code changes

## Notes
- Optional feature, not critical for Phase 2 success
- Provides flexibility for users with existing API keys
- Must maintain same cost tracking as OpenRouter
- Consider making pricing configurable by user
