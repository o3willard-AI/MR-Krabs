# Performance & Scalability Review: Cost-Optimized AI Orchestration

**Reviewer**: LLM Performance Reviewer (Claude Opus)
**Date**: April 3, 2026
**Documents Reviewed**: All project documentation in `docs/`

---

## 1. Executive Summary

The performance targets are reasonable for a library that wraps LLM calls (which themselves take 1-30 seconds). The <100ms overhead target is achievable for the happy path but will be exceeded under specific conditions: SQLite concurrent writes, tiktoken initialization, and OTel export. The most critical performance concern is **SQLite write contention** in the budget tracking path — this is a single-writer database being used as a concurrent budget ledger, which is architecturally mismatched. The circuit breaker's `threading.Lock` is adequate for moderate concurrency but will become a bottleneck at 1000+ concurrent tasks. Overall, the system should perform well for the Phase 1 target audience (individual developers, small teams) but will need architectural changes for the Phase 3+ scalability targets.

---

## 2. Bottleneck Analysis (Ranked)

### 2.1 #1 Bottleneck: SQLite Write Contention

**Severity**: High for concurrent workloads
**Location**: SYSTEM_ARCHITECTURE.md:328-339, PERFORMANCE_REVIEW_REQUEST.md:40-43

SQLite uses a single writer lock. When multiple concurrent tasks try to record spending, they serialize on the write lock. Under WAL mode, reads don't block writes, but writes still block other writes. The typical write latency for SQLite is 1-5ms, but under contention with 100+ concurrent writers, the queue delay grows linearly.

**Quantitative estimate**:
- SQLite write throughput (WAL mode): ~1000-2000 writes/second
- Each task requires at least 2 writes: budget reservation + spending record
- At 1000 concurrent tasks: ~2000 writes needed in quick succession
- Expected write queue delay: 1-2 seconds for the last task in the queue

This exceeds the <100ms overhead target by 10-20x.

**Recommendation**:
1. For Phase 1 (dev mode): SQLite is fine for individual developers running <10 concurrent tasks. Document this limitation.
2. Batch budget writes: Instead of writing per-call, accumulate spending in memory and flush every 100ms or every N calls.
3. Use an in-memory budget ledger with periodic SQLite checkpoints. The in-memory ledger handles budget checks atomically (no DB round-trip), and the SQLite write happens asynchronously.
4. For Phase 3 (production): PostgreSQL with connection pooling and `SELECT ... FOR UPDATE SKIP LOCKED` for non-blocking budget checks.

### 2.2 #2 Bottleneck: tiktoken Initialization

**Severity**: Medium (one-time cost, but significant)
**Location**: TECHNICAL_DESIGN_DECISIONS.md:471-502

The `TiktokenCounter._get_encoder()` method lazily loads encoders:
```python
self._encoders[model] = tiktoken.encoding_for_model(model)
```

tiktoken encoder initialization involves:
- Downloading the BPE merge file (~1.5MB for cl100k_base) on first use
- Parsing and loading it into memory (~50-100ms)
- Subsequent calls are cached in the `_encoders` dict

**Impact**: The first call to `estimate_tokens()` for each model will add 50-100ms. If using many different models, this happens multiple times.

**Recommendation**:
1. Pre-initialize encoders at startup for all configured models (eager loading, not lazy).
2. Ship the BPE merge files with the package to avoid the network download.
3. Use the fast approximation (`len(text) // 4`) for budget pre-checks and reserve tiktoken for accuracy-critical paths. The current design already does this (TECHNICAL_DESIGN_DECISIONS.md:120-123), which is good — but the `TiktokenCounter.count()` method is still called in some paths.

### 2.3 #3 Bottleneck: Circuit Breaker Lock Contention

**Severity**: Medium at high concurrency
**Location**: TECHNICAL_DESIGN_DECISIONS.md:194-275

The `CircuitBreaker` uses `threading.Lock` for all state operations. Every concurrent call to `can_execute()`, `record_success()`, or `record_failure()` acquires the lock. The lock is per-provider (not per-model, as recommended in the Architecture Review), so all tasks targeting the same provider contend on one lock.

**Quantitative estimate**:
- Lock acquisition: ~1-5 microseconds in Python (uncontended)
- At 1000 concurrent tasks hitting the same provider: ~1-5ms wait time
- Not a bottleneck on its own, but combined with other overhead, contributes to exceeding 100ms

