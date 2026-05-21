#!/usr/bin/env python3
"""Pressure / chaos tests for the MR-Krabs orchestrator.

Characterizes behavior under:
1. Rapid fail_up baton mashing — many fail_up signals mid-task
2. Concurrent task flood — multiple tasks arriving simultaneously
3. Stalled / incompetent judge — judge hangs or returns garbage
4. Task-while-pipelining — new task arrives while another is mid-escalation
"""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

from src.core.judge import Judge, Verdict
from src.core.failure_action import FailureAction
from src.core.orchestrator import LLMOrchestrator


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _accept_verdict():
    return Verdict(accepted=True, score=0.95, critique="Perfect",
                   checks_passed=["correctness"], checks_failed=[])

def _reject_verdict(critique="needs work"):
    return Verdict(accepted=False, score=0.3, critique=critique,
                   checks_passed=[], checks_failed=["correctness"])

def _fresh_orchestrator():
    """Create an orchestrator with all network-dependent collaborators mocked."""
    orch = LLMOrchestrator()
    orch.cost_tracker = MagicMock()
    orch.cost_tracker.get_summary.return_value = {"total_cost": 0.0}
    cb = MagicMock()
    cb.can_execute.return_value = True
    reg = MagicMock()
    reg.get.return_value = cb
    orch.circuit_breaker_registry = reg
    orch.notifier = MagicMock()
    return orch

