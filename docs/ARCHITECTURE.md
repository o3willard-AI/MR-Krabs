# MR-Krabs v0.2.0 — Judge-Based Escalation Architecture

**Status:** Implemented | **Tests:** 884 passing | **Last updated:** 2026-05-20

## Overview

MR-Krabs is a cost-optimized multi-tier AI orchestrator. It runs coding tasks through
a quality-gated escalation pipeline: start with a free local model, escalate to
progressively more capable cloud models only when quality demands it, and ultimately
return control to the user's own agent if all tiers are exhausted.

The system replaces budget-driven escalation with **judge-driven quality gates**.
Cost is tracked but never blocks execution — it's an observer, not a gatekeeper.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        execute_with_judge(task, context)            │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                  Tier Loop: L0 → L1 → L2 → Principal         │  │
│  │                                                               │  │
│  │   ┌─ Circuit Breaker gate ─┐                                  │  │
│  │   └─ FailUp check ─────────┘                                  │  │
│  │                                                               │  │
│  │   ┌─────── Retry Loop (per tier) ────────────────────────┐    │  │
│  │   │                                                       │    │  │
│  │   │  LLM Call ──→ Tool Execution ──→ Judge Evaluation     │    │  │
│  │   │       ↑                              │                │    │  │
│  │   │       └── Feedback (coaching reply) ─┘ (if rejected)  │    │  │
│  │   │                                                       │    │  │
│  │   └─── Accepted → return SUCCESS ─────────────────────────┘    │  │
│  │                                                               │  │
│  │   Retries exhausted → FailureAction → escalate to next tier   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Principal Agent reached → return escalation_context to caller      │
│                                                                     │
│  [FailNow] — skip to specified tier, one shot, no judge             │
│  [FailUp]  — abort current tier, bump up one level                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Tier Hierarchy

| Tier | Model | Provider | Cost | Role |
|------|-------|----------|------|------|
| L0-Coder | qwen3.5-397b-a17b | OpenRouter (free) | Free | First attempt |
| L1-Coder | minimax-m2.7 | OpenRouter | ~$0.0008/1K tok | First escalation |
| L2-Coder | grok-4.3 | OpenRouter | ~$0.008/1K tok | Second escalation |
| Principal | *user's own agent* | — | User's subscription | Final fallback |

**L3 is optional.** Users who want a dedicated cloud tier between L2 and Principal can
add L3-Coder (claude-sonnet-4.6) to their tiers list:

```python
# Default (L2 → Principal):
tiers = ["L0-Coder", "L1-Coder", "L2-Coder", "Principal"]

# With optional L3 (L2 → L3 → Principal):
tiers = ["L0-Coder", "L1-Coder", "L2-Coder", "L3-Coder", "Principal"]
```

### Principal Agent

The Principal Agent is the user's own agent — Hermes, Claude Code, Gemini CLI,
opencode, or any CLI coding agent. MR-Krabs cannot see or manage the Principal
Agent's LLM. When escalation reaches Principal, the orchestrator returns a
structured result instead of making an API call:

```python
{
    "success": False,
    "escalated_to_principal": True,
    "tier_used": "Principal",
    "escalation_context": {
        "task": "Write a bloom filter...",
        "tiers_attempted": ["L0-Coder", "L1-Coder", "L2-Coder"],
        "retries_per_tier": {"L0-Coder": 3, "L1-Coder": 2, "L2-Coder": 0},
        "last_feedback": "The sort function doesn't handle None inputs..."
    },
    "message": "Task escalated to Principal Agent. MR-Krabs attempted 3 tier(s)..."
}
```

This design ensures:
- The user's subscription credits get used as the final safety net
- The Principal Agent has full conversation context for better decisions
- No cost to MR-Krabs for the highest-tier call

## Judge System

The Judge is the quality gate for the entire pipeline. It evaluates agent outputs
and produces scored verdicts with coaching feedback.

**Key design decisions (research-backed):**

| Decision | Rationale | Source |
|----------|-----------|--------|
| Judge is a dedicated model, not a tier agent | Reliability ceiling — judge quality determines system quality | — |
| Judge always uses a reasoning model (Claude Sonnet) | Reasoning models produce more calibrated scores and fewer hallucinations | LMSYS MT-Bench |
| Judge prompt uses anchored rubric (0.0-0.2 crash → 0.9-1.0 perfect) | Eliminates score drift across calls | G-Eval |
| Judge explains before scoring (impartial judge framing) | Forces reasoning, reduces pattern-matching | LMSYS |
| Judge uses verbosity bias warning | Prevents longer-but-wrong outputs from scoring higher | LMSYS |
| Judge produces coaching replies on rejection | Gives the retry agent the best possible chance to fix | — |

### Verdict Structure

```python
@dataclass
class Verdict:
    accepted: bool          # score >= acceptance_threshold (default 0.7)
    score: float            # 0.0 - 1.0
    critique: str           # coaching reply with 5-point structure
    checks_passed: list[str]
    checks_failed: list[str]
```

### Coaching Reply (5-Point Structure)

When the Judge rejects output (score < 0.7), the critique follows a mandatory
5-point coaching structure designed to maximize the agent's chance of success on
the next retry:

1. **What was done well** — reinforce correct parts so they are kept
2. **What specific thing is wrong** — name the file, function, or line
3. **Why it's wrong** — what requirement does it violate?
4. **How to fix it** — concrete code change, e.g., "change line X from Y to Z"
5. **What to verify after fixing** — how to check the fix works