**Recommendation**:
1. The current `threading.Lock` is fine for Phase 1-2.
2. For Phase 3+, consider lock-free atomic counters using `threading.atomic` (Python 3.12+) or `asyncio`-native equivalents.
3. Shard circuit breakers by `(provider, model)` to reduce contention.

### 2.4 #4 Bottleneck: OpenTelemetry Span Creation

**Severity**: Low-Medium
**Location**: TECHNICAL_DESIGN_DECISIONS.md:576-638

Each task creates a parent span (`task.execute`) with child spans for each tier attempt (`tier.attempt`). The OTel SDK's span creation involves:
- Span context generation (trace ID, span ID)
- Attribute storage (dictionary allocation)
- Span processor notification (can involve synchronous batch export)

**Quantitative estimate**:
- Span creation: ~10-50 microseconds per span
- At 9 spans per task (worst case): ~0.5ms
- Exporter flush: 0-100ms depending on export destination

**Recommendation**:
1. Use the `BatchSpanProcessor` (not `SimpleSpanProcessor`) to decouple span creation from export.
2. The 10% sampling rate (TECHNICAL_DESIGN_DECISIONS.md:738) is appropriate for production. Consider 100% for development.
3. Under load, adaptive sampling should increase the sampling ratio. The current design doesn't address adaptive sampling.

---

## 3. Concurrency Concerns

### 3.1 Budget Check-Then-Act Race Condition

**Severity**: High
**Location**: TECHNICAL_DESIGN_DECISIONS.md:350-393

This is detailed in the Architecture Review. The `check_budget() → execute → record_spending()` sequence is not atomic. Two concurrent tasks can both pass the budget check and both execute, exceeding the budget.

**Detailed race condition analysis**:
```
Time  Task A                      Task B                      Budget: $5.00
─────────────────────────────────────────────────────────────────────────────
T1    check_budget() → $5 left
T2                                check_budget() → $5 left
T3    execute() → costs $4
T4                                execute() → costs $4
T5    record_spending($4)                                     Budget: $1.00
T6                                record_spending($4)         Budget: -$3.00
```

**Recommendation**: Budget reservation pattern with atomic decrement:

```python
async def reserve_budget(self, scope: str, estimated_cost: float) -> Reservation:
    """Atomically reserve budget. Returns reservation or raises BudgetExceeded."""
    # PostgreSQL: UPDATE budgets SET spent = spent + $1 WHERE scope = $2 AND spent + $1 <= limit RETURNING *
    # SQLite: BEGIN EXCLUSIVE; ... COMMIT;
    result = await self.storage.atomic_reserve(scope, estimated_cost)
    if not result:
        raise BudgetExceeded(scope, estimated_cost)
    return Reservation(id=result.id, amount=estimated_cost)
```

### 3.2 Circuit Breaker State Machine Race Condition

**Severity**: Medium
**Location**: TECHNICAL_DESIGN_DECISIONS.md:220-274

The circuit breaker has a subtle race in the `HALF_OPEN` state. The `can_execute()` method allows up to `half_open_max` (default: 3) concurrent test requests. But `record_failure()` immediately transitions to OPEN:

```python
def record_failure(self):
    with self._lock:
        self._failures += 1
        self._total += 1
        if self._state == CircuitState.HALF_OPEN:
            self._open()  # Immediately reopens
```

If 3 requests are in flight in HALF_OPEN, and the first one fails (reopening the circuit), the other 2 are still in flight. When they complete (success or failure), they call `record_success()` or `record_failure()` on a circuit that is now OPEN. The `record_success()` method doesn't check for HALF_OPEN state before incrementing `_successes`, but the success count is only used in the HALF_OPEN branch — so stale successes from a previous HALF_OPEN window could accumulate.

**Recommendation**:
1. In `record_success()`, if state is OPEN (because another thread already re-opened it), ignore the success.
2. Reset counters when transitioning from HALF_OPEN to OPEN.
3. Add a `_half_open_epoch` counter that increments on each HALF_OPEN entry; discard results from previous epochs.

### 3.3 Pending Spend Reconciliation Race

**Severity**: Low-Medium
**Location**: TECHNICAL_DESIGN_DECISIONS.md:399-408

