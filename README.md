<div align="center">

# MR-Krabs

**Quality-gated multi-tier AI orchestration with judge-based escalation.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-884%20passing-green.svg)](https://github.com/o3willard-AI/MR-Krabs)

</div>

---

MR-Krabs runs coding tasks through a quality-gated escalation pipeline: start with
a free local model, escalate to progressively more capable cloud models only when
the **Judge** determines quality is insufficient, and ultimately return control to
your own agent if all tiers are exhausted.

**Cost is tracked but never blocks execution** — it's an observer, not a gatekeeper.

## Quickstart

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

```python
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")
print(result.output)        # The code
print(f"Cost: ${result.cost:.4f}")  # $0.0000 (used free L0)
print(f"Tier: {result.tier}")       # L0-Coder
```

## How It Works

```
L0 (free local) → L1 (cheap cloud) → L2 (capable cloud) → Principal Agent (you)
                   ↑ escalated only if judge rejects              ↑ your own agent,
                   ↑ quality at current tier                      ↑ your subscription
```

1. **Try L0** — local model, free, handles ~87% of tasks
2. **Judge evaluates** — dedicated reasoning model scores output quality
3. **If rejected** — coaching feedback injected, agent retries (up to 3x per tier)
4. **If exhausted** — escalate to next tier, with configurable failure actions
5. **If all tiers fail** — returns control to your Principal Agent with full context

### The Judge

The Judge is a dedicated reasoning model (Claude Sonnet) — NOT a tier agent.
It evaluates every output with an anchored rubric and produces **coaching replies**
that tell the retry agent exactly what to fix, where, and how.

See [docs/JUDGE.md](docs/JUDGE.md) for the full prompt design, coaching reply structure,
and model selection rationale.

### Failure Actions

| Tier | On Exhaustion |
|------|--------------|
| L0 | Log and escalate silently |
| L1 | Notify and escalate |
| L2 | Notify and wait for human confirmation |

### Principal Agent

The final escalation tier is your own agent (Hermes, Claude Code, Gemini CLI, etc.).
MR-Krabs returns a structured result with full escalation context — task, tiers
attempted, retry counts, last judge feedback — so you can pick up where it left off.

L3 (Claude Sonnet via OpenRouter) is available as an optional cloud tier between
L2 and Principal.

## Configuration

```python
MODELS = {
    "Judge": {"model": "anthropic/claude-sonnet-4.6", "role": "judge"},
    "L0-Coder": {"provider": "lmstudio", "model": "qwen/qwen3-coder-30b"},
    "L1-Coder": {"provider": "openrouter", "model": "x-ai/grok-4.3"},
    "L2-Coder": {"provider": "openrouter", "model": "minimax/minimax-m2.7"},
    "Principal": {"role": "principal"},  # returns to caller
}
```

Default escalation path: `["L0-Coder", "L1-Coder", "L2-Coder", "Principal"]`

## API

```python
from cost_orchestrator import ask, AskResult

# Simple usage
result: AskResult = ask("Write a function")
print(result.output, result.cost, result.tier)

# With judge-based escalation
from src.core.orchestrator import LLMOrchestrator
orch = LLMOrchestrator()
result = orch.execute_with_judge(
    task_id="my-task",
    context={"task_spec": "Write a bloom filter in Python"},
    tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
    max_retries_per_tier=3,
)

if result.get("escalated_to_principal"):
    # MR-Krabs couldn't solve it — handle it yourself
    ctx = result["escalation_context"]
    print(f"Tried {ctx['tiers_attempted']} — last feedback: {ctx['last_feedback']}")
```

## Emergency Controls

```python
# Skip directly to a tier, one shot, no judge
set_fail_now("L1-Coder")
result = orch.execute_with_judge(...)

# Abort current tier, bump up one level
set_fail_up()
```

## Architecture

Full documentation in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT
