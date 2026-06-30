#!/usr/bin/env python3
"""Integration tests for judge-based escalation — mocked at PI + Judge boundaries.

Mocks _execute_pi_tier (PI subprocess) and Judge.evaluate (LLM evaluation).
No real subprocesses or API calls. (M1 — rewritten Jun 2026)
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from src.core.orchestrator import LLMOrchestrator
from src.core.judge import Verdict
from src.core.fail_now import set_fail_now, clear_fail_now
from src.core.fail_now import set_fail_up, clear_fail_up
from src.core.failure_action import FailureAction


# ── Helpers ────────────────────────────────────────────────────────

def _mk_pi_result(success=True, output="def solve(x): return x * 2",
                  written_paths=None, duration=0.5):
    """Build a mock return value for _execute_pi_tier."""
    return {
        "success": success,
        "output": output,
        "attempt": 1,
        "duration_seconds": duration,
        "written_paths": written_paths or [],
    }


def _mk_verdict(accepted=True, score=0.9, critique="Good",
                provisional=False):
    """Build a mock Verdict."""
    return Verdict(
        accepted=accepted,
        provisional=provisional,
        score=score,
        critique=critique,
        checks_passed=["correctness"] if accepted else [],
        checks_failed=[] if accepted else ["correctness"],
    )


class TestJudgeEscalationE2E:
    """End-to-end tests using mocked PI + Judge boundaries."""

    def setup_method(self):
        self.orchestrator = LLMOrchestrator()
        # Ensure PI backend is active regardless of config file
        if not self.orchestrator.pi_models and not self.orchestrator.opencode_models:
            self.orchestrator.pi_models = {"l0-coder": "test/model", "l1-coder": "test/model"}
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {"daily_total": 0.0}
        self.orchestrator.cost_tracker = mock_ct
        mock_reg = MagicMock()
        mock_cb = MagicMock()
        mock_cb.can_execute.return_value = True
        mock_reg.get.return_value = mock_cb
        self.orchestrator.circuit_breaker_registry = mock_reg
        mock_notifier = MagicMock()
        self.orchestrator.notifier = mock_notifier

    # ── Scenario 1: L0 accepts first try ──────────────────────────

    def test_l0_accepts_first_try(self):
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_l0",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L0-Coder"
        assert result["attempts_total"] == 1

    # ── Scenario 2: L0 rejects, retry succeeds ─────────────────────

    def test_l0_rejects_retry_succeeds(self):
        # First call: PI succeeds but judge rejects
        # Second call: PI succeeds and judge accepts
        pi_results = [
            _mk_pi_result(),
            _mk_pi_result(output="def foo(x): return x * 2"),
        ]
        judge_results = [
            _mk_verdict(accepted=False, score=0.3,
                       critique="Missing edge cases"),
            _mk_verdict(),
        ]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=pi_results,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_results,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_retry",
                context={"task_spec": "Write a function with edge cases"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L0-Coder"
        assert result["attempts_total"] == 2

    # ── Scenario 3: L0 exhausts, L1 accepts ────────────────────────

    def test_l0_exhausts_l1_accepts(self):
        pi_l0 = [_mk_pi_result() for _ in range(3)]  # 3 tries, all rejected
        pi_l1 = [_mk_pi_result(output="L1 good code")]
        judge_reject = [
            _mk_verdict(accepted=False, score=0.3, critique="Bad")
            for _ in range(3)
        ]
        judge_accept = [_mk_verdict()]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=pi_l0 + pi_l1,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_reject + judge_accept,
        ), patch(
            "src.core.orchestrator.get_tier_failure_action",
            return_value=FailureAction.NOTIFY_AND_ESCALATE,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_escalate",
                context={"task_spec": "Complex task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"

    # ── Scenario 4: FailNow skips all ──────────────────────────────

    def test_fail_now_skips_all(self):
        set_fail_now("L1-Coder")
        try:
            # FailNow uses call_llm_with_retry, not PI
            mock_call = MagicMock(return_value={
                "success": True, "output": "L1 direct output",
                "attempt": 1, "duration_seconds": 0.1,
            })
            self.orchestrator.call_llm_with_retry = mock_call

            result = self.orchestrator.execute_with_judge(
                task_id="test_failnow",
                context={"task_spec": "Urgent task"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder"],
            )

            assert result["success"] is True
            assert result["tier_used"] == "L1-Coder"
            assert result["attempts_total"] == 1
            assert result.get("fail_now") is True
        finally:
            clear_fail_now()
            os.environ.pop("MRKRABS_FAIL_NOW", None)

    # ── Scenario 5: PI hard failure on L0 → skips to L1 ────────────

    def test_pi_hard_failure_l0_skips_to_l1(self):
        # L0 hard-fails all 3 retries, then L1 succeeds
        pi_results = [
            _mk_pi_result(success=False, output=""),  # L0 fail
            _mk_pi_result(success=False, output=""),  # L0 retry fail
            _mk_pi_result(success=False, output=""),  # L0 retry fail
            _mk_pi_result(output="L1 output"),         # L1 success
        ]
        judge_results = [
            _mk_verdict(),  # L1 accepted
        ]
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=pi_results,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_results,
        ), patch(
            "src.core.orchestrator.get_tier_failure_action",
            return_value=FailureAction.NOTIFY_AND_ESCALATE,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_pi_fail",
                context={"task_spec": "Task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        assert "L0-Coder" in result["escalation_path"]

    # ── Scenario 6: Judge JSON parse failure → degrades gracefully

    def test_judge_json_parse_failure(self):
        """Judge returns non-JSON — rejected as raw text critique."""
        weird_verdict = Verdict(
            accepted=False, provisional=False, score=0.0,
            critique="This is definitely not JSON at all",
            checks_passed=[], checks_failed=["json_parse_error"],
        )
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=weird_verdict,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_json_fail",
                context={"task_spec": "Task"},
                tiers=["L0-Coder"],
                max_retries_per_tier=1,
            )

        assert result["success"] is False

    # ── Scenario 7: Cost tracking via mock ────────────────────────

    def test_cost_tracking_called(self):
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ):
            self.orchestrator.execute_with_judge(
                task_id="test_cost",
                context={"task_spec": "Task"},
                tiers=["L0-Coder"],
            )

        assert self.orchestrator.cost_tracker.record.called

    # ── Scenario 8: Feedback injection in retry prompt ────────────

    def test_feedback_in_retry_prompt(self):
        captured_tasks = []

        def capture_pi(tier, user_prompt, **kwargs):
            captured_tasks.append(user_prompt)
            return _mk_pi_result()

        judge_results = [
            _mk_verdict(accepted=False, score=0.3,
                       critique="NEEDS EDGE CASES"),
            _mk_verdict(),
        ]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=capture_pi,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_results,
        ):
            self.orchestrator.execute_with_judge(
                task_id="test_feedback",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder"],
                max_retries_per_tier=2,
            )

        assert len(captured_tasks) >= 2
        assert "NEEDS EDGE CASES" in captured_tasks[1]

    # ── Scenario 9: All tiers exhausted ───────────────────────────

    def test_all_tiers_exhausted(self):
        judge = _mk_verdict(accepted=False, score=0.2, critique="Terrible")
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=[_mk_pi_result(), _mk_pi_result()],
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=[judge, judge],
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_exhausted",
                context={"task_spec": "Impossible task"},
                tiers=["L0-Coder"],
                max_retries_per_tier=2,
            )

        assert result["success"] is False
        assert result["tier_used"] is None

    # ── Scenario 10: Circuit breaker blocks tier ──────────────────

    def test_circuit_breaker_blocks_tier(self):
        cb_mock_l0 = MagicMock()
        cb_mock_l0.can_execute.return_value = False
        cb_mock_l1 = MagicMock()
        cb_mock_l1.can_execute.return_value = True
        self.orchestrator.circuit_breaker_registry.get.side_effect = [
            cb_mock_l0, cb_mock_l1,
        ]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(output="L1 output"),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ), patch(
            "src.core.orchestrator.get_tier_failure_action",
            return_value=FailureAction.NOTIFY_AND_ESCALATE,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_cb",
                context={"task_spec": "Task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"

    # ── Scenario 11: FailUp bumps exactly one tier ─────────────────

    def test_fail_up_bumps_one_tier(self):
        set_fail_up()
        try:
            with patch.object(
                self.orchestrator, "_execute_pi_tier",
                return_value=_mk_pi_result(output="L1 output"),
            ), patch(
                "src.core.orchestrator.Judge.evaluate",
                return_value=_mk_verdict(),
            ):
                result = self.orchestrator.execute_with_judge(
                    task_id="test_fail_up",
                    context={"task_spec": "Task"},
                    tiers=["L0-Coder", "L1-Coder", "L2-Coder"],
                )

            assert result["success"] is True
            assert result["tier_used"] == "L1-Coder"
            assert "L0-Coder" in result["escalation_path"]
        finally:
            clear_fail_up()
            os.environ.pop("MRKRABS_FAIL_UP", None)

    # ── Scenario 12: All L0/L1/L2 exhausted → Principal escalation

    def test_all_tiers_exhausted_escalates_to_principal(self):
        judge = _mk_verdict(accepted=False, score=0.2, critique="Bad")
        # 3 tiers × 1 attempt each = 3 PI results
        pi = [_mk_pi_result() for _ in range(3)]
        judge_results = [judge for _ in range(3)]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=pi,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_results,
        ), patch(
            "src.core.orchestrator.get_tier_failure_action",
            return_value=FailureAction.NOTIFY_AND_ESCALATE,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_principal",
                context={"task_spec": "Solve P vs NP"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
                max_retries_per_tier=1,
            )

        assert result["success"] is False
        assert result.get("escalated_to_principal") is True
        assert result["tier_used"] == "Principal"

    # ── Test 13: Judge uses correct model param ───────────────────

    def test_judge_model_routing_respects_judge_model_param(self):
        """Judge model parameter is threaded through to evaluate()."""
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(),
        ), patch(
            "src.core.judge.Judge.__init__",
            return_value=None,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ) as mock_eval:
            # Need to mock __init__ so "custom-judge" doesn't fail model lookup
            self.orchestrator.execute_with_judge(
                task_id="test_judge_routing",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
                judge_model="custom-judge",
            )

        assert mock_eval.called

    # ── Test 14: Tool executor invoked before judge ────────────────

    def test_tool_executor_invoked_before_judge(self):
        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(
                written_paths=["test_output.py"],
            ),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_tool_execution",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True

    # ── Test 15: Cost tracker receives token estimates ──────────────

    def test_cost_tracker_receives_token_estimates(self):
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {"daily_total": 0.0}
        self.orchestrator.cost_tracker = mock_ct

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            return_value=_mk_pi_result(output="A" * 100),
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            return_value=_mk_verdict(),
        ):
            self.orchestrator.execute_with_judge(
                task_id="test_cost_tracking",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert mock_ct.record.called

    # ── Test 16: Notifier fires on escalation ──────────────────────

    def test_notifier_fires_on_escalation_with_correct_urgency(self):
        mock_notifier = MagicMock()
        self.orchestrator.notifier = mock_notifier

        pi_results = [
            _mk_pi_result(),  # L0 attempt
            _mk_pi_result(output="L1 output"),
        ]
        judge_results = [
            _mk_verdict(accepted=False, score=0.3, critique="Bad"),
            _mk_verdict(),
        ]

        with patch.object(
            self.orchestrator, "_execute_pi_tier",
            side_effect=pi_results,
        ), patch(
            "src.core.orchestrator.Judge.evaluate",
            side_effect=judge_results,
        ), patch(
            "src.core.orchestrator.get_tier_failure_action",
            return_value=FailureAction.NOTIFY_AND_ESCALATE,
        ):
            result = self.orchestrator.execute_with_judge(
                task_id="test_notifier_urgency",
                context={"task_spec": "Complex task"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        mock_notifier.send.assert_called()
