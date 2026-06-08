#!/usr/bin/env python3
"""Unit tests for WorkerPool — concurrent task dispatch."""

import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from src.core.admission import AdmissionGate
from src.core.judge import Judge, Verdict
from src.core.orchestrator import LLMOrchestrator
from src.core.worker_pool import TaskSpec, WorkerPool


def _accept_verdict():
    return Verdict(accepted=True, provisional=False, score=0.95, critique="Perfect",
                   checks_passed=["correctness"], checks_failed=[])


def _reject_verdict():
    return Verdict(accepted=False, provisional=False, score=0.3, critique="needs work",
                   checks_passed=[], checks_failed=["correctness"])


def _result(task_id, success=True):
    return {
        "task_id": task_id, "success": success,
        "output": f"output for {task_id}",
        "tier_used": "L0-Coder", "attempts_total": 1,
    }


class TestWorkerPool(unittest.TestCase):

    def setUp(self):
        self.gate = AdmissionGate(max_concurrent=3, acquire_timeout=5.0)
        self.pool = WorkerPool(gate=self.gate, task_timeout=10.0)

    def tearDown(self):
        self.pool.shutdown(wait=False)

    # ── Basic dispatch ──────────────────────────────────────────────

    def test_single_task_succeeds(self):
        task = TaskSpec(task_id="task-1", context={"task_spec": "Write fib()"})
        with patch.object(LLMOrchestrator, "execute_with_judge",
                          return_value=_result("task-1")):
            futures = self.pool.dispatch([task])
            result = futures["task-1"].result(timeout=5)

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")

    # ── Concurrent execution ────────────────────────────────────────

    def test_multiple_tasks_run_concurrently(self):
        """3 tasks complete in < 2s (parallel), not 3s+ (serial)."""
        def delayed_execute(*args, **kwargs):
            time.sleep(0.5)
            return _result(kwargs.get("task_id", "unknown"))

        tasks = [
            TaskSpec(task_id=f"task-{i}", context={"task_spec": f"Task {i}"})
            for i in range(3)
        ]

        start = time.monotonic()
        with patch.object(LLMOrchestrator, "execute_with_judge", side_effect=delayed_execute):
            results = self.pool.run_all(tasks)
        elapsed = time.monotonic() - start

        for task_id, result in results.items():
            self.assertTrue(result["success"], f"{task_id} failed: {result}")

        self.assertLess(elapsed, 1.5,
                        f"Tasks should run in parallel (~0.5s), took {elapsed:.1f}s")

    # ── Gate rejection ──────────────────────────────────────────────

    def test_gate_rejects_overflow(self):
        """Gate max=1 → second task rejected immediately."""
        small_gate = AdmissionGate(max_concurrent=1, acquire_timeout=0.1)
        small_pool = WorkerPool(gate=small_gate, task_timeout=10.0)

        def slow_execute(*args, **kwargs):
            time.sleep(2.0)
            return _result(kwargs.get("task_id", "?"))

        task_a = TaskSpec(task_id="task-a", context={"task_spec": "Slow"})
        task_b = TaskSpec(task_id="task-b", context={"task_spec": "Fast"})

        with patch.object(LLMOrchestrator, "execute_with_judge", side_effect=slow_execute):
            futures = small_pool.dispatch([task_a, task_b])

            result_a = futures["task-a"].result(timeout=5)
            result_b = futures["task-b"].result(timeout=5)

        self.assertTrue(result_a["success"])
        self.assertFalse(result_b["success"])
        self.assertTrue(result_b.get("rejected"))
        self.assertIn("gate full", result_b.get("reason", ""))

        small_pool.shutdown(wait=False)

    # ── Task isolation ──────────────────────────────────────────────

    def test_task_isolation_on_failure(self):
        """Task A crashes — Task B still completes normally."""
        call_count = [0]

        def flaky_execute(*args, **kwargs):
            call_count[0] += 1
            tid = kwargs.get("task_id", "?")
            if tid == "task-a":
                raise RuntimeError("Simulated crash in task-a")
            return _result(tid)

        task_a = TaskSpec(task_id="task-a", context={"task_spec": "Crash"})
        task_b = TaskSpec(task_id="task-b", context={"task_spec": "Normal"})

        with patch.object(LLMOrchestrator, "execute_with_judge", side_effect=flaky_execute):
            results = self.pool.run_all([task_a, task_b])

        self.assertFalse(results["task-a"]["success"])
        self.assertIn("Simulated crash", results["task-a"].get("error", ""))
        self.assertTrue(results["task-b"]["success"])

    # ── Run all blocks ──────────────────────────────────────────────

    def test_run_all_blocks_until_complete(self):
        """run_all() returns only after all tasks finish."""
        completion_order = []

        def tracked_execute(*args, **kwargs):
            tid = kwargs.get("task_id", "?")
            time.sleep(0.2)
            completion_order.append(tid)
            return _result(tid)

        tasks = [
            TaskSpec(task_id=f"task-{i}", context={"task_spec": f"Task {i}"})
            for i in range(2)
        ]

        with patch.object(LLMOrchestrator, "execute_with_judge", side_effect=tracked_execute):
            results = self.pool.run_all(tasks)

        self.assertEqual(len(results), 2)
        self.assertTrue(results["task-0"]["success"])
        self.assertTrue(results["task-1"]["success"])
        self.assertEqual(len(completion_order), 2)

    # ── Pool status ─────────────────────────────────────────────────

    def test_status_reflects_running_tasks(self):
        """Status shows running tasks while they're executing."""
        started = threading.Event()
        finish = threading.Event()

        def waiting_execute(*args, **kwargs):
            started.set()
            finish.wait(timeout=5)
            return _result(kwargs.get("task_id", "?"))

        task = TaskSpec(task_id="task-status", context={"task_spec": "test"})

        with patch.object(LLMOrchestrator, "execute_with_judge", side_effect=waiting_execute):
            futures = self.pool.dispatch([task])

            # Wait for task to start
            self.assertTrue(started.wait(timeout=5),
                            "Task did not start within 5 seconds")

            status = self.pool.status
            self.assertIn("task-status", status["running"])

            # Let task finish
            finish.set()
            futures["task-status"].result(timeout=5)

        # After completion, not in running
        status2 = self.pool.status
        self.assertNotIn("task-status", status2["running"])


if __name__ == "__main__":
    unittest.main()
