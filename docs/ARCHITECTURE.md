# MR-Krabs v0.2.0 — Judge-Based Escalation Architecture

**Status:** Design sketch — not yet implemented
**Replaces:** Current hardcoded L0→L1→L2→L3 budget-driven loop in `_ask_with_escalation()`

## Problem

Current escalation is prescriptive and budget-obsessed:
- Only escalates on HTTP failure (connection refused, 4xx, 5xx) — never on *quality*
- Budget acts as a kill switch, not a tracking tool
- No human-in-the-loop when costs rise
- No way to say "screw the budget, use the best model and finish this"

## New Model

```
┌──────────────────────────────────────────────────────────┐
│                      ask(prompt)                         │
│                          │                               │
│  ┌───────────────────────▼────────────────────────────┐  │
│  │              for tier in [L0, L1, L2, L3]:         │  │
│  │                 │                                  │  │
│  │    ┌────────────▼────────────┐                     │  │
│  │    │  for retry in 1..N:    │  ← configurable     │  │
│  │    │    output = tier.call( │    (default 3)       │  │
│  │    │      prompt, feedback) │                     │  │
│  │    │    verdict = JUDGE(    │  ← L2 by default     │  │
│  │    │      task, output)     │                     │  │
│  │    │    if verdict.accepted │                     │  │
│  │    │      → return SUCCESS  │                     │  │
│  │    │    feedback = verdict. │                     │  │
│  │    │      critique          │                     │  │
│  │    └────────────────────────┘                     │  │
│  │                                                    │  │
│  │    # All retries exhausted — failure state          │  │
│  │    action = tier_config.on_failure                  │  │
│  │    if action == LOG_ONLY:                           │  │
│  │      log(spend, failure)  → continue to next tier   │  │
│  │    elif action == NOTIFY_AND_ESCALATE:              │  │
│  │      notify(spend, failure, next_tier)              │  │
│  │      → continue to next tier                        │  │
│  │    elif action == NOTIFY_AND_WAIT:                   │  │
│  │      notify(spend, failure, next_tier)              │  │
│  │      WAIT for human confirmation                     │  │
│  │      if not confirmed → return ABORTED              │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [FAIL NOW SIGNAL] — at any point, human or agent        │
│  can trigger: skip to specified tier, ignore budget      │
└──────────────────────────────────────────────────────────┘
```

## Components

### 1. Judge (`judge.py`)

LLM-powered quality evaluator. Default: L2 model (claude-sonnet).

```python
@dataclass
class Verdict:
    accepted: bool
    score: float          # 0.0 - 1.0
    critique: str         # specific, actionable feedback
    checks_passed: list[str]
    checks_failed: list[str]

class Judge:
    def __init__(self, model: str = "L2-Coder", 
                 criteria: list[str] = None):
        """Default criteria: correctness, completeness, style, safety."""
    
    def evaluate(self, task: str, output: str) -> Verdict:
        """Ask the judge LLM: is this output good enough?"""
```

Judge prompt template (sent to L2 model):
```
You are a code quality judge. Evaluate this output against the task.

TASK: {task}
OUTPUT: {output}

Check:
1. Does the code solve the stated problem?
2. Is it complete (no TODOs, no missing functions)?
3. Does it follow Python best practices?
4. Are there bugs or edge case issues?
5. Is it production-ready?

Return JSON: {"accepted": bool, "score": 0.0-1.0, "critique": "..."}
```

### 2. Failure Actions (`failure_action.py`)

```python
class FailureAction(Enum):
    LOG_ONLY = "log_only"
    NOTIFY_AND_ESCALATE = "notify_and_escalate"
    NOTIFY_AND_WAIT = "notify_and_wait"

# Per-tier defaults:
TIER_FAILURE_ACTIONS = {
    "L0-Coder": FailureAction.LOG_ONLY,        # L0 is free, just log
    "L1-Coder": FailureAction.NOTIFY_AND_ESCALATE,  # notify, keep going
    "L2-Coder": FailureAction.NOTIFY_AND_WAIT,      # getting expensive, ask human
    "L3-Coder": FailureAction.NOTIFY_AND_WAIT,      # most expensive, always ask
}
```

### 3. Notifier (`notify.py`)

Pluggable notification backends. Default: mesh message to primary agent.

```python
class Notifier(ABC):
    @abstractmethod
    def send(self, message: str, urgency: str) -> bool: ...

class MeshNotifier(Notifier):
    """Send via agent mesh to primary agent."""
    
class TelegramNotifier(Notifier):
    """Send via Telegram to human."""
    
class NoopNotifier(Notifier):
    """Silent — for testing."""
```

### 4. Fail-Now Signal

A mechanism for human or agent to preempt the escalation loop:

```python
# Set before calling ask():
set_fail_now(tier="L3-Coder")  

# Or via environment:
export MRKRABS_FAIL_NOW=L2-Coder

# Or via agent mesh message:
mesh.send("mrkrabs://fail-now", {"tier": "L3-Coder"})
```

When `fail_now` is set, `ask()` skips directly to the specified tier, calls once (no retry loop), and returns whatever it gets. Cost is logged but not checked.

### 5. Cost Tracking (unchanged role)

`CostTracker` remains, but its role shifts from *controller* to *observer*:
- Tracks spend per task, per tier, per session
- Communicates spend in notifications
- Available for analysis and reporting
- Does NOT block execution except at NOTIFY_AND_WAIT boundaries

## Implementation Plan

| Phase | What | Effort |
|-------|------|--------|
| 1 | `Judge` class + verdict prompt | 1 day |
| 2 | Refactor `_ask_with_escalation()` to use Judge + retry loop | 1 day |
| 3 | `FailureAction` enum + per-tier config | 0.5 day |
| 4 | `Notifier` base + MeshNotifier implementation | 1 day |
| 5 | `FailNow` signal (env var + function) | 0.5 day |
| 6 | Integration tests + live tier escalation test | 1 day |
| | **Total** | **5 days** |

## What Gets Deleted (already done)

- Hardcoded budget reservations in `_ask_with_escalation()`
- `max_cost` parameter on `ask()` (replaced by failure actions)
- Budget-driven abort (replaced by human-in-the-loop at expensive tiers)

## What Stays

- `CostTracker` — for tracking and communication
- `MODELS` dict + tier config — still the source of truth for providers
- Direct HTTP calls in `call_llm()` — no unnecessary adapter layers
- `circuit_breaker.py`, `rate_limit.py` — useful, partially wired
