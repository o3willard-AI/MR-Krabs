#!/usr/bin/env python3
"""Unit tests for execute_with_judge() state machine paths — Principal, FailNow, FailUp, FailureActions."""

import unittest
from unittest.mock import patch, MagicMock

from src.core.judge import Judge, Verdict
from src.core.failure_action import FailureAction
from src.core.orchestrator import LLMOrchestrator


class TestOrchestratorStateMachine(unittest.TestCase):
    """Tests for every control-flow branch in execute_with_judge()."""

    def setUp(self):
        self.orchestrator = LLMOrchestrator()
        self._mock_cost_tracker()
        self._mock_circuit_breaker()
        self.orchestrator.notifier = MagicMock()

    def _mock_cost_tracker(self):
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {
            "total_cost": 0.0, "tier_costs": {}, "token_counts": {},
        }
        self.orchestrator.cost_tracker = mock_ct
        return mock_ct

    def _mock_circuit_breaker(self, allow=True):
        mock_cb = MagicMock()
        mock_cb.can_execute.return_value = allow
        mock_reg = MagicMock()
        mock_reg.get.return_value = mock_cb
        self.orchestrator.circuit_breaker_registry = mock_reg
        return mock_reg, mock_cb

    # ── Principal Escalation ───────────────────────────────────────

    def test_principal_escalation_when_tiers_exhausted(self):
        """All L0/L1 retries fail → escalation reaches Principal."""
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": f"out{i}", "attempt": 1, "duration_seconds": 1}
            for i in range(6)
        ]

        rejections = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="nope",
                    checks_passed=[], checks_failed=["c"])
            for _ in range(6)
        ]

        with patch.object(Judge, "evaluate", side_effect=rejections):
            result = self.orchestrator.execute_with_judge(
                task_id="test_principal",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder", "Principal"],
            )

        self.assertFalse(result["success"])
        self.assertTrue(result["escalated_to_principal"])
        self.assertEqual(result["tier_used"], "Principal")
        self.assertEqual(result["attempts_total"], 6)
        self.assertIn("task", result["escalation_context"])
        self.assertIn("tiers_attempted", result["escalation_context"])
        self.assertIn("retries_per_tier", result["escalation_context"])
        self.assertIn("last_feedback", result["escalation_context"])
        self.assertEqual(mock_llm.call_count, 6)

    def test_principal_escalation_direct(self):
        """Tiers start with Principal → immediate escalation, no LLM call."""
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()

        result = self.orchestrator.execute_with_judge(
            task_id="test_principal",
            context={"task_spec": "Write code"},
            tiers=["Principal"],
        )

        self.assertTrue(result["escalated_to_principal"])
        self.assertFalse(result["success"])
        mock_llm.assert_not_called()

    # ── FailNow Preemption ─────────────────────────────────────────

    def test_fail_now_preemption_success(self):
        """FailNow signal → one-shot tier call, no judge, auto-clear."""
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "direct output",
            "attempt": 1, "duration_seconds": 2.0,
        }

        with patch("src.core.orchestrator.get_fail_now", return_value="L1-Coder"), \
             patch("src.core.orchestrator.clear_fail_now") as mock_clear, \
             patch("src.core.orchestrator.check_mesh_fail_now"), \
             patch.object(Judge, "evaluate") as mock_judge:
            result = self.orchestrator.execute_with_judge(
                task_id="test_failnow",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["fail_now"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        mock_clear.assert_called_once()
        mock_judge.assert_not_called()

    def test_fail_now_falls_through_on_failure(self):
        """FailNow tier fails → falls through to next tier via normal loop."""
        # Strategy: fail_now says L0-Coder, it fails. Fallthrough starts
        # normal loop from L0-Coder again. L0 succeeds but Judge rejects
        # (max_retries=1), so it escalates to L2 which Judge accepts.
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            # FailNow call: L0 fails
            {"success": False, "error": "down", "attempts": 1, "ready_for_escalation": True},
            # Normal loop L0: succeeds, Judge rejects
            {"success": True, "output": "L0 normal", "attempt": 1, "duration_seconds": 1},
            # Normal loop L2: succeeds, Judge accepts
            {"success": True, "output": "L2 output", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no",
                    checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="ok",
                    checks_passed=["c"], checks_failed=[]),
        ]

        with patch("src.core.orchestrator.get_fail_now", return_value="L0-Coder"), \
             patch("src.core.orchestrator.clear_fail_now"), \
             patch("src.core.orchestrator.check_mesh_fail_now"), \
             patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_failnow",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L2-Coder"],
                max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L2-Coder")

    # ── FailUp Abort ──────────────────────────────────────────────

    def test_fail_up_at_tier_entry_skips_tier(self):
        """FailUp active at tier entry → skip tier, continue to next.

        is_fail_up_active call sequence (3 calls for 2 tiers w/ max_retries=1):
          L0 tier entry: True  → skip L0
          L1 tier entry: False → proceed to retry loop
          L1 retry 1:    False → execute, judge accepts, return
        """
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.return_value = {
            "success": True, "output": "L1 output",
            "attempt": 1, "duration_seconds": 1,
        }

        with patch("src.core.orchestrator.is_fail_up_active",
                   side_effect=[True, False, False]), \
             patch("src.core.orchestrator.clear_fail_up") as mock_clear, \
             patch("src.core.orchestrator.check_mesh_fail_up"), \
             patch.object(Judge, "evaluate", return_value=Verdict(
                 accepted=True, provisional=False, score=0.9, critique="ok",
                 checks_passed=[], checks_failed=[],
             )):
            result = self.orchestrator.execute_with_judge(
                task_id="test_failup",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertIn("L0-Coder", result["escalation_path"])
        mock_clear.assert_called()

    def test_fail_up_mid_retry_aborts_tier(self):
        """FailUp triggers during retry loop → abort tier, record retries, continue.

        is_fail_up_active call sequence (5 calls for 2 tiers w/ max_retries=2):
          L0 tier entry: False → proceed
          L0 retry 1:    False → execute, judge rejects
          L0 retry 2:    True  → abort mid-retry, retries=1, continue to L1
          L1 tier entry: False → proceed
          L1 retry 1:    False → execute, judge accepts, return
        """
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 attempt", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1 output", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="bad",
                    checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="ok",
                    checks_passed=["c"], checks_failed=[]),
        ]

        with patch("src.core.orchestrator.is_fail_up_active",
                   side_effect=[False, False, True, False, False, False]), \
             patch("src.core.orchestrator.clear_fail_up") as mock_clear, \
             patch("src.core.orchestrator.check_mesh_fail_up"), \
             patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_failup",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=2,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.assertEqual(result["retries_per_tier"]["L0-Coder"], 1)
        self.assertEqual(mock_llm.call_count, 2)
        mock_clear.assert_called()

    # ── Failure Actions ────────────────────────────────────────────

    def test_failure_action_log_only(self):
        """LOG_ONLY: L0 exhausted → silently continue to L1."""
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 out", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1 out", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no",
                    checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="yes",
                    checks_passed=["c"], checks_failed=[]),
        ]

        with patch.object(Judge, "evaluate", side_effect=verdicts):
            # L0-Coder defaults to LOG_ONLY in tier_config.py
            result = self.orchestrator.execute_with_judge(
                task_id="test_logonly",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")

    def test_failure_action_notify_and_escalate(self):
        """NOTIFY_AND_ESCALATE: L0 fails → notifier fires per-tier → L1 succeeds.

        After the fix, failure_action dispatches inside the for-tier loop
        (not post-loop), so L0's notification fires immediately and
        escalation continues to L1 which succeeds.
        """
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 out", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1 out", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no",
                    checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="yes",
                    checks_passed=["c"], checks_failed=[]),
        ]

        with patch("src.core.orchestrator.get_tier_failure_action",
                   return_value=FailureAction.NOTIFY_AND_ESCALATE), \
             patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_notify_esc",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.orchestrator.notifier.send.assert_called()

    def test_failure_action_notify_and_wait_confirmed(self):
        """NOTIFY_AND_WAIT + human confirms: L0 fails → human gate per-tier →
        confirmed → continues to L1 which succeeds.

        After the fix, the human gate fires per-tier inside the loop.
        Confirmation allows escalation to continue.
        """
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 out", "attempt": 1, "duration_seconds": 1},
            {"success": True, "output": "L1 out", "attempt": 1, "duration_seconds": 1},
        ]

        verdicts = [
            Verdict(accepted=False, provisional=False, score=0.3, critique="no",
                    checks_passed=[], checks_failed=["c"]),
            Verdict(accepted=True, provisional=False, score=0.9, critique="yes",
                    checks_passed=["c"], checks_failed=[]),
        ]

        with patch("src.core.orchestrator.get_tier_failure_action",
                   return_value=FailureAction.NOTIFY_AND_WAIT), \
             patch("src.core.human_gate.write_pending_file"), \
             patch("src.core.human_gate.wait_for_human", return_value=(True, "")), \
             patch.object(Judge, "evaluate", side_effect=verdicts):
            result = self.orchestrator.execute_with_judge(
                task_id="test_wait_confirm",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L1-Coder")
        self.orchestrator.notifier.send.assert_called()

    def test_failure_action_notify_and_wait_aborted(self):
        """NOTIFY_AND_WAIT + human denies → abort escalation, return failure."""
        mock_llm = self.orchestrator.call_llm_with_retry = MagicMock()
        mock_llm.side_effect = [
            {"success": True, "output": "L0 out", "attempt": 1, "duration_seconds": 1},
        ]

        with patch("src.core.orchestrator.get_tier_failure_action",
                   return_value=FailureAction.NOTIFY_AND_WAIT), \
             patch("src.core.human_gate.write_pending_file"), \
             patch("src.core.human_gate.wait_for_human", return_value=(False, "user declined")), \
             patch.object(Judge, "evaluate", return_value=Verdict(
                 accepted=False, provisional=False, score=0.3, critique="no",
                 checks_passed=[], checks_failed=["c"],
             )):
            result = self.orchestrator.execute_with_judge(
                task_id="test_wait_abort",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder"],
                max_retries_per_tier=1,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "user declined")
        self.assertIsNone(result["tier_used"])


if __name__ == "__main__":
    unittest.main()
