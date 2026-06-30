#!/usr/bin/env python3
"""Unit tests for the Judge-based escalation system in LLMOrchestrator."""

import unittest
from unittest.mock import patch, MagicMock

from src.core.judge import Judge, Verdict
from src.core.orchestrator import LLMOrchestrator


class TestJudgeEscalation(unittest.TestCase):
    def setUp(self):
        self.orchestrator = LLMOrchestrator()

    def _mock_cost_tracker(self):
        """Replace cost_tracker with a mock (avoids real file I/O)."""
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {
            "total_cost": 0.0,
            "tier_costs": {},
            "token_counts": {}
        }
        self.orchestrator.cost_tracker = mock_ct
        return mock_ct

    def _mock_circuit_breaker(self, allow=True):
        """Replace circuit_breaker_registry with a mock that allows/blocks all tiers."""
        mock_cb = MagicMock()
        mock_cb.can_execute.return_value = allow
        mock_reg = MagicMock()
        mock_reg.get.return_value = mock_cb
        self.orchestrator.circuit_breaker_registry = mock_reg
        return mock_reg, mock_cb

    def _mock_circuit_breaker_sequence(self, results):
        """Replace circuit_breaker_registry where get() returns sequenced results."""
        mock_cbs = [MagicMock() for _ in results]
        for cb, allow in zip(mock_cbs, results):
            cb.can_execute.return_value = allow
        mock_reg = MagicMock()
        mock_reg.get.side_effect = mock_cbs
        self.orchestrator.circuit_breaker_registry = mock_reg
        return mock_reg

    # ── Happy Path ───────────────────────────────────────────────

    def test_execute_with_judge_happy_path(self):
        """L0 accepts on first try."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "Success output",
            "attempt": 1, "duration_seconds": 2.0,
        }

        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="Good work",
            checks_passed=["correctness"], checks_failed=[],
        )):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")
        self.assertEqual(result["attempts_total"], 1)
        self.assertEqual(result["retries_per_tier"]["L0-Coder"], 1)

    # ── Retry Success ────────────────────────────────────────────

    def test_execute_with_judge_retry_success(self):
        """L0 fails judge once, retry 2 passes."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "Attempt 1", "attempt": 1, "duration_seconds": 2.0},
            {"success": True, "output": "Attempt 2", "attempt": 2, "duration_seconds": 2.5},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="Needs improvement",
                    checks_passed=[], checks_failed=["correctness"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="Good work",
                    checks_passed=["correctness"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")
        self.assertEqual(result["attempts_total"], 2)

    # ── Multi-Tier Escalation ────────────────────────────────────

    def test_execute_with_judge_multi_tier_escalation(self):
        """L0 fails all 3 retries, L1 accepts on first try."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 a1", "attempt": 1, "duration_seconds": 1},  # L0 retry 1
            {"success": True, "output": "L0 a2", "attempt": 2, "duration_seconds": 1},  # L0 retry 2
            {"success": True, "output": "L0 a3", "attempt": 3, "duration_seconds": 1},  # L0 retry 3
            {"success": True, "output": "L1 a1", "attempt": 1, "duration_seconds": 1},  # L1 retry 1
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="Bad 1", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=False, provisional=False, score=0.4, critique="Bad 2", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=False, provisional=False, score=0.2, critique="Bad 3", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="Good!", checks_passed=["c"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertEqual(result["attempts_total"], 4)
        self.assertIn("L0-Coder", result["escalation_path"])
        self.assertIn("L1-Coder", result["escalation_path"])

    # ── All Tiers Exhausted ──────────────────────────────────────

    def test_execute_with_judge_all_tiers_exhausted(self):
        """All tiers fail — total failure."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": f"out{i}", "attempt": 1, "duration_seconds": 1}
            for i in range(6)  # 3 L0 + 3 L1
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="nope", checks_passed=[], checks_failed=["c"])
            for _ in range(6)
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertFalse(result["success"])
        self.assertIsNone(result["tier_used"])
        self.assertEqual(result["attempts_total"], 6)

    # ── HTTP Failure Mid-Tier ────────────────────────────────────

    def test_execute_with_judge_http_failure_mid_tier(self):
        """L0 HTTP failure → skips to L1, which accepts."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": False, "error": "HTTP 500", "attempts": 1, "ready_for_escalation": True},
            {"success": True, "output": "L1 ok", "attempt": 1, "duration_seconds": 1},
        ]

        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="ok", checks_passed=[], checks_failed=[],
        )) as mock_judge:
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        # Judge should NOT be called for L0 (HTTP failure skips judge)
        mock_judge.assert_called_once()  # only called for L1

    # ── Feedback Injection ───────────────────────────────────────

    def test_execute_with_judge_feedback_injection(self):
        """Feedback from rejected attempt appears in next call's prompt."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "A1", "attempt": 1, "duration_seconds": 2.0},
            {"success": True, "output": "A2", "attempt": 2, "duration_seconds": 2.5},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="ADD MORE DETAIL",
                    checks_passed=[], checks_failed=["correctness"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="Good", checks_passed=[], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["attempts_total"], 2)

        # Verify feedback was injected into the second call's user_prompt
        second_call = mock_llm.call_args_list[1]
        user_prompt = second_call[0][2]  # positional arg index 2 = user_prompt
        self.assertIn("ADD MORE DETAIL", str(user_prompt))
        self.assertIn("Previous Attempt 1 Feedback", str(user_prompt))

    # ── Cost Tracking (observer) ─────────────────────────────────

    def test_execute_with_judge_cost_tracking(self):
        """CostTracker.record() called (observer — never blocks)."""
        mock_ct = self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "ok", "attempt": 1, "duration_seconds": 2.0,
        }

        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="ok", checks_passed=[], checks_failed=[],
        )):
            self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder"],
            )

        mock_ct.record.assert_called_once()

    # ── Circuit Breaker Blocks Tier ──────────────────────────────

    def test_execute_with_judge_circuit_breaker_blocks_tier(self):
        """Circuit breaker blocks L0 → skips to L1."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker_sequence([False, True])  # block L0, allow L1

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "Success", "attempt": 1, "duration_seconds": 2.0,
        }

        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="Good", checks_passed=[], checks_failed=[],
        )):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertIn("L0-Coder", result["escalation_path"])

    # ── Custom Tiers ─────────────────────────────────────────────

    def test_execute_with_judge_custom_tiers(self):
        """Only specified tiers are used."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()

        # L1 fails 3 retries, L3 succeeds on first
        mock_llm.side_effect = [
            {"success": True, "output": "L1a1", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1a2", "attempt": 2, "duration_seconds": 1},
            {"success": True, "output": "L1a3", "attempt": 3, "duration_seconds": 1},
            {"success": True, "output": "L3a1", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=False, provisional=False, score=0.3, critique="no", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=False, provisional=False, score=0.3, critique="no", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="yes", checks_passed=["c"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L1-Coder", "L3-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L3-Coder")
        self.assertEqual(result["attempts_total"], 4)

    # ── Edge Cases ───────────────────────────────────────────────

    def test_execute_with_judge_judge_unavailable(self):
        """Judge.evaluate raises → degrade gracefully, move to next tier."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0a1", "attempt": 1, "duration_seconds": 1},  # judge raises
            {"success": True, "output": "L0a2", "attempt": 2, "duration_seconds": 1},  # judge raises
            {"success": True, "output": "L0a3", "attempt": 3, "duration_seconds": 1},  # judge raises
            {"success": True, "output": "L1a1", "attempt": 1, "duration_seconds": 1},  # judge works
        ]

        # Judge raises on L0 calls, works on L1
        judge_calls = [0]
        real_evaluate = Judge.evaluate

        def flaky_evaluate(self_judge, task, output):
            judge_calls[0] += 1
            if judge_calls[0] <= 3:
                raise RuntimeError("Judge API down")
            return Verdict(
                accepted=True, provisional=False, score=0.9, critique="ok",
                checks_passed=["c"], checks_failed=[],
            )

        with patch.object(Judge, "evaluate", side_effect=flaky_evaluate, autospec=True):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertEqual(result["attempts_total"], 4)

    def test_execute_with_judge_tool_execution_failure(self):
        """Tool execution failure → judge still evaluates, escalates if rejected."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0a1", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L0a2", "attempt": 2, "duration_seconds": 1},
        ]

        # First rejected, second accepted
        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="Tool exec failed",
                    checks_passed=[], checks_failed=["tool"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="ok", checks_passed=["c"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")
        self.assertEqual(result["attempts_total"], 2)

    def test_execute_with_judge_empty_context(self):
        """Empty context — task_id used as judge task."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "ok", "attempt": 1, "duration_seconds": 1,
        }

        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="ok", checks_passed=[], checks_failed=[],
        )) as mock_judge:
            result = self.orchestrator.execute_with_judge(
                task_id="bare_task", context={},
                tiers=["L0-Coder"],
            )

        self.assertTrue(result["success"])
        # Judge should have been called with task="bare_task" (the task_id)
        self.assertEqual(mock_judge.call_args[1]["task"], "bare_task")

    def test_execute_with_judge_max_retries_custom(self):
        """max_retries_per_tier=1 → only one attempt per tier."""
        self._mock_cost_tracker()
        self._mock_circuit_breaker(allow=True)

        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no", checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="yes", checks_passed=["c"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_task", context={"task_spec": "Test task"},
                tiers=["L0-Coder", "L1-Coder"], max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertEqual(result["retries_per_tier"]["L0-Coder"], 1)


if __name__ == "__main__":
    unittest.main()
