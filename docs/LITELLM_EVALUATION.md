# LiteLLM Evaluation

**Status**: Evaluated / Deferred
**Created**: 2026-04-03

---

## What is LiteLLM?

[LiteLLM](https://github.com/BerriAI/litellm) is an open-source library that provides a unified interface to 100+ LLM providers. It already handles:
- Provider-specific API formats and authentication
- Cost tracking with up-to-date pricing
- Fallback/retry logic across providers
- Streaming support
- Token counting

## Analysis

### Pros
- **100+ providers supported out of the box** — far more than we could maintain
- **Active maintenance** — large community, frequent updates
- **Cost tracking built-in** — eliminates need for our own pricing tables
- **Standard OpenAI interface** — drop-in replacement for OpenAI SDK
- **Fallback support** — automatic provider failover

### Cons
- **Additional dependency** — increases install size and complexity
- **Version drift** — pricing and provider support changes with LiteLLM releases
- **Less control** — we can't customize provider-specific behavior as easily
- **Potential conflicts** — LiteLLM has its own retry/fallback logic that may conflict with ours
- **Not needed for v1** — we only support OpenRouter and LM Studio initially

## Decision: Defer to Future

**Rationale**: The v1 library only needs to support OpenRouter (OpenAI-compatible API) and LM Studio (also OpenAI-compatible). Both work with standard HTTP calls. LiteLLM's value proposition becomes compelling only when:
1. We need to support 10+ providers with different API formats
2. We need automatic provider failover
3. We need real-time cost tracking across providers

None of these are v1 requirements.

## How to Adopt Later

If adopted, LiteLLM should be an **optional dependency**:

```toml
[project.optional-dependencies]
litellm = ["litellm>=1.0.0"]
```

Users would install with: `pip install cost-orchestrator[litellm]`

The integration would look like:

```python
# With LiteLLM
import litellm
from cost_orchestrator import CostTracker

# LiteLLM handles provider routing
response = litellm.completion(model="openrouter/qwen/qwen3.5-397b-a17b", messages=messages)

# We still handle budget and escalation
cost = litellm.completion_cost(response)
tracker.record(task_id, tier, model, tokens, duration)
```

## Alternative: Use LiteLLM's Pricing Data Only

A middle ground: use LiteLLM's `model_cost` dictionary for pricing data without adopting the full library. This gives us accurate pricing without the dependency overhead.

```python
# Extract pricing from LiteLLM
from litellm import model_cost

OUR_PRICING = {
    model: {
        "prompt": cost["input_cost_per_token"],
        "completion": cost["output_cost_per_token"],
    }
    for model, cost in model_cost.items()
    if "openrouter" in model or "anthropic" in model
}
```

This could be done as a build-time script that generates our pricing tables from LiteLLM's data.
