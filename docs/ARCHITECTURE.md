# MR-Krabs Architecture

**Config-driven, judge-gated, multi-tier coding agent.**

## Recommended Infrastructure

**MR-Krabs is designed to work with [llama.cpp](https://github.com/ggerganov/llama.cpp).**
llama.cpp is the only recommended model server — it handles tool-call formats,
stop-token behavior, and reasoning-model content extraction correctly. We
strongly advise against LM Studio (known jinja template injection bugs),
Ollama (tool-call inconsistencies), and vLLM (stop-token behaviour differences).

## Pipeline

```
Tier Loop: L0 → L1 → L2 → Principal
  ┌─ Circuit Breaker gate → FailUp check
  │
  │  Retry Loop (per tier):
  │    OpenCode subprocess → Tool execution → Judge evaluation
  │         ↑                              │
  │         └── Coaching feedback ─────────┘ (if reject)
  │
  │  Accepted → return SUCCESS
  │  Retries exhausted → FailureAction → escalate
  │
  Principal reached → return escalation_context to caller
```

## Coder Backend

The default coder sub-agent is **OpenCode CLI** (`opencode run`). Each coder tier
spawns an OpenCode process that writes files directly to disk, then the orchestrator
reads them back for Judge evaluation. OpenCode is the recommended backend because it:

- Works reliably with llama.cpp (no jinja template issues)
- Handles multi-file tasks with native tool use (write, bash, read, edit)
- Produces verifiable output — files on disk, not parsed from model text

**PI Coding Agent** is available as a fallback. Configure `pi_models` in your config
to use PI for specific tiers. When a tier has both `opencode_models` and `pi_models`
entries, OpenCode takes priority.

```yaml
# Default: OpenCode for all coder tiers
opencode_models:
  l0-coder: llama_cpp_23/ornith-1.0-35b
  l1-coder: openrouter/deepseek/deepseek-v4-flash
  l2-coder: openrouter/xiaomi/mimo-v2.5

opencode_timeouts:
  l0-coder: 2400
  l1-coder: 1200
  l2-coder: 1200

# Fallback: PI for specific tiers
pi_models:
  l0-coder: litellm/mrk-coder-l0
```

Execution: spawns OpenCode → writes files to `project_root` → orchestrator reads
files → feeds contents to Judge.

When neither OpenCode nor PI is configured, falls back to raw LLM via ProviderRouter.

## Tier Hierarchy

**Example deployment.** Configure your own in `~/.mrkrabs/config.yaml`.
See [MODEL_CONFIG.md](MODEL_CONFIG.md).

| Tier | Example | Runtime | Cost | Role |
|------|---------|---------|------|------|
| L0-Coder | 30B MoE on llama.cpp | OpenCode on local GPU | Free | ~75% success |
| L1-Coder | Fast cloud model | OpenCode via OpenRouter | Cloud | First escalation |
| L2-Coder | Premium cloud model | OpenCode via OpenRouter | Cloud | Second escalation |
| Principal | — | Calling agent | Your sub | Final fallback |

## Judge System

| Property | Value |
|----------|-------|
| Class | Reasoning model recommended |
| Temperature | 0.1 |
| Threshold | 0.7 (configurable) |
| Rubric | Anchored 0.0–1.0 |

Coaching reply structure (on rejection): what was done well → what's wrong → why → how to fix → verify.

## Principal Agent

Returns structured result with full escalation context including best output and file contents so the calling agent can continue.

## Configuration-Driven

No hardcoded models or tiers. `~/.mrkrabs/config.yaml` defines everything.

See [MODEL_CONFIG.md](MODEL_CONFIG.md) for full reference.
