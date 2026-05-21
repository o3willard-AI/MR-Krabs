# PERF-09a: Admission Gate — Backpressure Controller

**Phase:** Production Hardening — Scalability & Resiliency
**Priority:** P0 (prerequisite for concurrent task execution)
**Estimated effort:** 45m
**Dependencies:** None (greenfield, no existing code to modify)

## Goal

Add an admission controller that gates concurrent orchestrator execution. Without it, spawning per-task orchestrator instances has no upper bound — 100 tasks = 100 simultaneous LLM calls = rate-limit hell or cost explosion.

## Design

```
AdmissionGate(max_concurrent=3, acquire_timeout=30)
    │
    ├── admit() → AdmissionTicket
    │       blocks until slot available or timeout
    │       ticket.release() frees the slot
    │
    ├── context manager:  with gate as ticket:
    │
    ├── Metrics:
    │       current_count    — active tasks
    │       rejected_count   — timed-out acquires
    │       total_admitted   — lifetime counter
    │       total_wait_secs  — aggregate wait time
    │
    └── Thread-safe (threading.Semaphore)
```

## File

`src/core/admission.py`

## Public API

```python
from src.core.admission import AdmissionGate, AdmissionTicket

gate = AdmissionGate(max_concurrent=3, acquire_timeout=30.0)

# Blocking acquire
ticket = gate.admit(task_id="task-1")
if ticket.admitted:
    try:
        # run orchestrator...
    finally:
        ticket.release()
else:
    # rejected — gate full, timeout exceeded

# Context manager (preferred)
with gate.admit(task_id="task-1") as ticket:
    if ticket.admitted:
        run_orchestrator()
    else:
        handle_rejection()

# Query
print(gate.metrics)  # {"current": 2, "rejected": 0, "admitted": 42, ...}
```

## Implementation notes

### AdmissionTicket (dataclass)
- `admitted: bool` — False means rejected (timeout or gate closed)
- `task_id: str`
- `wait_seconds: float` — how long acquire blocked
- `release()` — returns slot to pool; no-op if not admitted
- Private `_gate: AdmissionGate | None` back-reference for release

### AdmissionGate
- Uses `threading.Semaphore` (NOT BoundedSemaphore — release from different thread is intentional)
- `admit(task_id)` acquires semaphore with timeout; returns AdmissionTicket
- `_release()` called by ticket.release()
- `metrics` property returns snapshot dict
- `shutdown()` closes gate — future admits return rejected immediately

### Thread safety
- `threading.Semaphore` is intrinsically thread-safe
- Metrics counters use `threading.Lock` for consistency
- `shutdown()` sets a flag, then acquires all remaining semaphore slots to drain

## Tests

File: `tests/unit/test_admission.py`

### 1. `test_single_admit_release`
- Gate(max_concurrent=1). Admit → admitted=True, current=1. Release → current=0.

### 2. `test_concurrent_limit_blocks`
- Gate(max_concurrent=1). Admit task-A (blocks slot). Start thread for task-B (acquire_timeout=2s). Assert task-B rejected (timeout). Release task-A. Retry task-B → admitted.

### 3. `test_context_manager`
- `with gate.admit("t1") as ticket:` → admitted=True. Block exits → slot freed. Next admit succeeds immediately.

### 4. `test_multiple_slots`
- Gate(max_concurrent=3). Admit 3 tasks → all admitted, current=3. 4th blocks, times out. Release one → 4th succeeds.

### 5. `test_shutdown_rejects`
- Gate(max_concurrent=2). Admit 1 task. Call shutdown(). Next admit → rejected immediately. Current task can still release().

### 6. `test_metrics_accuracy`
- Admit 2, reject 1, release 1. Assert metrics.current=1, metrics.rejected=1, metrics.total_admitted=2.

## Verification
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/unit/test_admission.py -v
```
All 6 tests pass. No regressions on existing suite.
