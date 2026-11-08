"""Unit tests for LLMOrchestrator._system_prompt_for_backend (wi-LG-REFACTOR-1).

The gate: for a tier in each backend class, the method must return the
SAME prompt string execute_with_judge would have used for that attempt
(same template the loop selects under has_opencode / has_pi / raw,
including the fix-prompt switch on feedback retries).

execute_with_judge is deliberately NOT rewired to this method in this
slice (extraction + tests only), so equality here is asserted against
the getters the loop calls, not against the loop itself.
"""

import unittest

from src.core.orchestrator import LLMOrchestrator


def make_orchestrator(opencode_tiers=(), pi_tiers=()):
    orch = LLMOrchestrator()
    orch.opencode_models = {t.lower(): "oc-model" for t in opencode_tiers}
    orch.pi_models = {t.lower(): "pi-model" for t in pi_tiers}
    return orch


class TestSystemPromptForBackend(unittest.TestCase):
    def test_opencode_tier_no_feedback_uses_build_agent_prompt(self):
        orch = make_orchestrator(opencode_tiers=["l0-coder"])
        self.assertEqual(
            orch._system_prompt_for_backend("l0-coder"),
            orch._get_agent_system_prompt("code"),
        )

    def test_opencode_tier_with_feedback_uses_fix_agent_prompt(self):
        orch = make_orchestrator(opencode_tiers=["l0-coder"])
        self.assertEqual(
            orch._system_prompt_for_backend("l0-coder", has_feedback=True),
            orch._get_agent_system_prompt("fix"),
        )

    def test_pi_tier_no_feedback_uses_pi_prompt(self):
        orch = make_orchestrator(pi_tiers=["l1-coder"])
        self.assertEqual(
            orch._system_prompt_for_backend("l1-coder"),
            orch._get_pi_system_prompt("code"),
        )

    def test_pi_tier_with_feedback_uses_pi_fix_prompt(self):
        orch = make_orchestrator(pi_tiers=["l1-coder"])
        self.assertEqual(
            orch._system_prompt_for_backend("l1-coder", has_feedback=True),
            orch._get_pi_system_prompt("fix"),
        )

    def test_raw_tier_uses_agent_prompt_without_feedback(self):
        orch = make_orchestrator()
        self.assertEqual(
            orch._system_prompt_for_backend("l2-coder"),
            orch._get_agent_system_prompt("code"),
        )

    def test_raw_tier_keeps_build_prompt_with_feedback(self):
        # The subtle one: execute_with_judge passes agent_system_prompt
        # (build prompt) to call_llm_with_retry on EVERY attempt,
        # including feedback retries -- only the OpenCode/PI branches
        # switch to the fix template. The helper must match.
        orch = make_orchestrator()
        self.assertEqual(
            orch._system_prompt_for_backend("l2-coder", has_feedback=True),
            orch._get_agent_system_prompt("code"),
        )

    def test_opencode_wins_over_pi_when_tier_in_both(self):
        # Matches the loop's if/elif order: OpenCode checked first.
        orch = make_orchestrator(opencode_tiers=["l0-coder"], pi_tiers=["l0-coder"])
        self.assertEqual(
            orch._system_prompt_for_backend("l0-coder"),
            orch._get_agent_system_prompt("code"),
        )

    def test_task_type_passthrough(self):
        orch = make_orchestrator()
        self.assertEqual(
            orch._system_prompt_for_backend("l2-coder", task_type="plan"),
            orch._get_agent_system_prompt("plan"),
        )

    def test_fix_and_build_prompts_are_distinct_templates(self):
        # Guards the test itself: if the fix/build templates ever
        # collapsed to identical strings, the feedback tests above
        # would pass vacuously. They are distinct files in the repo.
        orch = make_orchestrator()
        self.assertNotEqual(
            orch._get_agent_system_prompt("code"),
            orch._get_agent_system_prompt("fix"),
        )
        self.assertNotEqual(
            orch._get_pi_system_prompt("code"),
            orch._get_pi_system_prompt("fix"),
        )

    def test_pi_prompt_differs_from_agent_prompt(self):
        # The PI branch must not accidentally return the agent prompt
        # (the loop's pi template carries the write-tool directive).
        orch = make_orchestrator(pi_tiers=["l1-coder"])
        self.assertNotEqual(
            orch._system_prompt_for_backend("l1-coder"),
            orch._get_agent_system_prompt("code"),
        )


if __name__ == "__main__":
    unittest.main()