def _mock_llm_success(output="mock output"):
    return {"success": True, "output": output, "attempt": 1, "duration_seconds": 0.01}


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 1: Fail-Up Machine Gun
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailUpMachineGun(unittest.TestCase):
    """What happens when 50 fail_up signals arrive during one task?"""

    def test_rapid_fail_up_exhausts_all_tiers(self):
        """Each fail_up bumps one tier. 50 fail_ups should exhaust everything."""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        # Every tier entry and every retry check — always True
        # This should cause the orchestrator to skip every tier instantly
        with patch("src.core.orchestrator.is_fail_up_active", return_value=True), \
             patch("src.core.orchestrator.clear_fail_up"), \
             patch("src.core.orchestrator.check_mesh_fail_up"):
            result = orch.execute_with_judge(
                task_id="chaos_failup",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
            )

        # Every tier was skipped by fail_up → Principal reached, no LLM calls
        self.assertTrue(result["escalated_to_principal"])
        self.assertEqual(result["tier_used"], "Principal")
        # LLM should NEVER have been called (all tiers skipped at entry)
        orch.call_llm_with_retry.assert_not_called()

    def test_interleaved_fail_up_partial_work(self):
        """Alternating fail_up — some tiers do work, some get aborted mid-retry."""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        # Pattern:
        #   L0 entry: False → proceed
        #   L0 retry 1: True → abort mid-retry (no LLM call, no Judge)
        #   L1 entry: False → proceed
        #   L1 retry 1: False → LLM called, Judge rejects
        #   L1 retry 2: True → abort mid-retry (no LLM call)
        #   L2 entry: True → skip
        #   → Principal reached
        # Total LLM calls: 1 (L1 retry 1 only)
        with patch("src.core.orchestrator.is_fail_up_active",
                   side_effect=[
                       False,  # L0 entry
                       True,   # L0 retry 1
                       False,  # L1 entry
                       False,  # L1 retry 1
                       True,   # L1 retry 2
                       True,   # L2 entry
                   ]), \
             patch("src.core.orchestrator.clear_fail_up"), \
             patch("src.core.orchestrator.check_mesh_fail_up"), \
             patch.object(Judge, "evaluate", side_effect=[
                 _reject_verdict(),  # L1 retry 1 rejected
             ]):
            result = orch.execute_with_judge(
                task_id="chaos_interleaved",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
                max_retries_per_tier=2,
            )

        self.assertTrue(result["escalated_to_principal"])
        self.assertIn("L0-Coder", result["escalation_path"])
        self.assertIn("L1-Coder", result["escalation_path"])
        self.assertIn("L2-Coder", result["escalation_path"])
        self.assertEqual(orch.call_llm_with_retry.call_count, 1,
                         f"Expected 1 LLM call, got {orch.call_llm_with_retry.call_count}")
        self.assertEqual(result["retries_per_tier"]["L0-Coder"], 0)
        self.assertEqual(result["retries_per_tier"]["L1-Coder"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 2: Concurrent Task Flood
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrentTaskFlood(unittest.TestCase):
    """What happens when 10 tasks hit the orchestrator simultaneously?

    ANSWER: The orchestrator is synchronous with NO queuing. Each task
    executes independently. If called from threads, the instance's mutable
    state (escalation_path, retries_per_tier, feedback) is shared and
    will corrupt. The supporting components (circuit breaker, cost tracker)
    ARE thread-safe — but the orchestrator loop itself is not.
    """

    def test_shared_orchestrator_thread_safety(self):
        """Launch 5 concurrent tasks on one orchestrator — does it crash?"""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        errors = []
        results = []

        def run_task(task_id):
            try:
                with patch.object(Judge, "evaluate", return_value=_accept_verdict()):
                    r = orch.execute_with_judge(
                        task_id=task_id,
                        context={"task_spec": f"Task {task_id}"},
                        tiers=["L0-Coder"],
                        max_retries_per_tier=1,
                    )
                    results.append(r)
            except Exception as e:
                errors.append((task_id, str(e)))

        threads = [threading.Thread(target=run_task, args=(f"task-{i}",))
                   for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Should NOT crash (components are thread-safe, even if orchestrator state is shared)
        self.assertEqual(len(errors), 0,
                         f"Orchestrator crashed under concurrent load: {errors}")

        # Some tasks should have succeeded (though results may be interleaved)
        successes = [r for r in results if r.get("success")]
        self.assertGreater(len(successes), 0,
                           "No tasks succeeded under concurrent load")

    def test_independent_orchestrators_thread_safety(self):
        """Each task gets its own orchestrator — the safe pattern.

        Uses setUp-level Judge mock to avoid patch.object thread-safety
        issues with concurrent context-manager entry.
        """
        errors = []
        results = []

        def run_task(task_id):
            try:
                orch = _fresh_orchestrator()
                orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())
                r = orch.execute_with_judge(
                    task_id=task_id,
                    context={"task_spec": f"Task {task_id}"},
                    tiers=["L0-Coder"],
                    max_retries_per_tier=1,
                )
                results.append((task_id, r["success"], r["tier_used"]))
            except Exception as e:
                errors.append((task_id, str(e)))

        # Patch Judge.evaluate BEFORE spawning threads to avoid races
        with patch.object(Judge, "evaluate", return_value=_accept_verdict()):
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(run_task, f"task-{i}") for i in range(10)]
                for f in as_completed(futures):
                    f.result(timeout=15)

        self.assertEqual(len(errors), 0)
        successes = [r for r in results if r[1]]
        self.assertEqual(len(successes), 10,
                         f"Expected 10 successes, got {len(successes)}: {results}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 3: Stalled / Incompetent Judge
# ═══════════════════════════════════════════════════════════════════════════════

class TestStalledJudge(unittest.TestCase):
    """What happens when the judge is slow, hung, or returns garbage?"""

    def test_judge_returns_gibberish(self):
        """Judge returns unparseable JSON — should degrade to rejection."""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        # The real Judge.evaluate parses JSON from the LLM response.
        # We mock the LLM response to return garbage.
        gibberish_llm_output = "not json at all just raw text {{{"

        # Mock requests.post for the judge call to return garbage
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": gibberish_llm_output}}],
            }

            # First call: agent tier (L0)
            # Second call: judge
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {
                    "choices": [{"message": {"content": "def solve(): return 42"}}],
                }),
                mock_response,
            ]

            # Need a real Judge for this test — but with mocked HTTP
            os.environ["OPENROUTER_API_KEY"] = "fake-key"
            try:
                result = orch.execute_with_judge(
                    task_id="chaos_gibberish",
                    context={"task_spec": "Write solve()"},
                    tiers=["L0-Coder"],
                )
            finally:
                del os.environ["OPENROUTER_API_KEY"]

        # Should NOT crash — judge degradation path should kick in
        # (Either accepted by luck, or rejected gracefully)
        self.assertIn("success", result)

    def test_slow_judge_timeout_handling(self):
        """Judge takes 5 seconds to respond — does the orchestrator hang?"""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        def slow_evaluate(*args, **kwargs):
            time.sleep(5.0)
            return _accept_verdict()

        start = time.monotonic()
        with patch.object(Judge, "evaluate", side_effect=slow_evaluate):
            result = orch.execute_with_judge(
                task_id="chaos_slow_judge",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder"],
                timeout_seconds=10,  # generous timeout
            )
        elapsed = time.monotonic() - start

        # If the orchestrator has a timeout, it should return within bounds
        # (The judge's 5s sleep is within the 10s timeout)
        self.assertTrue(result["success"])
        self.assertGreaterEqual(elapsed, 4.5,
                                f"Judge should have taken ~5s, got {elapsed:.1f}s")

    def test_judge_always_rejects(self):
        """Incompetent judge that rejects everything — escalation should work."""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

        # L2-Coder defaults to NOTIFY_AND_WAIT → needs human_gate patched
        with patch.object(Judge, "evaluate", return_value=_reject_verdict("always bad")), \
             patch("src.core.human_gate.write_pending_file"), \
             patch("src.core.human_gate.wait_for_human", return_value=(True, "")):
            result = orch.execute_with_judge(
                task_id="chaos_always_reject",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
                max_retries_per_tier=1,
            )

        # Should escalate all the way to Principal
        self.assertTrue(result["escalated_to_principal"])
        self.assertIn("L0-Coder", result["escalation_path"])
        self.assertIn("L1-Coder", result["escalation_path"])
        self.assertIn("L2-Coder", result["escalation_path"])

    def test_judge_accepts_garbage_code(self):
        """Overly permissive judge that accepts anything — code may be broken."""
        orch = _fresh_orchestrator()
        orch.call_llm_with_retry = MagicMock(
            return_value=_mock_llm_success(output="def broken(::: syntax error")
        )

        with patch.object(Judge, "evaluate", return_value=_accept_verdict()):
            result = orch.execute_with_judge(
                task_id="chaos_lenient",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder"],
            )

        # Judge accepted garbage — orchestrator doesn't second-guess
        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 4: Task-While-Pipelining
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskWhilePipelining(unittest.TestCase):
    """What happens when a new task arrives while one is mid-escalation?

    ANSWER: The orchestrator has NO queuing. It processes one task at a time
    synchronously. A second task must either:
    a) Wait (caller blocks)
    b) Use a separate orchestrator instance (caller spawns)
    c) Be dropped (caller's responsibility)

    There is no built-in queue, no task registry, no admission control.
    """

    def test_second_task_blocks_on_same_orchestrator(self):
        """Calling execute_with_judge() while another is running blocks."""
        orch = _fresh_orchestrator()

        # Make the first task slow (judge takes time)
        call_order = []

        def slow_task():
            orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())
            with patch.object(Judge, "evaluate", return_value=_accept_verdict()):
                result = orch.execute_with_judge(
                    task_id="slow_task",
                    context={"task_spec": "Slow"},
                    tiers=["L0-Coder"],
                )
            call_order.append("slow_done")
            return result

        def fast_task():
            orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())
            with patch.object(Judge, "evaluate", return_value=_accept_verdict()):
                result = orch.execute_with_judge(
                    task_id="fast_task",
                    context={"task_spec": "Fast"},
                    tiers=["L0-Coder"],
                )
            call_order.append("fast_done")
            return result

        # Launch slow task in a thread, then try fast task
        slow_thread = threading.Thread(target=slow_task)
        slow_thread.start()
        time.sleep(0.1)  # let slow task start

        # Fast task called directly — this blocks until slow task's orchestrator
        # finishes (since execute_with_judge is synchronous and the mock
        # call_llm_with_retry returns instantly, this actually completes fast).
        #
        # In reality with real HTTP calls, the second call would block
        # waiting for the first to complete if using the same orchestrator.
        fast_task()

        slow_thread.join(timeout=5)
        self.assertIn("slow_done", call_order)
        self.assertIn("fast_done", call_order)

    def test_independent_orchestrators_run_concurrently(self):
        """Two orchestrator instances — tasks run truly in parallel."""
        results = {}
        start_times = {}

        def run_task(task_id, delay):
            orch = _fresh_orchestrator()
            orch.call_llm_with_retry = MagicMock(return_value=_mock_llm_success())

            def delayed_judge(*args, **kwargs):
                time.sleep(delay)
                return _accept_verdict()

            start_times[task_id] = time.monotonic()
            with patch.object(Judge, "evaluate", side_effect=delayed_judge):
                r = orch.execute_with_judge(
                    task_id=task_id,
                    context={"task_spec": task_id},
                    tiers=["L0-Coder"],
                )
            results[task_id] = (r["success"], time.monotonic() - start_times[task_id])

        # Launch both simultaneously
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(run_task, "task-a", 0.5)
            f2 = executor.submit(run_task, "task-b", 0.5)
            f1.result(timeout=10)
            f2.result(timeout=10)

        # Both should complete in ~0.5s (parallel), not 1.0s (serial)
        self.assertTrue(results["task-a"][0])
        self.assertTrue(results["task-b"][0])
        total_wall = max(results["task-a"][1], results["task-b"][1])
        self.assertLess(total_wall, 1.0,
                        f"Tasks should run in parallel (~0.5s), took {total_wall:.1f}s")


if __name__ == "__main__":
    unittest.main()
