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

## 4. Force escalation

```python
import os
os.environ["MRKRABS_FAIL_NOW"] = "l2-coder"
result = orch.execute_with_judge(task_id="complex", ...)
```

## 5. Abort stuck tier

```python
os.environ["MRKRABS_FAIL_UP"] = "1"
```

## 6. Verify install

```bash
python -m src.validators.templates
python -m src.validators.startup
```
