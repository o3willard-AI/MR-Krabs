# MR-Krabs Architecture

**Config-driven, judge-gated, PI-backed multi-tier coding agent.**

## Pipeline

```
Tier Loop: L0 → L1 → L2 → Principal
  ┌─ Circuit Breaker gate → FailUp check
  │
  │  Retry Loop (per tier):
  │    PI subprocess → Tool execution → Judge evaluation
  │         ↑                              │
  │         └── Coaching feedback ─────────┘ (if reject)
  │
  │  Accepted → return SUCCESS
  │  Retries exhausted → FailureAction → escalate
  │
  Principal reached → return escalation_context to caller
```

## Tier Hierarchy

| Tier | Model | Runtime | Cost | Role |
|------|-------|---------|------|------|
| L0-Coder | qwen3-coder-30b | PI on .23 | Free | ~75% success |
| L1-Coder | deepseek-v4-flash | PI via OpenRouter | Cloud | First escalation |
| L2-Coder | mimo-v2.5 | PI via OpenRouter | Cloud | Second escalation |
| Principal | — | Calling agent | Your sub | Final fallback |

## PI Coder Backend

Each coder tier executes through `pi --mode json`. Config:

```yaml
pi_models:
  l0-coder: litellm/mrk-coder-l0
  l1-coder: openrouter/deepseek/deepseek-v4-flash
  l2-coder: openrouter/xiaomi/mimo-v2.5

pi_timeouts:
  l0-coder: 2400
  l1-coder: 1200
  l2-coder: 1200
```

Execution: spawns PI → parses JSONL events → extracts tool calls → writes files → feeds contents to Judge.

When PI is absent, falls back to raw LLM via ProviderRouter.

## Judge System

| Property | Value |
|----------|-------|
| Model | claude-distilled-35b (.21) |
| Temperature | 0.1 |
| Threshold | 0.7 |
| Rubric | Anchored 0.0–1.0 |

Coaching reply structure (on rejection): what was done well → what's wrong → why → how to fix → verify.

## Principal Agent

Returns structured result with full escalation context including best output and file contents so the calling agent can continue.

## Configuration-Driven

No hardcoded models or tiers. `~/.mrkrabs/config.yaml` defines everything.

See [MODEL_CONFIG.md](MODEL_CONFIG.md) for full reference.