The `reconcile_pending_spends()` method iterates over `_pending_spends` and clears it:

```python
def reconcile_pending_spends(self):
    for scope, amount in self._pending_spends:
        self.storage.record_spending(scope, amount)
    self._pending_spends.clear()
```

If a new pending spend is added between the iteration and the `.clear()`, it will be lost. This list needs a lock, or should use a thread-safe queue.

**Recommendation**: Use `collections.deque` or `queue.Queue` and drain it atomically:

```python
def reconcile_pending_spends(self):
    while True:
        try:
            scope, amount = self._pending_spends_queue.get_nowait()
            self.storage.record_spending(scope, amount)
        except queue.Empty:
            break
```

---

## 4. Scaling Limits

### 4.1 SQLite: Hard Limit at ~50-100 Concurrent Writers

SQLite is not designed for concurrent write access. Even with WAL mode, practical write throughput tops out at ~50-100 concurrent tasks before write queue delays dominate the overhead budget. This is fine for individual developers but won't work for the "1000+ concurrent executions" target (NFR-002, PRD.md:192).

**Breaking point**: ~50 concurrent tasks with frequent budget updates.
**Fix**: Switch to PostgreSQL, or use in-memory budget tracking with async persistence.

### 4.2 Single-Process Python: Hard Limit at ~500-1000 Concurrent Async Tasks

Python's asyncio is single-threaded. The orchestrator's async event loop can handle many concurrent I/O-bound tasks (LLM API calls), but CPU-bound operations (token counting, context simplification, JSON serialization) happen on the main thread. With 1000 concurrent tasks, CPU-bound operations will create head-of-line blocking.

**Breaking point**: ~500 concurrent tasks if context simplification involves significant string processing.
**Fix**: Offload CPU-intensive work (token counting, context simplification) to a thread pool via `asyncio.to_thread()`.

### 4.3 Horizontal Scaling: Shared Budget State Is the Bottleneck

The scalable deployment diagram (SYSTEM_ARCHITECTURE.md:389-420) shows multiple app servers sharing a PostgreSQL database. Budget tracking requires consistent reads and writes across servers. Without careful coordination:
- Two servers check budget simultaneously and both allow a task
- Budget overrun occurs

**Fix**: PostgreSQL advisory locks or `SELECT FOR UPDATE` for budget operations. Alternatively, a Redis-based budget ledger with atomic `DECRBY` operations (faster than PostgreSQL for this specific pattern).

### 4.4 Memory Scaling: Unbounded In-Memory Structures

Several in-memory structures can grow unboundedly:
- `TiktokenCounter._encoders`: One encoder per model (~5-10MB each). With many models, this grows.
- `CircuitBreaker` instances: One per provider (or per model, if the recommendation is followed).
- OTel spans in the batch processor: If the export destination is slow, spans accumulate.
- `_pending_spends`: If storage is down for a long time, this list grows unboundedly.

**Recommendation**:
1. Cap `_encoders` with an LRU cache (max 10 models).
2. Set `max_export_batch_size` and `max_queue_size` on the OTel `BatchSpanProcessor`.
3. Cap `_pending_spends` at a maximum size (e.g., 1000 entries) and reject new tasks when full.

---

## 5. Benchmark Recommendations

### 5.1 Overhead Microbenchmark

Measure the time spent in orchestrator code (excluding LLM call time) for a single task:

```python
@benchmark
async def test_orchestrator_overhead():
    """Measure orchestration overhead with a mock provider that returns instantly."""
    orchestrator = CostOptimizedOrchestrator(
        provider=InstantMockProvider(),  # Returns in 0ms
        storage=InMemoryStorage(),
    )
    result = await orchestrator.execute_task(
        task_id="bench-1",
        description="test",
        initial_tier="L0-Coder"
    )
    # Target: total time < 100ms (all overhead, no LLM call)
```

Run this with:
- No OTel export (baseline)
- With OTel console export
- With OTel OTLP export
- With SQLite storage
- With PostgreSQL storage

### 5.2 Concurrent Budget Stress Test

