# MR-Krabs Coding Tier Configuration — v0.2.0

**Date:** May 2026
**Principle:** Optimize for coding capability per dollar. Start with cheapest local models, escalate through OpenRouter's best coding models on failure.

---

## Tier Summary

| Tier | Role | Model | Provider | Est. Cost/1M tok | Strengths |
|------|------|-------|----------|-----------------|-----------|
| **L0-Planner** | Task decomposition | `qwen/qwen3.5-27b` | LM Studio (local) | $0 | Strong reasoning, free |
| **L0-Reviewer** | Code review | `qwen/qwen3.5-27b` | LM Studio (local) | $0 | Good at finding bugs |
| **L0-Coder** | First-pass implementation | `qwen/qwen3.5-9b` | LM Studio (local) | $0 | Fast, free, surprisingly capable at simple tasks |
| **L1-Coder** | Escalated implementation | `deepseek/deepseek-v3.2` | OpenRouter | $0.27 / $1.10 | Best-in-class open-weight coding, 128K ctx |
| **L2-Coder** | Complex implementation | `anthropic/claude-sonnet-4` | OpenRouter | $3 / $15 | Industry-leading coding, tool use |
| **L3-Coder** | Critical/blocked tasks | `anthropic/claude-opus-4.7` | OpenRouter | $15 / $75 | Maximum capability, complex reasoning |
| **L3-Architect** | Architecture & design | `anthropic/claude-opus-4.7` | OpenRouter | $15 / $75 | System design, multi-file refactors |

---

## Rationale Per Tier

### L0 — Local (Zero Cost)

- **`qwen/qwen3.5-27b`** (Planner/Reviewer): 27B parameters, strong reasoning benchmarks, good at decomposition and finding bugs. Runs on LM Studio at `.21`.
- **`qwen/qwen3.5-9b`** (Coder): 9B parameters, fast, handles simple well-specified coding tasks. Our earlier testing showed 70% completion rate with correct code at 80 tok/s. Best for mechanical, single-file edits.

**Selection logic:** L0-Coder tries first. If it times out or produces broken code, escalate to L1.

### L1 — DeepSeek (Best Value Coding)

- **`deepseek/deepseek-v3.2`**: Latest DeepSeek release, top-tier open-weight coding model. 128K context window, strong on HumanEval and SWE-bench. At $0.27/$1.10 per 1M tokens, it's the best coding-per-dollar on OpenRouter.

### L2 — Claude Sonnet (Production Coding)

- **`anthropic/claude-sonnet-4`**: Industry standard for coding agents. Excellent tool use, handles complex multi-file refactors, strong type understanding. $3/$15 per 1M.

### L3 — Claude Opus (Maximum Capability)

- **`anthropic/claude-opus-4.7`**: Latest Opus. For tasks where correctness matters more than cost — critical production bugs, architectural decisions, security-sensitive code.

---

## Cost Optimization Strategy

With this tier configuration, a typical coding task flows:

1. **L0-Coder (free)** → attempts task. 70% chance of success for simple tasks.
2. **L1-Coder ($0.0003/req)** → DeepSeek handles most remaining cases. Expected cost: ~$0.0003 per escalation.
3. **L2-Coder ($0.015/req)** → Sonnet for complex multi-file work. Rarely needed.
4. **L3-Coder ($0.075/req)** → Opus for critical failures. Reserved for <1% of tasks.

**Expected blended cost:** ~$0.001 per successful coding task (mostly L0 + occasional L1).

---

## Configuration

```python
MODELS = {
    "L0-Planner": {
        "provider": "lmstudio",
        "model": "qwen/qwen3.5-27b",
        "base_url": "http://192.168.101.21:1234/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
    "L0-Reviewer": {
        "provider": "lmstudio",
        "model": "qwen/qwen3.5-27b",
        "base_url": "http://192.168.101.21:1234/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
    "L0-Coder": {
        "provider": "lmstudio",
        "model": "qwen/qwen3.5-9b",
        "base_url": "http://192.168.101.21:1234/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L1-Coder": {
        "provider": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L2-Coder": {
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L3-Coder": {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.7",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L3-Architect": {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.7",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
}
```
