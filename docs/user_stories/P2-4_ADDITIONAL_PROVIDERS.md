# Story P2-4: Additional LLM Providers

**Priority**: P1 (High - Expands Capability)  
**Estimate**: 1 week  
**Phase**: Week 14

---

## User Story

As a developer  
I want support for multiple LLM providers beyond OpenRouter  
So that I can choose the best provider for my needs, avoid vendor lock-in, and optimize costs further

---

## Acceptance Criteria

### AC1: OpenAI Provider Adapter

- [ ] OpenAI API support (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- [ ] Pricing configured accurately
- [ ] Works with existing tier system
- [ ] Budget tracking integrated
- [ ] Authentication via `OPENAI_API_KEY` env var

### AC2: Anthropic Provider Adapter

- [ ] Anthropic API support (claude-3-opus, claude-3-sonnet, etc.)
- [ ] Pricing configured accurately
- [ ] Works with existing tier system
- [ ] Budget tracking integrated
- [ ] Authentication via `ANTHROPIC_API_KEY` env var

### AC3: Provider Selection

- [ ] Providers auto-detected based on available keys
- [ ] Fallback to LM Studio if no API keys set
- [ ] Provider switching configurable
- [ ] Clear error messages for missing keys
- [ ] `orchestrator doctor` shows available providers

### AC4: Pricing Configuration

- [ ] OpenAI pricing in pyproject.toml
- [ ] Anthropic pricing in pyproject.toml
- [ ] Pricing configurable per model
- [ ] Pricing updates tracked
- [ ] Accurate cost calculation for all providers

### AC5: Tier Mapping

- [ ] Each provider mapped to appropriate tiers
- [ ] Cheapest models in L0 tier
- [ ] Balanced models in L1 tier
- [ ] Premium models in L2/L3 tiers
- [ ] Cross-provider tier compatibility

### AC6: Unified API

- [ ] Same `ask()` function works with all providers
- [ ] No code changes needed for provider switching
- [ ] Provider selection transparent to user
- [ ] Error messages provider-agnostic
- [ ] All providers tested end-to-end

---

## Technical Implementation

### Files to Create/Modify

1. `src/providers/openai_provider.py` - OpenAI adapter
2. `src/providers/anthropic_provider.py` - Anthropic adapter
3. `src/core/pricing.py` - Extend pricing table
4. `src/core/config.py` - Provider detection logic
5. `docs/user_stories/P2-4_ADDITIONAL_PROVIDERS.md` - This story

### Implementation Plan

```python
# src/providers/openai_provider.py

from openai import OpenAI
from src.core.cost import TokenCount

class OpenAIProvider:
    """OpenAI API provider adapter."""
    
    MODEL_PRICING = {
        "gpt-4o": {
            "prompt": 0.0000025,
            "completion": 0.000010
        },
        "gpt-4-turbo": {
            "prompt": 0.000010,
            "completion": 0.000030
        },
        "gpt-3.5-turbo": {
            "prompt": 0.0000005,
            "completion": 0.0000015
        },
    }
    
    def __init__(self):
        self.client = OpenAI()
    
    def chat_completions_create(
        self, 
        model: str, 
        messages: list[dict],
        **kwargs
    ) -> dict:
        """Create chat completion via OpenAI API."""
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        
        # Extract token usage
        usage = response.usage
        tokens = TokenCount(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens
        )
        
        return {
            "success": True,
            "output": response.choices[0].message.content,
            "tokens": tokens,
            "model": model,
            "duration_seconds": response.response_ms / 1000 if hasattr(response, 'response_ms') else 0
        }
    
    def get_pricing(self, model: str) -> dict:
        """Get pricing for model."""
        return self.MODEL_PRICING.get(model, {
            "prompt": 0.000001,
            "completion": 0.000001
        })
```

```python
# src/providers/anthropic_provider.py

import anthropic
from src.core.cost import TokenCount

class AnthropicProvider:
    """Anthropic API provider adapter."""
    
    MODEL_PRICING = {
        "claude-3-opus-20240229": {
            "prompt": 0.000015,
            "completion": 0.000075
        },
        "claude-3-sonnet-20240229": {
            "prompt": 0.000003,
            "completion": 0.000015
        },
        "claude-3-haiku-20240307": {
            "prompt": 0.00000025,
            "completion": 0.00000125
        },
    }
    
    def __init__(self):
        self.client = anthropic.Anthropic()
    
    def messages_create(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """Create message via Anthropic API."""
        response = self.client.messages.create(
            model=model,
            messages=messages,
            **kwargs
        )
        
        # Extract token usage
        tokens = TokenCount(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens
        )
        
        return {
            "success": True,
            "output": response.content[0].text,
            "tokens": tokens,
            "model": model,
            "duration_seconds": 0
        }
    
    def get_pricing(self, model: str) -> dict:
        """Get pricing for model."""
        return self.MODEL_PRICING.get(model, {
            "prompt": 0.000001,
            "completion": 0.000001
        })
```

```python
# src/core/pricing.py

# Extend existing MODEL_COSTS with new providers

MODEL_COSTS = {
    # ... existing OpenRouter models ...
    
    # OpenAI models
    "gpt-4o": {"prompt": 0.0000025, "completion": 0.000010},
    "gpt-4-turbo": {"prompt": 0.000010, "completion": 0.000030},
    "gpt-3.5-turbo": {"prompt": 0.0000005, "completion": 0.0000015},
    
    # Anthropic models
    "claude-3-opus-20240229": {"prompt": 0.000015, "completion": 0.000075},
    "claude-3-sonnet-20240229": {"prompt": 0.000003, "completion": 0.000015},
    "claude-3-haiku-20240307": {"prompt": 0.00000025, "completion": 0.00000125},
}
```

```python
# src/core/config.py

def detect_available_providers() -> list[str]:
    """Detect which providers are available based on environment variables."""
    providers = []
    
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append("openrouter")
    
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("anthropic")
    
    if os.environ.get("LM_STUDIO_HOST"):
        providers.append("lmstudio")
    
    return providers
```

---

## Testing Requirements

### Unit Tests (test_openai_provider.py, test_anthropic_provider.py)

1. `test_openai_chat_completion` - OpenAI API calls work
2. `test_anthropic_message_creation` - Anthropic API calls work
3. `test_token_extraction` - Token counts extracted correctly
4. `test_pricing_accuracy` - Pricing matches official docs
5. `test_error_handling` - API errors handled gracefully

### Integration Tests

1. Real OpenAI task with cost tracking
2. Real Anthropic task with cost tracking
3. Provider switching based on available keys
4. Budget enforcement across providers
5. `orchestrator doctor` shows correct providers

---

## Provider Tier Mapping

| Tier | OpenRouter | OpenAI | Anthropic | LM Studio |
|------|-----------|--------|------------|-----------|
| **L0** | qwen/qwen3.5-397b-a17b | gpt-3.5-turbo | claude-3-haiku | local |
| **L1** | x-ai/grok-4.1-fast | gpt-4-turbo | claude-3-sonnet | local |
| **L2** | claude-sonnet-4.6 | - | claude-3-sonnet | - |
| **L3** | claude-opus-4.6 | gpt-4o | claude-3-opus | - |

---

## Out of Scope

- Google Vertex AI (Phase 3)
- AWS Bedrock (Phase 3)
- Custom provider configuration
- Provider performance benchmarking
- Automatic provider selection (manual via env vars)

---

## Dependencies

- P1 complete (core infrastructure)
- Provider API access for testing

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **API Latency** | Same as native |
| **Cost Accuracy** | 100% accurate |
| **Error Messages** | Provider-agnostic |
| **Switching Time** | <100ms |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Both providers tested with real API calls
- [ ] Pricing verified against official docs
- [ ] Documentation updated
- [ ] Example projects for each provider

---

## Success Metrics

- **Adoption**: 10+ users testing new providers
- **Accuracy**: 100% cost calculation accuracy
- **Compatibility**: Works with all major models
- **Reliability**: No provider-specific failures

---

*Draft: April 26, 2026*