```python
async def test_concurrent_budget_accuracy():
    """Run 100 concurrent tasks with a tight budget and verify no overrun."""
    orchestrator = CostOptimizedOrchestrator(budget_daily_usd=10.0)

    tasks = [
        orchestrator.execute_task(task_id=f"stress-{i}", description=f"task {i}")
        for i in range(100)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Verify: total actual spending <= budget + one task's max cost (for the race window)
    total_spent = sum(r.cost for r in results if isinstance(r, ExecutionResult))
    assert total_spent <= 10.0 + MAX_SINGLE_TASK_COST
```

### 5.3 Escalation Latency Benchmark

```python
async def test_worst_case_escalation_latency():
    """Measure total time for a task that fails through all tiers."""
    orchestrator = CostOptimizedOrchestrator(
        provider=AlwaysFailProvider(),  # All tiers fail
    )
    start = time.monotonic()
    result = await orchestrator.execute_task(task_id="worst-case", description="test")
    duration = time.monotonic() - start

    # Target: total escalation duration < 30 seconds
    # (9 attempts x max 3s backoff = 27s theoretical max)
    assert duration < 30.0
    assert result.success is False
    assert result.total_attempts == 9  # 3+3+2+1
```

### 5.4 Memory Profile Under Load

```python
async def test_memory_under_sustained_load():
    """Run 10,000 tasks and verify memory doesn't grow unboundedly."""
    import tracemalloc
    tracemalloc.start()

    orchestrator = CostOptimizedOrchestrator(
        provider=InstantMockProvider(),
        storage=InMemoryStorage(),
    )

    for i in range(10000):
        await orchestrator.execute_task(task_id=f"mem-{i}", description=f"task {i}")

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Target: peak memory < 200MB for 10,000 tasks
    assert peak < 200 * 1024 * 1024
```

### 5.5 Context Simplification Performance

```python
def test_context_simplification_large_input():
    """Verify context simplification is fast even for large inputs."""
    large_context = "x" * 500_000  # ~125K tokens (simulating a large codebase context)

    start = time.monotonic()
    simplified = simplify_structural(large_context, target_ratio=0.7)
    duration = time.monotonic() - start

    # Target: < 10ms for 500KB context
    assert duration < 0.010
```

---

## 6. Monitoring Recommendations

### 6.1 Key Performance Indicators to Monitor in Production

| Metric | Alert Threshold | Rationale |
|--------|----------------|-----------|
| `orchestrator.overhead.ms` (p99) | > 200ms | Overhead exceeding target |
| `orchestrator.db.write_latency.ms` (p99) | > 50ms | Database write contention |
| `orchestrator.budget.check_latency.ms` (p99) | > 20ms | Budget check bottleneck |
| `orchestrator.circuit_breaker.lock_wait.ms` (p99) | > 10ms | Lock contention |
| `orchestrator.memory.rss_bytes` | > 500MB | Memory leak or unbounded growth |
| `orchestrator.pending_spends.count` | > 100 | Storage is down or slow |
| `orchestrator.escalation.total_duration.ms` (p99) | > 60s | Escalation loop too slow |
| `orchestrator.otel.export_queue_size` | > 10000 | OTel export backing up |

### 6.2 Dashboard Panels (Grafana)

1. **Overhead histogram**: Distribution of orchestrator overhead (excluding LLM time)
2. **Budget utilization**: Current spend vs. limit, per scope
3. **Tier distribution**: % of tasks at each tier (should be >70% at L0)
4. **Escalation rate**: % of tasks that escalate, trend over time
5. **Circuit breaker state**: Per-provider state timeline
6. **Error rate by category**: Stack of error categories over time
7. **Concurrent task count**: Gauge of in-flight tasks
8. **Storage write latency**: Histogram of DB write times

### 6.3 Profiling Strategy

1. **Continuous profiling**: Use `py-spy` or `pyinstrument` in production with low overhead sampling.
2. **Benchmark CI**: Run the overhead microbenchmark on every PR and fail if regression > 10%.
3. **Load test on release**: Run the concurrent stress test before each release with the target concurrency level.

---

## 7. Answers to Specific Questions

### Q1: What's the most likely performance bottleneck?

**SQLite write contention in budget tracking.** Every LLM call requires at least one DB write (spending record), and with concurrent tasks, these writes serialize. This is the most likely cause of the <100ms overhead target being exceeded.

### Q2: What benchmark would you run to validate the <100ms overhead claim?

