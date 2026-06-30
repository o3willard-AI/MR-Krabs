# Model Configuration Examples

These are **examples** — not defaults. MR‑Krabs ships with no hardcoded
models. Copy one of these as a starting point and adapt it to your setup.

> **Important:** MR-Krabs is designed to work with
> [llama.cpp](https://github.com/ggerganov/llama.cpp). All examples below use
> llama.cpp as the model server. Other backends (LM Studio, Ollama, vLLM) are
> **not recommended** — they have known issues with tool-call formats, jinja
> template injection, and inconsistent stop-token behavior.

---

## Example 1: Hybrid llama.cpp + OpenRouter (Recommended)

Our .21/.23 setup. Local 30B+ models on llama.cpp for coding, OpenRouter for
the Judge and cloud fallbacks. This is the configuration we use in production.

```yaml
version: "1.0"

providers:
  llama_cpp_21:
    type: openai_compatible
    base_url: http://192.168.101.21:8080/v1
    timeout: 1800
  llama_cpp_23:
    type: openai_compatible
    base_url: http://192.168.101.23:8080/v1
    timeout: 1800
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    timeout: 300

models:
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]

  l0-planner:
    provider: llama_cpp_21
    model: claude-distilled-35b
    temperature: 0.0
    max_tokens: 16384
    roles: [planner]
    tools: [file_read]

  l1-planner:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]
    tools: [file_read]

  orchestrator:
    provider: llama_cpp_23
    model: qwen3-coder-30b
    temperature: 0.0
    max_tokens: 32768
    roles: [orchestrator]

  l0-coder:
    provider: llama_cpp_23
    model: ornith-1.0-35b
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]
    tools: [file_write, file_read]

  l1-coder:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  l2-coder:
    provider: openrouter
    model: anthropic/claude-haiku-4.5
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  principal:
    provider: ""
    model: ""
    roles: [principal]

# OpenCode coder backend (default)
opencode_models:
  l0-coder: llama_cpp_23/ornith-1.0-35b
  l1-coder: openrouter/deepseek/deepseek-v4-flash
  l2-coder: openrouter/xiaomi/mimo-v2.5

opencode_timeouts:
  l0-coder: 2400
  l1-coder: 1200
  l2-coder: 1200

workflows:
  code:
    tiers: [l0-coder, l1-coder, l2-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
  plan:
    tiers: [l0-planner, l1-planner, principal]
    max_retries_per_tier: 3
    judge_model: judge

tier_failure_actions:
  l0-coder: log_only
  l1-coder: notify_and_escalate
  l2-coder: notify_and_wait
  l0-planner: log_only
  l1-planner: notify_and_escalate

budget:
  daily_limit_usd: 10.00
  budget_awareness: true
  tier_thresholds:
    0.8: l2-coder
    0.5: l1-coder
    0.3: l0-coder
```

---

## Example 2: Budget 12 GB (Single-GPU llama.cpp)

Single-GPU build (e.g., RTX 3060 12GB) using a 9B–12B model quantized at
Q4_K_M on llama.cpp. Judge scoring will be less calibrated than a cloud
reasoning model — expect more false accepts. Add an OpenRouter Judge if
you have API access.

```yaml
version: "1.0"

providers:
  llama_cpp_local:
    type: openai_compatible
    base_url: http://192.168.101.17:8080/v1
    timeout: 1800

models:
  judge:
    provider: llama_cpp_local
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 2048
    roles: [judge]

  l0-planner:
    provider: llama_cpp_local
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [planner]
    tools: [file_read]

  orchestrator:
    provider: llama_cpp_local
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [orchestrator]

  l0-coder:
    provider: llama_cpp_local
    model: qwen2.5-coder-3b-instruct
    temperature: 0.0
    max_tokens: 4096
    roles: [coder]
    tools: [file_write, file_read]

  principal:
    roles: [principal]

opencode_models:
  l0-coder: llama_cpp_local/qwen2.5-coder-3b-instruct

opencode_timeouts:
  l0-coder: 1200

workflows:
  code:
    tiers: [l0-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
  plan:
    tiers: [l0-planner, principal]
    max_retries_per_tier: 3
    judge_model: judge
```

**Limitations of this build:**
- Small models max out at ~400 lines per build, ~75 lines per file
- Judge calibration less reliable than cloud reasoning models
- 3B coder handles single-file tasks; multi-file builds should escalate to Principal
- No cloud fallback — Principal is the only escalation path

---

## Example 3: Full Cloud (All via OpenRouter)

No local GPUs needed. Pay per token. Best for evaluation and prototyping.
Use a local llama.cpp instance for the coder tier once you move to production.

```yaml
version: "1.0"

providers:
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    timeout: 300

models:
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]

  l0-planner:
    provider: openrouter
    model: google/gemini-2.5-pro
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]

  l1-planner:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]

  orchestrator:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 32768
    roles: [orchestrator]

  l0-coder:
    provider: openrouter
    model: x-ai/grok-4.1-fast
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  l1-coder:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  l2-coder:
    provider: openrouter
    model: anthropic/claude-haiku-4.5
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  principal:
    roles: [principal]

opencode_models:
  l0-coder: openrouter/x-ai/grok-4.1-fast
  l1-coder: openrouter/google/gemini-2.5-flash
  l2-coder: openrouter/anthropic/claude-haiku-4.5

opencode_timeouts:
  l0-coder: 600
  l1-coder: 600
  l2-coder: 600

workflows:
  code:
    tiers: [l0-coder, l1-coder, l2-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
  plan:
    tiers: [l0-planner, l1-planner, principal]
    max_retries_per_tier: 3
    judge_model: judge
```

---

## Model Server Comparison

| Backend | Tool Calls | Stop Tokens | Reasoning Models | Recommended? |
|---------|:----------:|:-----------:|:----------------:|:------------:|
| **llama.cpp** | ✅ Reliable | ✅ Correct | ✅ Works | **Yes** |
| LM Studio | ❌ Jinja bugs | ⚠️ Mixed | ❌ Breaks | No |
| Ollama | ⚠️ Inconsistent | ⚠️ Mixed | ⚠️ Partial | No |
| vLLM | ⚠️ Format varies | ❌ Ignored | ⚠️ Partial | No |

## Role Reference

| Role | Purpose | Suggested Class |
|---|---|---|
| `judge` | Quality gate — scores all outputs | Reasoning model (R1, Sonnet, o4-mini) |
| `l0-planner` | Task decomposition (first try) | 30B+ MoE on llama.cpp, Gemini 2.5 Pro |
| `l1-planner` | Fallback planner | Gemini 2.5 Flash, Claude Haiku |
| `l2-planner` | Last-resort planner | Claude Sonnet 4.6 |
| `orchestrator` | Task routing & coordination | 30B MoE on llama.cpp, Gemini Flash |
| `l0-coder` | Code generation (first try) | 30B MoE on llama.cpp (Ornith, Qwen3-Coder) |
| `l1-coder` | Fallback coder | Gemini Flash, Claude Haiku |
| `l2-coder` | Last-resort coder | Claude Sonnet 4.6 |
| `principal` | Returns to caller agent | (your agent — Hermes, Claude Code, etc.) |
