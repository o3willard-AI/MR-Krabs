# PERF-09b: Worker Pool — Per-Task Orchestrator Dispatcher

**Phase:** Production Hardening — Scalability & Resiliency
**Priority:** P0 (enables concurrent task execution)
**Estimated effort:** 60m
**Dependencies:** PERF-09a (AdmissionGate)

## Goal

Add a worker pool that dispatches tasks to independent `LLMOrchestrator` instances, gated by the `AdmissionGate`. This is the "one orchestrator per task" pattern — each task gets full isolation, and the admission gate prevents overload.

## Design

```
TaskQueue(["task-1", "task-2", ..., "task-N"])
    │
    ▼
WorkerPool(max_workers=3, gate=AdmissionGate(max_concurrent=3))
    │
    ├── Spawn worker for task-1 ──► LLMOrchestrator #1 ──► Result
    ├── Spawn worker for task-2 ──► LLMOrchestrator #2 ──► Result
    ├── Spawn worker for task-3 ──► LLMOrchestrator #3 ──► Result
    │
    └── Collect results as futures → completed dict
```

## File

`src/core/worker_pool.py`

## Public API

```python
from src.core.admission import AdmissionGate
from src.core.worker_pool import WorkerPool, TaskSpec

gate = AdmissionGate(max_concurrent=3)
pool = WorkerPool(gate=gate, task_timeout=300.0)

tasks = [
    TaskSpec(task_id="task-1", context={"task_spec": "Write fib()"}, tiers=["L0-Coder"]),
    TaskSpec(task_id="task-2", context={"task_spec": "Write sort()"}, tiers=["L0-Coder", "L1-Coder"]),
]

# Fire-and-forget
futures = pool.dispatch(tasks)
# futures: dict[task_id, Future[dict]] — caller can wait/check/cancel

# Block until all done
results = pool.run_all(tasks)
# results: dict[task_id, dict] — the execute_with_judge() return value

# Query
status = pool.status
# {"running": ["task-1"], "completed": {"task-2": result}, "rejected": ["task-3"]}
```

## Classes

### TaskSpec (dataclass)
- `task_id: str` — unique identifier
- `context: dict` — passed to execute_with_judge()
- `tiers: list[str] | None = None` — escalation tiers
- `max_retries_per_tier: int = 3`
- `judge_model: str = "Judge"`
- `timeout_seconds: float = 300.0`

### WorkerPool
- `__init__(gate: AdmissionGate, task_timeout: float = 300.0)`
- `dispatch(tasks: list[TaskSpec]) -> dict[str, Future]` — non-blocking; returns futures immediately. Rejected tasks get a resolved future with `{"success": False, "rejected": True}`.
- `run_all(tasks: list[TaskSpec]) -> dict[str, dict]` — blocking; waits for all futures, returns results dict.
- `status` property — snapshot of running/completed/rejected tasks.

## Implementation notes

### Per-task isolation
Each task gets a **fresh LLMOrchestrator instance**. The worker:
1. Calls `gate.admit(task_id)` — blocks until slot or timeout
2. If rejected: returns `{"success": False, "rejected": True, "reason": "gate full"}`
3. Creates `LLMOrchestrator()`
4. Injects shared components: `orchestrator.circuit_breaker_registry = shared_registry` (optional — separate registries per instance is also valid and simpler)
5. Calls `orchestrator.execute_with_judge(**task_spec.to_dict())`
6. Releases gate ticket
7. Returns result

### Shared vs isolated components
- **Circuit breaker**: should be **shared** — one provider going down should block all tasks from using it, not just one
- **Cost tracker**: can be **shared** or **isolated**. Shared = aggregate cost view. Isolated = per-task cost tracking.
- **Notifier**: naturally shared (single Telegram/Discord channel)
- **fail_up/fail_now**: already global (mesh files) — no sharing needed

Start simple: everything isolated except circuit breaker. Add shared cost tracker as a follow-up.

### Thread safety
- `ThreadPoolExecutor` from `concurrent.futures` — battle-tested
- AdmissionGate is thread-safe (semaphore + lock)
- LLMOrchestrator is NOT thread-safe internally (no locks on instance state) — but that's fine because each task gets its own instance
- CircuitBreakerRegistry IS thread-safe (locks on individual breakers)

## Tests

File: `tests/unit/test_worker_pool.py`

### 1. `test_single_task_succeeds`
- Pool.dispatch([task]). Future resolves with success=True, tier_used="L0-Coder". Gate shows current=0 after.

### 2. `test_multiple_tasks_run_concurrently`
- Dispatch 3 tasks (gate max_concurrent=3, max_retries=1, mocked Judge.evaluate). All 3 complete in < 1s (parallel, not serial).

### 3. `test_gate_rejects_overflow`
- Gate max_concurrent=1. Dispatch task-A (admitted). Dispatch task-B (acquire_timeout=0.1s → rejected). Result has rejected=True.

### 4. `test_run_all_blocks_until_complete`
- run_all([task1, task2]). All results present. Function returns after last task finishes.

### 5. `test_task_isolation_on_failure`
- Task-A's Judge raises RuntimeException. Task-A result has success=False. Task-B (same pool, concurrent) completes normally — no cross-contamination.

### 6. `test_circuit_breaker_shared_state`
- Two tasks, shared circuit_breaker_registry. Task-A trips breaker on L0-Coder provider. Task-B's L0-Coder call is skipped. Task-B falls through to L1. Verifies isolation + shared gating.

## Verification
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/unit/test_worker_pool.py -v
```
All 6 tests pass. No regressions on existing suite.
