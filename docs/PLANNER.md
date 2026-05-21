# MR-Krabs Planner Stack

The planner stack enables MR-Krabs to produce implementation plans
(architecture, design docs, phase breakdowns) using the same multi-tier
escalation pipeline as code generation. It works by swapping the agent
system prompts and targeting planner-tier LLMs.

## Quick Start

```python
from src.core.worker_pool import TaskSpec, WorkerPool
from src.core.admission import AdmissionGate

gate = AdmissionGate(max_concurrent=3)
pool = WorkerPool(gate=gate)

# Plan a feature
plan_task = TaskSpec(
    task_id="design-auth-module",
    context={
        "task_spec": "Design an OAuth2 authentication module with JWT refresh tokens. "
                     "It must support Google and GitHub providers, rate limiting on "
                     "login attempts, and session management."
    },
    task_type="plan",                     # ← the only change from code tasks
    tiers=["L0-Planner", "L1-Architect"],  # planner model tiers
)

result = pool.run_all([plan_task])
print(result["design-auth-module"]["output"])
```

## Task Types

| Type | `task_type` | Default tiers | Models | Prompt template |
|------|-------------|---------------|--------|-----------------|
| Code | `"code"` (default) | `L0-Coder`, `L1-Coder`, `L2-Coder` | qwen3-coder-30b, grok-4.3, minimax-m2.7 | `code-system-prompt.md` |
| Plan | `"plan"` | `L0-Planner`, `L1-Architect`, `L2-Architect` | qwen3-coder-30b, grok-4.3, claude-sonnet-4.6 | `plan-system-prompt.md` |

**If `task_type` is not specified, everything defaults to code.** No
ambiguity — three independent defaults all converge on `"code"`:
`TaskSpec.task_type`, `execute_with_judge(task_type=...)`, and
`_get_agent_system_prompt(task_type=...)`.

## How It Works

### Prompt Routing

The orchestrator loads the agent system prompt based on `task_type`:

```
TaskSpec(task_type="plan")
    │
    ▼
execute_with_judge(task_type="plan")
    │
    ▼
_get_agent_system_prompt("plan")
    │
    ▼
Loads: docs/workflow/templates/plan-system-prompt.md
```

The code prompt and plan prompt are completely independent. You can
customize either without affecting the other. Templates live at:

```
docs/workflow/templates/
├── code-system-prompt.md    ← agent = expert developer, writes code
├── plan-system-prompt.md    ← agent = architect, writes markdown plans
└── agent-system-prompt.md   ← legacy (no longer used)
```

### Tier Configuration

