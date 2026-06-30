# Cookbook

Integration recipes for AI agents. Every example is executable.

## 1. Execute from command line

```python
import subprocess, json
result = subprocess.run(
    ["python", "-m", "src.core.orchestrator", "--task", "Write a UUID v7 generator"],
    capture_output=True, text=True, cwd="/path/to/MR-Krabs"
)
output = json.loads(result.stdout)
```

## 2. Programmatic with judge pipeline

```python
from src.core.orchestrator import LLMOrchestrator

orch = LLMOrchestrator()
result = orch.execute_with_judge(
    task_id="rate-limiter",
    context={"task_spec": "Write an async rate limiter with Redis backend"},
    tiers=["l0-coder", "l1-coder", "l2-coder", "principal"],
    max_retries_per_tier=3,
)
```

## 3. L0-only (zero cloud cost)

```python
result = orch.execute_with_judge(
    task_id="simple-sort",
    context={"task_spec": "Sort a list of dicts by key"},
    tiers=["l0-coder", "principal"],
    max_retries_per_tier=5,
)
```

## 4. With structured acceptance criteria (spec dict)

```python
result = orch.execute_with_judge(
    task_id="auth-module",
    context={
        "task_spec": "Write an authentication module with password hashing",
        "spec": {
            "success_criteria": [
                "Passwords are hashed with bcrypt",
                "Login returns JWT token",
                "All tests pass",
            ],
            "constraints": [
                "Must use existing ORM — no raw SQL",
                "No new dependencies",
            ],
            "anti_patterns": [
                "eval()",
                "shell=True",
                "plaintext password storage",
            ],
        },
    },
    tiers=["l0-coder", "l1-coder", "principal"],
    max_retries_per_tier=3,
)
```

The `spec` dict is injected into the Judge's evaluation prompt as structured
"## Acceptance Criteria" — giving the Judge an objective bar for scoring.

## 5. Resume from checkpoint

```python
# If a previous pipeline run was killed mid-escalation, resume it:
result = orch.execute_with_judge(
    task_id="same-task-id-as-before",
    context={"task_spec": "..."},
    tiers=["l0-coder", "l1-coder", "l2-coder", "principal"],
    max_retries_per_tier=3,
    resume_from_checkpoint=True,  # skips already-completed tiers
)
```

Checkpoints are written after every tier verdict to
`docs/workflow/escalations/<task_id>_checkpoint.json`. Completed tiers are
skipped on resume; accumulated files and escalation state are restored.

## 6. Self-improvement hook

```bash
# After pipeline runs, auto-discover failure patterns and update model profiles:
MRKRABS_SELF_IMPROVE=1 python -m src.core.orchestrator --task "Write a bloom filter"
# Prints: [SELF-IMPROVE] Discovered 2 patterns across 1 models
```

The SelfImprover reads verdict data from `~/.mrkrabs/debug/`, discovers
recurring failure patterns, and injects `KnownFailure` entries into
`src/core/model_profiles.py` so the Judge catches them on first sight.

## 7. Force escalation

```python
import os
os.environ["MRKRABS_FAIL_NOW"] = "l2-coder"
result = orch.execute_with_judge(task_id="complex", ...)
```

## 8. Abort stuck tier

```python
os.environ["MRKRABS_FAIL_UP"] = "1"
```

## 9. Verify install

```bash
python -m src.validators.templates
python -m src.validators.startup
```

## 10. Environment Variables

All MR-Krabs behavior can be controlled via environment variables.
These override config.yaml settings at runtime.

| Variable | Purpose | Values |
|----------|---------|--------|
| `MRKRABS_CONFIG` | Override config file path | Path to config.yaml |
| `MRKRABS_PROMPT_FLOW_DEBUG` | Dump every agent's full prompt/response to disk | `1` or unset |
| `MRKRABS_SELF_IMPROVE` | Auto-discover failure patterns and update model profiles after pipeline runs | `1` or unset |
| `MRKRABS_FAIL_NOW` | Force a specific tier to fail (simulate escalation) | Tier name, e.g. `l0-coder` |
| `MRKRABS_FAIL_UP` | Immediately abort current tier and escalate | `1` |
| `MRKRABS_ENABLE_HEURISTIC_CLASSIFIER` | Enable regex-based task classification | `true` or unset |

### Debugging with prompt flow dumps

```bash
MRKRABS_PROMPT_FLOW_DEBUG=1 python -m src.core.orchestrator --task "Write a bloom filter"
# Dumps appear in ~/.mrkrabs/debug/<task_id>/
```

### Simulating escalation

```bash
# Force L0 to fail — tests that L1 picks up the work
MRKRABS_FAIL_NOW=l0-coder python -m src.core.orchestrator --task "Write a bloom filter"

# Kill current tier immediately
MRKRABS_FAIL_UP=1 python -m src.core.orchestrator --task "Write a bloom filter"
```
