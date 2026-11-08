"""Durability on the PRODUCTION path (wi-LG-REFACTOR-2).

The production tier loop runs as a checkpointed LangGraph graph
(SqliteSaver, one thread per task_id:tier). This test proves the
production execute_with_judge resumes a crashed tier instead of
restarting it:

  Run 1: the judge seam raises SimulatedCrash (modelling SIGKILL
         between the coder and judge nodes). The exception propagates
         out of execute_with_judge.
  Run 2: execute_with_judge with the SAME task_id resumes from the
         checkpoint at the judge node. The coder must NOT re-run
         (call count stays 1 across both runs) and the run completes.

Uses scripted seams for the coder/judge (repo injectable-seam
convention); everything else (routing, state, checkpointing) is the
real production code.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.judge import Judge, Verdict
from src.core.orchestrator import LLMOrchestrator


class SimulatedCrash(BaseException):
    """Stands in for a process death (SIGKILL) between nodes.

    Deliberately a BaseException, NOT an Exception: the production
    judge node catches Exception around Judge.evaluate and degrades
    to a synthetic rejection. A real process death cannot be caught
    that way, and this seam must faithfully model that.
    """


class TestProductionDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.orchestrator = LLMOrchestrator(project_root=str(self.root))
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {
            "total_cost": 0.0, "tier_costs": {}, "token_counts": {},
        }
        self.orchestrator.cost_tracker = mock_ct
        mock_cb = MagicMock()
        mock_cb.can_execute.return_value = True
        mock_reg = MagicMock()
        mock_reg.get.return_value = mock_cb
        self.orchestrator.circuit_breaker_registry = mock_reg
        self.orchestrator.notifier = MagicMock()

    def tearDown(self):
        self.tmp.cleanup()

    def test_crash_between_coder_and_judge_resumes_without_rerunning_coder(self):
        coder_calls = []
        judge_calls = []

        def fake_coder(*args, **kwargs):
            coder_calls.append(1)
            return {
                "success": True, "output": "def is_even(n): return n % 2 == 0",
                "attempt": 1, "duration_seconds": 0.5,
            }

        def flaky_evaluate(self_judge, task, output):
            judge_calls.append(1)
            if len(judge_calls) == 1:
                raise SimulatedCrash("process died before judge body ran")
            return Verdict(
                accepted=True, provisional=False, score=0.95, critique="ok",
                checks_passed=[], checks_failed=[],
            )

        context = {"task_spec": "Write is_even(n) in solution.py"}
        with patch.object(
            self.orchestrator, "call_llm_with_retry", side_effect=fake_coder
        ), patch.object(Judge, "evaluate", flaky_evaluate):
            # Run 1: crash mid-loop (after coder, before judge body)
            with self.assertRaises(SimulatedCrash):
                self.orchestrator.execute_with_judge(
                    task_id="durable-prod",
                    context=dict(context),
                    tiers=["L0-Coder"],
                )
            self.assertEqual(len(coder_calls), 1)

            # Run 2: same task_id resumes from checkpoint
            result = self.orchestrator.execute_with_judge(
                task_id="durable-prod",
                context=dict(context),
                tiers=["L0-Coder"],
            )

        # Coder ran exactly once across both invocations
        self.assertEqual(len(coder_calls), 1)
        # Judge ran twice (crashed attempt + resumed attempt)
        self.assertEqual(len(judge_calls), 2)
        self.assertTrue(result["success"])
        self.assertEqual(result["tier_used"], "L0-Coder")
        self.assertEqual(result["attempts_total"], 1)

    def test_completed_run_starts_fresh_on_repeat_call(self):
        """A normally-completed tier must NOT resume on the next call
        (guards against stale-checkpoint leakage between independent
        runs with the same task_id)."""
        coder_calls = []

        def fake_coder(*args, **kwargs):
            coder_calls.append(1)
            n = len(coder_calls)
            return {
                "success": True, "output": f"out{n}",
                "attempt": n, "duration_seconds": 0.5,
            }

        accept = Verdict(
            accepted=True, provisional=False, score=0.9, critique="ok",
            checks_passed=[], checks_failed=[],
        )
        context = {"task_spec": "Write is_even(n) in solution.py"}
        with patch.object(
            self.orchestrator, "call_llm_with_retry", side_effect=fake_coder
        ), patch.object(Judge, "evaluate", return_value=accept):
            first = self.orchestrator.execute_with_judge(
                task_id="fresh-check", context=dict(context),
                tiers=["L0-Coder"],
            )
            second = self.orchestrator.execute_with_judge(
                task_id="fresh-check", context=dict(context),
                tiers=["L0-Coder"],
            )

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        # Second call ran the coder again (fresh state, not a resume)
        self.assertEqual(len(coder_calls), 2)
        self.assertEqual(second["output"], "out2")


if __name__ == "__main__":
    unittest.main()