Planner tiers are defined in `src/core/model_config.py` alongside coder
tiers. The planner models use **lower temperature** (0.3) and are
restricted to `file_read` only (plans don't execute code):

```python
"L0-Planner": {
    "provider": "lmstudio",
    "model": "qwen/qwen3-coder-30b",
    "temperature": 0.3,
    "tools": ["file_read"],           # read-only — planners survey, don't write code
},
"L1-Architect": {
    "provider": "openrouter",
    "model": "x-ai/grok-4.3",
    "temperature": 0.3,
    "tools": ["file_read"],
},
```

To add custom planner tiers, add entries to `MODELS` with the pattern
above. You can mix planner and coder tiers in a single escalation path
if needed — the prompt routing is per-task, not per-tier.

### Judge Evaluation

The judge evaluates plans on different criteria than code:

| Code criteria | Plan criteria |
|---------------|---------------|
| Correctness (does it compile?) | Completeness (are all requirements covered?) |
| Efficiency (big-O, memory) | Feasibility (can it be built?) |
| Edge cases handled | Risk identification (what could go wrong?) |
| Style conventions | Clarity (can a developer follow it?) |

The judge prompt template (`docs/workflow/templates/judge-prompt.md`)
can accept a `{task_type}` variable to swap evaluation criteria.
Currently the judge uses a unified prompt that covers both code and
plan evaluation — customize this template for task-type-specific
judging.

### Escalation

The escalation pipeline is identical for code and plan tasks:

```
Task enters ──► L0-Planner ──► Judge ──► accepted? ──► return plan
                    │                        │
                    │ rejected               │
                    ▼                        │
              Retry (up to 3x) ──────────────┘
                    │
                    │ all retries exhausted
                    ▼
              L1-Architect ──► Judge ──► ...
                    │
                    ▼
              L2-Architect ──► ... ──► Principal (human)
```

All the same infrastructure applies: circuit breakers, cost tracking,
failure actions, fail_up/fail_now signals, and the admission gate.

### Concurrency

Planner tasks work with the WorkerPool just like code tasks:

```python
# Mix code and plan tasks in the same pool
tasks = [
    TaskSpec(task_id="fib", context={...}, task_type="code"),
    TaskSpec(task_id="design-auth", context={...}, task_type="plan"),
    TaskSpec(task_id="sort", context={...}, task_type="code"),
]

futures = pool.dispatch(tasks)
# All three run concurrently, each with its own orchestrator and prompt
```

## Experimental Heuristic Classifier

**Status: Experimental — disabled by default. May change or be removed.**

The heuristic classifier attempts to auto-detect whether a task is code
or plan based on keyword matching. It is gated behind an environment
variable:

```bash
export MRKRABS_ENABLE_HEURISTIC_CLASSIFIER=true
```

When enabled, `TaskSpec` without an explicit `task_type` will be
classified:

```python
# With MRKRABS_ENABLE_HEURISTIC_CLASSIFIER=true:
spec = TaskSpec(task_id="t1", context={"task_spec": "design the auth architecture"})
# → task_type auto-detected as "plan"

spec = TaskSpec(task_id="t2", context={"task_spec": "implement the login endpoint"})
# → task_type auto-detected as "code"
```

**Explicit `task_type` always wins.** If you set `task_type="plan"`, the
heuristic is never consulted, regardless of the env var.

### Classification Rules

The classifier uses weighted keyword matching:

| Signal strength | Plan keywords | Code keywords |
|-----------------|---------------|---------------|
| Normal (1pt) | architecture, design doc, implementation plan, roadmap, specification | implement, write code, fix bug, refactor, deploy, test |
| Strong (2pt) | architecture, design doc, implementation plan, system design, blueprint, proposal | implement, write code, fix bug, refactor, PR, pull request |

The type with the higher score wins. Ties default to code.

### Limitations (why it's experimental)

- **Substring false positives**: "pr" matches "blueprint", giving
  spurious code scores to plan-oriented text
- **No semantic understanding**: "write a plan for implementing auth" is
  a plan task but scores high on code keywords
- **Language-dependent**: keywords are English-only
- **No context awareness**: can't see that a task is part of a larger
  planning session

We evaluate accuracy over time. If the heuristic proves reliable, it
will be promoted to fully supported in a future version.

## Adding a New Task Type

To add a third task type (e.g., `"review"`):

1. **Create a prompt template**: `docs/workflow/templates/review-system-prompt.md`
2. **Add model tiers** (optional): entries in `src/core/model_config.py`
   with `"tools": ["file_read"]` (reviewers don't write code)
3. **Update the classifier** (optional): add keywords to
   `src/core/task_classifier.py`
4. **No code changes needed**: the orchestrator already loads
   `{task_type}-system-prompt.md` dynamically

## Reference

- Prompt templates: `docs/workflow/templates/{type}-system-prompt.md`
- Model config: `src/core/model_config.py`
- Classifier: `src/core/task_classifier.py`
- Worker pool: `src/core/worker_pool.py` (TaskSpec.task_type)
- Orchestrator: `src/core/orchestrator.py` (execute_with_judge, _get_agent_system_prompt)
- Tests: `tests/unit/test_task_routing.py`
