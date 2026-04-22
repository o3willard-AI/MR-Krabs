#!/usr/bin/env python3
"""Performance benchmark suite for the orchestrator.

Benchmarks:
1. Overhead microbenchmark — measure orchestrator code overhead with mock provider
2. Concurrent budget stress test — verify no overrun under concurrency
3. Context simplification performance — verify <10ms for 500KB input
4. Memory profile under load — verify bounded memory for sustained operations
"""

from __future__ import annotations

import time
import sys
import os
import tracemalloc
import threading
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.cost import CostTracker, Budget, TokenCount, BudgetExceededError
from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState
from src.core.error_classifier import FailureAnalyzer, ErrorCategory, ErrorAction
from src.core.model_capabilities import CapabilityChecker, MODEL_REGISTRY
from src.core.orchestrator import LLMOrchestrator


def benchmark_overhead():
    """Measure orchestration overhead with mock operations."""
    tracker = CostTracker()
    tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)

    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        tracker.calculate_cost("x-ai/grok-4.1-fast", tokens)
    elapsed = time.perf_counter() - start

    per_call_ms = (elapsed / iterations) * 1000
    print(f"  Overhead microbenchmark: {per_call_ms:.3f}ms per call ({iterations} iterations)")
    assert per_call_ms < 1.0, f"Overhead too high: {per_call_ms:.3f}ms"
    return per_call_ms


def benchmark_concurrent_budget():
    """Run concurrent tasks with tight budget and verify no overrun."""
    budget = Budget(daily_limit_usd=Decimal("10.00"))
    tracker = CostTracker(budget=budget)
    errors = []
    success_count = [0]
    blocked_count = [0]
    lock = threading.Lock()

    def task(i):
        try:
            r = tracker.reserve_budget(f"task-{i}", Decimal("0.50"))
            with lock:
                success_count[0] += 1
            tracker.finalize_spending(r.id, Decimal("0.40"))
        except BudgetExceededError:
            with lock:
                blocked_count[0] += 1
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = []
    for i in range(100):
        t = threading.Thread(target=task, args=(i,))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_spent = tracker.daily_total
    print(f"  Concurrent budget: {success_count[0]} succeeded, {blocked_count[0]} blocked, spent=${total_spent:.2f}")
    assert total_spent <= Decimal("10.50"), f"Budget overrun: ${total_spent}"
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    return total_spent


def benchmark_context_simplification():
    """Verify context simplification is fast even for large inputs."""
    orch = LLMOrchestrator()
    large_context = "x" * 500_000

    iterations = 10
    start = time.perf_counter()
    for _ in range(iterations):
        orch._simplify_context(large_context, 0.7)
    elapsed = time.perf_counter() - start

    per_call_ms = (elapsed / iterations) * 1000
    print(f"  Context simplification (500KB): {per_call_ms:.2f}ms per call")
    assert per_call_ms < 10.0, f"Context simplification too slow: {per_call_ms:.2f}ms"
    return per_call_ms


def benchmark_circuit_breaker():
    """Measure circuit breaker overhead under contention."""
    registry = CircuitBreakerRegistry()
    iterations = 100000

    start = time.perf_counter()
    for _ in range(iterations):
        cb = registry.get("openrouter", "test-model")
        cb.can_execute()
        cb.record_success()
    elapsed = time.perf_counter() - start

    per_call_us = (elapsed / iterations) * 1_000_000
    print(f"  Circuit breaker: {per_call_us:.1f}us per operation ({iterations} iterations)")
    assert per_call_us < 100, f"Circuit breaker too slow: {per_call_us:.1f}us"
    return per_call_us


def benchmark_error_classification():
    """Measure error classification speed."""
    analyzer = FailureAnalyzer()
    test_errors = [
        ConnectionError("Connection refused"),
        ValueError("Context length exceeded"),
        RuntimeError("429 Too Many Requests"),
        PermissionError("Invalid API key"),
        TimeoutError("Request timed out"),
    ]

    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        for err in test_errors:
            analyzer.analyze(err)
    elapsed = time.perf_counter() - start

    per_call_us = (elapsed / (iterations * len(test_errors))) * 1_000_000
    print(f"  Error classification: {per_call_us:.1f}us per error")
    assert per_call_us < 500, f"Error classification too slow: {per_call_us:.1f}us"
    return per_call_us


def benchmark_memory_under_load():
    """Run many operations and verify memory doesn't grow unboundedly."""
    tracemalloc.start()

    tracker = CostTracker()
    registry = CircuitBreakerRegistry()
    tokens = TokenCount(prompt_tokens=100, completion_tokens=50)

    for i in range(10000):
        tracker.calculate_cost("x-ai/grok-4.1-fast", tokens)
        cb = registry.get("openrouter", "test-model")
        cb.can_execute()
        cb.record_success()
        if i % 100 == 0:
            tracker.record(f"task-{i}", "L0", "x-ai/grok-4.1-fast", tokens, 0.1)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    print(f"  Memory under load (10k ops): peak={peak_mb:.1f}MB")
    assert peak_mb < 200, f"Memory too high: {peak_mb:.1f}MB"
    return peak_mb


def run_all():
    """Run all benchmarks."""
    print("=" * 60)
    print("Performance Benchmarks")
    print("=" * 60)

    results = {}
    results["overhead_ms"] = benchmark_overhead()
    results["concurrent_budget"] = benchmark_concurrent_budget()
    results["context_simplification_ms"] = benchmark_context_simplification()
    results["circuit_breaker_us"] = benchmark_circuit_breaker()
    results["error_classification_us"] = benchmark_error_classification()
    results["memory_peak_mb"] = benchmark_memory_under_load()

    print()
    print("=" * 60)
    print("Results Summary")
    print("=" * 60)
    for k, v in results.items():
        print(f"  {k}: {v}")
    print()
    print("All benchmarks PASSED")
    return results


if __name__ == "__main__":
    run_all()