The **Overhead Microbenchmark** (Section 5.1): use a mock provider that returns instantly, measure only the orchestrator code, and report p50/p95/p99 overhead. Run it with different storage backends and OTel configurations.

### Q3: Should we publish performance benchmarks publicly?

**Yes.** Publish:
1. Overhead per call (p50, p95, p99) with different storage backends
2. Maximum concurrent tasks before performance degradation
3. Memory usage under sustained load
4. Comparison: cost with orchestrator vs. cost without (the primary value metric)

This builds trust and lets users make informed decisions about using the tool.

### Q4: What's the right approach to load testing?

Use a combination of:
1. **Microbenchmarks** (pytest-benchmark): Overhead per component
2. **Integration stress tests** (custom async): 100-1000 concurrent mock tasks
3. **End-to-end load tests** (locust): Real provider calls at target throughput
4. **Soak tests**: Run for 24 hours at moderate load to find memory leaks

### Q5: Are there algorithmic inefficiencies?

1. **Error classification** (TECHNICAL_DESIGN_DECISIONS.md:877-924): The `analyze()` method iterates over the entire `ERROR_CLASSIFICATION` dict for message matching. This is O(n) where n = number of error patterns. For ~30 patterns, this is negligible, but a compiled regex alternation would be O(1) amortized.

2. **Context simplification** (TECHNICAL_DESIGN_DECISIONS.md:36-43): `simplify_structural()` splits the entire context into lines, then takes head/tail. For a 100K token context (~400KB), this creates a large list of strings. Consider using byte offsets instead of line splitting.

3. **Section-aware reduction** (TECHNICAL_DESIGN_DECISIONS.md:61-74): The `estimate_tokens()` function is called per section, which means the entire text is scanned multiple times. Consider a single-pass approach.

4. **Config loading** (TECHNICAL_DESIGN_DECISIONS.md:1340-1372): Config is loaded and merged at startup, which is fine. But if config is reloaded on every call (design unclear), that would be wasteful.

### Q6: What would you monitor in production?

See Section 6.1. The most important metrics are:
1. **Orchestrator overhead p99** (is the system adding too much latency?)
2. **Budget accuracy** (is actual spend within budget?)
3. **Tier distribution** (are most tasks at L0, as expected?)
4. **Pending spend count** (is storage healthy?)

---

## 8. Specific Performance Decisions to Scrutinize

### 8.1 Is <100ms overhead meaningful?

**Yes and no.** LLM calls take 1-30 seconds, so 100ms is <1% overhead — negligible for user-perceived latency. But for a library that wraps every LLM call, developers are sensitive to perceived overhead. If the library adds 500ms per call, developers notice it in interactive sessions.

**Recommendation**: Target <50ms for the happy path (no retries, no escalation), <100ms including budget check and OTel instrumentation, and unbounded for the escalation loop (which involves actual LLM retries).

### 8.2 Is SQLite's write concurrency a problem for testing?

**Yes.** Integration tests that run concurrent tasks will hit SQLite contention. Tests should use InMemoryStorage by default and only test SQLite in dedicated concurrency tests.

### 8.3 Should budget checks be async?

**Yes.** All I/O operations (database reads, network calls) in the hot path should be async. The current design uses `async` for task execution (TECHNICAL_DESIGN_DECISIONS.md:584) but the `BudgetEnforcer.check_budget()` method (TECHNICAL_DESIGN_DECISIONS.md:352) is synchronous. This should be `async def check_budget()`.

### 8.4 Should metrics be aggregated before emission?

**For counters and histograms: no.** The OTel SDK already handles aggregation internally. The `BatchSpanProcessor` batches span exports.

**For budget remaining gauge: maybe.** If budget is checked 1000 times per second, updating the gauge 1000 times per second is wasteful. Consider updating the gauge on a timer (every 1-5 seconds) rather than on every budget check.

### 8.5 Is context simplification fast enough for 100K+ tokens?

**Probably, but needs benchmarking.** A 100K token context is ~400KB of text. String splitting, slicing, and reassembly for 400KB should take <1ms on modern hardware. But the section-aware strategy involves regex parsing, keyword matching, and possibly AST parsing for code files — these could be slower.

**Recommendation**: The context simplification benchmark (Section 5.5) should be a gate for any strategy change. If any strategy exceeds 10ms for a 500KB input, it should be optimized or rejected.
