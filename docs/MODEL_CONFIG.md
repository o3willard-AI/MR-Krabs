# Model Configuration Examples

These are **examples** — not defaults. MR‑Krabs ships with no hardcoded
models. Copy one of these as a starting point and adapt it to your setup.

---

## Example 1: Hybrid High-End (24 GB GPUs)

Our .21/.23 setup. Local 30B+ MoE models for coding and planning,
OpenRouter for the Judge and cloud fallbacks.

```yaml
version: "1.0"

providers:
  litellm:
    type: openai_compatible
    base_url: http://192.168.101.42:4000/v1
    api_key_env: LITELLM_MASTER_KEY
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
    provider: litellm
    model: mrk-planner-l0           # claude-distilled 35B on .21
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
    provider: litellm
    model: mrk-orchestrator         # qwen30-coder 30B on .23
    temperature: 0.0
    max_tokens: 32768
    roles: [orchestrator]

  l0-coder:
    provider: litellm
    model: mrk-coder-l0             # qwen30-coder 30B on .23
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

## Example 2: Budget 12 GB (All Local via LM Studio)

Single-GPU build using Sushi 9B as the workhorse and Qwen2.5-Coder-3B
for code generation. Judge scoring will be less calibrated than a cloud
reasoning model — expect more false accepts. Add an OpenRouter fallback
for the Judge if you have API access.

```yaml
version: "1.0"

providers:
  lmstudio_17:
    type: openai_compatible
    base_url: http://192.168.101.17:1234/v1
    timeout: 1800

models:
  judge:
    provider: lmstudio_17
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 2048
    roles: [judge]
    profile: sushi-9b

  l0-planner:
    provider: lmstudio_17
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [planner]
    tools: [file_read]
    profile: sushi-9b

  orchestrator:
    provider: lmstudio_17
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [orchestrator]
    profile: sushi-9b

  l0-coder:
    provider: lmstudio_17
    model: qwen2.5-coder-3b-instruct
    temperature: 0.0
    max_tokens: 4096
    roles: [coder]
    tools: [file_write, file_read]

  principal:
    roles: [principal]

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
- Sushi maxes out at ~400 lines per build, ~75 lines per file
- Sushi Judge calibration: 0.95 for correct code, 0.1 for SQL injection — passable but not as reliable as DeepSeek R1
- 3B coder can handle single-file tasks; multi-file builds should escalate to Principal
- No cloud fallback — Principal is the only escalation path

---

## Example 3: Full Cloud (All via OpenRouter)

No local GPUs needed. Pay per token. Best for evaluation and prototyping.

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

## Role Reference

| Role | Purpose | Suggested Class |
|---|---|---|
| `judge` | Quality gate — scores all outputs | Reasoning model (R1, Sonnet, o4-mini) |
| `l0-planner` | Task decomposition (first try) | 30B+ MoE local, Gemini 2.5 Pro |
| `l1-planner` | Fallback planner | Gemini 2.5 Flash, Claude Haiku |
| `l2-planner` | Last-resort planner | Claude Sonnet 4.6 |
| `orchestrator` | Task routing & coordination | 30B MoE local, Gemini Flash |
| `l0-coder` | Code generation (first try) | 30B MoE local, Grok Fast |
| `l1-coder` | Fallback coder | Gemini Flash, Claude Haiku |
| `l2-coder` | Last-resort coder | Claude Sonnet 4.6 |
| `principal` | Returns to caller agent | (your agent — Hermes, Claude Code, etc.) |