Example coaching reply: *"The sort function doesn't handle None inputs — add
`if lst is None: return []` at the top of the function and verify with
`test_sort_none_input()`."*

See [JUDGE.md](./JUDGE.md) for the full prompt template, model selection
rationale, and criteria configuration.

## Agent System Prompt

Each coding agent (all tiers) receives a system prompt based on SotA patterns
from Aider, SWE-agent, and CodeAct:

- **Role:** Expert software developer
- **Tools:** `file_read()` and `file_write()` with format examples
- **Rules:** Read before writing, match conventions, write complete code,
  flag ambiguous tasks, handle edge cases, verify changes
- **Anti-hallucination:** "If the task is ambiguous, ask — do not guess"

Template: `docs/workflow/templates/agent-system-prompt.md`

## Escalation Pipeline

The core method is `LLMOrchestrator.execute_with_judge()`:

```
for tier in tiers:
    → Circuit breaker gate (skip blocked tiers)
    → FailUp check (abort tier and bump up if active)
    → Retry loop (max_retries_per_tier attempts):
        → LLM call with agent system prompt + feedback from prior judge
        → Tool execution (parse file_read/file_write from output)
        → Judge.evaluate(task, output) → Verdict
        → Cost tracking (observer only, never blocks)
        → If accepted → return SUCCESS
        → If rejected → save critique as feedback for next retry
    → Retries exhausted → FailureAction → escalate to next tier

→ All tiers exhausted → total failure
```

### Default Tiers

```python
["L0-Coder", "L1-Coder", "L2-Coder", "Principal"]
```

### Retry Per Tier

Default: 3 retries per tier. Configurable via `max_retries_per_tier`.

### Feedback Injection

On retry N+1, the Judge's critique is injected into the user prompt:
```
## Previous Attempt Feedback
The prior output was rejected by the quality judge.
Critique: {coaching reply}
Please fix these issues and try again.
```

## Failure Actions

Per-tier configurable actions when all retries are exhausted:

| Action | Behavior | Default Tiers |
|--------|----------|---------------|
| `LOG_ONLY` | Log the failure, continue to next tier | L0 |
| `NOTIFY_AND_ESCALATE` | Send notification, continue to next tier | L1 |
| `NOTIFY_AND_WAIT` | Send notification, wait for human confirmation | L2 |

Human confirmation for `NOTIFY_AND_WAIT`:
- Writes `~/.mrkrabs/pending/<task_id>.json`
- Polls for `{confirmed: true}` or `{confirmed: false, reason: "..."}`
- 15-minute timeout → auto-abort

## FailNow / FailUp Signals

Emergency controls to bypass the normal escalation flow:

| Signal | Effect | Trigger |
|--------|--------|---------|
| `FailNow` | Skip directly to specified tier, one shot, no judge | `set_fail_now("L1-Coder")` or `MRKRABS_FAIL_NOW` env var |
| `FailUp` | Abort current tier, bump up one level | `set_fail_up()` or `MRKRABS_FAIL_UP` env var |

Both auto-clear after use. The fail-now path also checks a mesh signal file for
remote triggering.

## Cost Tracking

`CostTracker` is an **observer only** — it tracks spend per task, per tier, per
session, but never blocks execution. Budget is communicated in notifications and
available for reporting, but cost doesn't gate the pipeline.

```
CostTracker.record() — records spend, never raises
CostTracker.get_summary() — returns {daily_total, budget_remaining, ...}
```

## Model Configuration

All models are defined in `src/core/model_config.py`:

```python
MODELS = {
    "Judge": {  # dedicated — never a tier agent
        "model": "anthropic/claude-sonnet-4.6",
        "temperature": 0.1,  # low temp for consistent evaluations
        "role": "judge",
    },
    "L0-Coder": {"provider": "lmstudio", "model": "qwen/qwen3-coder-30b", ...},
    "L1-Coder": {"provider": "openrouter", "model": "x-ai/grok-4.3", ...},
    "L2-Coder": {"provider": "openrouter", "model": "minimax/minimax-m2.7", ...},
    "Principal": {"role": "principal"},  # no provider — returns to caller
    # L3-Coder and L3-Architect available as optional cloud tiers
}
```

## Key Files

| File | Purpose |
|------|---------|
| `src/core/orchestrator.py` | `execute_with_judge()` — main escalation pipeline |
| `src/core/judge.py` | Judge class, verdict evaluation, coaching prompt |
| `src/core/judge_criteria.py` | Default criteria + task type detection |
| `src/core/model_config.py` | MODELS dict — all tiers + Judge + Principal |
| `src/core/failure_action.py` | FailureAction enum (LOG_ONLY/NOTIFY_AND_ESCALATE/NOTIFY_AND_WAIT) |
| `src/core/fail_now.py` | FailNow/FailUp signals (env var + function + mesh) |
| `src/core/notify.py` | Pluggable notifiers (Mesh, Telegram, fallback) |
| `src/core/human_gate.py` | Pending file + human confirmation for NOTIFY_AND_WAIT |
| `src/core/cost.py` | CostTracker — observer-only spend tracking |
| `src/core/circuit_breaker.py` | Per-model circuit breaker |
| `docs/workflow/templates/agent-system-prompt.md` | Agent system prompt template |
| `docs/JUDGE.md` | Judge best practices, prompt design, coaching reply spec |
