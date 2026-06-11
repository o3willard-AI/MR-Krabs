#!/usr/bin/env python3
"""Tests for task-type classification and prompt routing."""

import os
import unittest
from unittest.mock import patch, MagicMock

from src.core.task_classifier import (
    classify_task, is_heuristic_enabled, _heuristic_classify,
)
from src.core.worker_pool import TaskSpec
from src.core.orchestrator import LLMOrchestrator


class TestTaskClassifier(unittest.TestCase):

    def setUp(self):
        self._orig_env = os.environ.get("MRKRABS_ENABLE_HEURISTIC_CLASSIFIER")
        os.environ.pop("MRKRABS_ENABLE_HEURISTIC_CLASSIFIER", None)

    def tearDown(self):
        if self._orig_env is not None:
            os.environ["MRKRABS_ENABLE_HEURISTIC_CLASSIFIER"] = self._orig_env
        else:
            os.environ.pop("MRKRABS_ENABLE_HEURISTIC_CLASSIFIER", None)

    def test_explicit_code_always_wins(self):
        result = classify_task("write an architecture plan", explicit_type="code")
        self.assertEqual(result, "code")

    def test_explicit_plan_always_wins(self):
        result = classify_task("implement a function", explicit_type="plan")
        self.assertEqual(result, "plan")

    def test_defaults_to_code_when_heuristic_disabled(self):
        result = classify_task("design the architecture and write an implementation plan")
        self.assertEqual(result, "code")

    def test_heuristic_plan_detection(self):
        """Test the heuristic function directly (env-independent)."""
        result = _heuristic_classify(
            "design the system architecture and write an implementation plan"
        )
        self.assertEqual(result, "plan")

    def test_heuristic_code_detection(self):
        result = _heuristic_classify(
            "implement the auth module and fix the login bug"
        )
        self.assertEqual(result, "code")

    def test_heuristic_plan_beats_code_on_strong_signals(self):
        """Strong plan signals ('blueprint', 'proposal') outweigh weak code signals."""
        # "write" is a weak code keyword, "blueprint" + "design doc" are
        # strong plan signals → plan wins
        result = _heuristic_classify(
            "write a blueprint and design doc for the new proposal"
        )
        self.assertEqual(result, "plan")

    def test_heuristic_ambiguous_defaults_to_code(self):
        """Ambiguous text without strong signals defaults to code."""
        result = _heuristic_classify("do the thing with the stuff")
        self.assertEqual(result, "code")

    def test_is_heuristic_disabled_by_default(self):
        self.assertFalse(is_heuristic_enabled())

    def test_is_heuristic_enabled_with_env(self):
        """When env var is set, classify_task without explicit_type uses heuristic."""
        os.environ["MRKRABS_ENABLE_HEURISTIC_CLASSIFIER"] = "1"
        # Re-import so the module-level _HEURISTIC_ENABLED picks up the env var
        import importlib
        import src.core.task_classifier as tc
        importlib.reload(tc)

        result = tc.classify_task(
            "design the system architecture and write an implementation plan"
        )
        self.assertEqual(result, "plan")


class TestTaskSpecTaskType(unittest.TestCase):

    def test_default_task_type_is_code(self):
        spec = TaskSpec(task_id="t1", context={"task_spec": "test"})
        self.assertEqual(spec.task_type, "code")

    def test_explicit_plan_type(self):
        spec = TaskSpec(task_id="t1", context={"task_spec": "test"}, task_type="plan")
        self.assertEqual(spec.task_type, "plan")

    def test_to_kwargs_includes_task_type(self):
        spec = TaskSpec(task_id="t1", context={"task_spec": "plan this"},
                        task_type="plan", tiers=["L0-Planner"])
        kwargs = spec.to_kwargs()
        self.assertEqual(kwargs["task_type"], "plan")
        self.assertEqual(kwargs["tiers"], ["L0-Planner"])


class TestOrchestratorPromptRouting(unittest.TestCase):

    def setUp(self):
        self.orchestrator = LLMOrchestrator()

    def test_code_prompt_template_loads(self):
        """Code template exists and contains expected sections."""
        prompt = self.orchestrator._get_agent_system_prompt("code")
        self.assertIn("ROLE", prompt)
        self.assertIn("file_read", prompt)
        self.assertIn("file_write", prompt)
        self.assertIn("Anti-Hallucination", prompt)

    def test_plan_prompt_template_loads(self):
        """Plan template exists and contains expected sections."""
        prompt = self.orchestrator._get_agent_system_prompt("plan")
        self.assertIn("ROLE", prompt)
        self.assertIn("Architecture", prompt)
        self.assertIn("## Tasks", prompt)
        self.assertIn("Brevity", prompt)

    def test_unknown_type_falls_back_to_inline(self):
        """Unknown task_type loads fallback."""
        prompt = self.orchestrator._get_agent_system_prompt("bogus_type")
        self.assertIn("write tool", prompt)
        self.assertIn("production-quality", prompt)

    def test_execute_with_judge_accepts_task_type(self):
        """execute_with_judge accepts and routes task_type."""
        orch = self.orchestrator
        orch.call_llm_with_retry = MagicMock()
        orch.call_llm_with_retry.return_value = {
            "success": True, "output": "plan output",
            "attempt": 1, "duration_seconds": 0.1,
        }
        orch.cost_tracker = MagicMock()
        orch.cost_tracker.get_summary.return_value = {"total_cost": 0}
        cb = MagicMock(); cb.can_execute.return_value = True
        reg = MagicMock(); reg.get.return_value = cb
        orch.circuit_breaker_registry = reg
        orch.notifier = MagicMock()

        from src.core.judge import Judge, Verdict
        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="Good plan",
            checks_passed=[], checks_failed=[],
        )):
            result = orch.execute_with_judge(
                task_id="plan-task",
                context={"task_spec": "Design auth module"},
                task_type="plan",
                tiers=["L0-Planner"],
            )

        self.assertTrue(result["success"])

    def test_execute_with_judge_defaults_to_code(self):
        """No task_type → defaults to code."""
        orch = self.orchestrator
        orch.call_llm_with_retry = MagicMock()
        orch.call_llm_with_retry.return_value = {
            "success": True, "output": "code output",
            "attempt": 1, "duration_seconds": 0.1,
        }
        orch.cost_tracker = MagicMock()
        orch.cost_tracker.get_summary.return_value = {"total_cost": 0}
        cb = MagicMock(); cb.can_execute.return_value = True
        reg = MagicMock(); reg.get.return_value = cb
        orch.circuit_breaker_registry = reg
        orch.notifier = MagicMock()

        from src.core.judge import Judge, Verdict
        with patch.object(Judge, "evaluate", return_value=Verdict(
            accepted=True, provisional=False, score=0.9, critique="Good code",
            checks_passed=[], checks_failed=[],
        )):
            result = orch.execute_with_judge(
                task_id="code-task",
                context={"task_spec": "Write fib function"},
            )

        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
