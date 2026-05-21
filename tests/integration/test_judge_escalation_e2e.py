#!/usr/bin/env python3
"""Integration tests for judge-based escalation — mocked at the HTTP layer.

Mocks requests.post to simulate the full pipeline:
HTTP → JSON parse → Judge evaluation → escalation decision.
No real API calls.
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


# ── Mock Helpers ──────────────────────────────────────────────────

def _mock_post_for_models(responses: dict):
    """Build a requests.post mock that routes by model name.

    Args:
        responses: dict mapping model substrings -> (content, status_code)
                   e.g. {"qwen3-coder-30b": ('{"score": 0.9, ...}', 200)}
    """
    def side_effect(url, **kwargs):
        payload = kwargs.get("json", {})
        model = payload.get("model", "")
        content = "Default response"
        status = 200
        for key, (c, s) in responses.items():
            if key in model:
                content = c
                status = s
                break
        mock = MagicMock()
        mock.status_code = status
        mock.json.return_value = {
            "choices": [{"message": {"content": content}}],
            "model": model,
        }
        return mock
    return side_effect


class TestJudgeEscalationE2E:
    """End-to-end tests mocking requests.post for the full pipeline."""

    def setup_method(self):
        """Fresh orchestrator for each test."""
        # Set fake API key so Judge doesn't fail before HTTP mock
        os.environ["OPENROUTER_API_KEY"] = "fake-key-for-e2e-tests"
        self.orchestrator = LLMOrchestrator()
        # Replace with fully mocked cost tracker
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {"daily_total": 0.0}
        self.orchestrator.cost_tracker = mock_ct
        # Replace with fully mocked circuit breaker
        mock_reg = MagicMock()
        mock_cb = MagicMock()
        mock_cb.can_execute.return_value = True
        mock_reg.get.return_value = mock_cb
        self.orchestrator.circuit_breaker_registry = mock_reg

    def teardown_method(self):
        """Clean up env var."""
        if os.environ.get("OPENROUTER_API_KEY") == "fake-key-for-e2e-tests":
            del os.environ["OPENROUTER_API_KEY"]

    # ── Scenario 1: L0 accepts first try ──────────────────────────

    def test_l0_accepts_first_try(self):
        """L0 returns good code, Judge accepts → success, 1 tier."""
        # Judge (L2-Coder) returns "accepted" verdict
        judge_json = json.dumps({
            "score": 0.9, "critique": "Excellent",
            "checks_passed": ["correctness", "completeness"],
            "checks_failed": [],
        })
        # L0-Coder returns good code output
        l0_output = "def solve(x): return x * 2"

        responses = {
            "qwen3-coder-30b": (l0_output, 200),      # L0-Coder call
            "anthropic/claude-sonnet-4.6": (judge_json, 200), # Judge call
        }

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            result = self.orchestrator.execute_with_judge(
                task_id="test_l0",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L0-Coder"
        assert result["attempts_total"] == 1
        assert result["verdict"].accepted is True

    # ── Scenario 2: L0 rejects, retry succeeds ─────────────────────

    def test_l0_rejects_retry_succeeds(self):
        """L0 output rejected by Judge, feedback injected, retry passes."""
        reject_json = json.dumps({
            "score": 0.3, "critique": "Missing edge case handling",
            "checks_passed": [], "checks_failed": ["correctness"],
        })
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good now",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        # L0-Coder called twice, Judge called twice
        responses = {
            "qwen3-coder-30b": [  # side_effect for L0 calls
                ("def foo(): pass", 200),
                ("def foo(x):\n    if x < 0: return 0\n    return x * 2", 200),
            ],
            "anthropic/claude-sonnet-4.6": [  # side_effect for judge calls
                (reject_json, 200),
                (accept_json, 200),
            ],
        }

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            # Find sequential response
            for key, seq in responses.items():
                if key in model:
                    if isinstance(seq, list) and seq:
                        content, status = seq.pop(0)
                    else:
                        content, status = seq
                    mock = MagicMock()
                    mock.status_code = status
                    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
                    return mock
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": "default"}}]}
            return mock

        with patch("requests.post", side_effect=side_effect):
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
        """L0 fails all 3 retries, NOTIFY_AND_ESCALATE, L1 accepts."""
        reject_json = json.dumps({
            "score": 0.3, "critique": "Bad",
            "checks_passed": [], "checks_failed": ["correctness"],
        })
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        # L0 gets called 3 times (all rejected), L1 once (accepted)
        # Judge gets called 4 times: 3 rejects + 1 accept
        judge_seqs = {
            "anthropic/claude-sonnet-4.6": [
                (reject_json, 200), (reject_json, 200), (reject_json, 200),
                (accept_json, 200),
            ],
        }
        coder_seqs = {
            "qwen3-coder-30b": [("L0 out", 200), ("L0 out", 200), ("L0 out", 200)],
            "x-ai/grok-4.3": [("L1 out", 200)],
        }

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            # Check judge sequences first
            for key, seq in judge_seqs.items():
                if key in model and seq:
                    content, status = seq.pop(0)
                    mock = MagicMock()
                    mock.status_code = status
                    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
                    return mock
            # Then coder sequences
            for key, seq in coder_seqs.items():
                if key in model and seq:
                    content, status = seq.pop(0)
                    mock = MagicMock()
                    mock.status_code = status
                    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
                    return mock
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": "default"}}]}
            return mock

        with patch("requests.post", side_effect=side_effect):
            result = self.orchestrator.execute_with_judge(
                task_id="test_escalate",
                context={"task_spec": "Complex task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        assert result["attempts_total"] >= 3  # at least L0 attempts

    # ── Scenario 4: FailNow skips all ──────────────────────────────

    def test_fail_now_skips_all(self):
        """set_fail_now('L1-Coder') → L0 skipped, L1 one-shot."""
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        set_fail_now("L1-Coder")
        try:
            responses = {
                "x-ai/grok-4.3": ("L1 direct output", 200),
            }

            with patch("requests.post", side_effect=_mock_post_for_models(responses)):
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
            # Also clear env var if set
            if "MRKRABS_FAIL_NOW" in os.environ:
                del os.environ["MRKRABS_FAIL_NOW"]

    # ── Scenario 5: HTTP failure on L0 → skips to L1 ──────────────

    def test_http_failure_l0_skips_to_l1(self):
        """L0 returns HTTP 500 → skips immediately to L1."""
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        responses = {
            "qwen3-coder-30b": ("error", 500),           # L0 fails
            "x-ai/grok-4.3": ("L1 output", 200),         # L1 succeeds
            "anthropic/claude-sonnet-4.6": (accept_json, 200),   # Judge (called for L1)
        }

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            result = self.orchestrator.execute_with_judge(
                task_id="test_http_fail",
                context={"task_spec": "Task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        # L0 should be in escalation path
        assert "L0-Coder" in result["escalation_path"]

    # ── Scenario 6: Judge JSON parse failure → degrades gracefully

    def test_judge_json_parse_failure(self):
        """Judge LLM returns malformed JSON → reject verdict, continue."""
        malformed = "This is definitely not JSON at all"

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            content = malformed if "claude" in model else "L0 output"
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": content}}]}
            return mock

        with patch("requests.post", side_effect=side_effect):
            result = self.orchestrator.execute_with_judge(
                task_id="test_json_fail",
                context={"task_spec": "Task"},
                tiers=["L0-Coder"],
                max_retries_per_tier=1,
            )

        # Should fail because Judge can't parse → all retries exhausted
        assert result["success"] is False
        assert result["attempts_total"] == 1

    # ── Scenario 7: Cost tracking via mock ────────────────────────

    def test_cost_tracking_called(self):
        """Cost tracker record() is called as observer."""
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        responses = {
            "qwen3-coder-30b": ("output", 200),
            "anthropic/claude-sonnet-4.6": (accept_json, 200),
        }

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            self.orchestrator.execute_with_judge(
                task_id="test_cost",
                context={"task_spec": "Task"},
                tiers=["L0-Coder"],
            )

        # cost_tracker.record() should have been called
        assert self.orchestrator.cost_tracker.record.called

    # ── Scenario 8: Feedback injection in retry prompt ────────────

    def test_feedback_in_retry_prompt(self):
        """Judge rejection critique appears in next retry's prompt."""
        reject_json = json.dumps({
            "score": 0.3, "critique": "NEEDS EDGE CASES",
            "checks_passed": [], "checks_failed": ["correctness"],
        })

        captured_prompts = []

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            messages = payload.get("messages", [])

            if "qwen3-coder-30b" in model:
                for msg in messages:
                    if msg.get("role") == "user":
                        captured_prompts.append(msg["content"])
                content = "L0 output"
            elif "claude" in model:
                content = reject_json  # Judge returns rejection
            else:
                content = "default"

            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": content}}]}
            return mock

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake-key-for-test"}), \
             patch("requests.post", side_effect=side_effect):
            self.orchestrator.execute_with_judge(
                task_id="test_feedback",
                context={"task_spec": "Write code"},
                tiers=["L0-Coder"],
                max_retries_per_tier=2,
            )

        assert len(captured_prompts) >= 2
        second_prompt = captured_prompts[1]
        assert "NEEDS EDGE CASES" in second_prompt
        assert "Previous Attempt Feedback" in second_prompt

    # ── Scenario 9: All tiers exhausted ───────────────────────────

    def test_all_tiers_exhausted(self):
        """Every tier fails every retry → total failure."""
        reject_json = json.dumps({
            "score": 0.2, "critique": "Terrible",
            "checks_passed": [], "checks_failed": ["everything"],
        })

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            content = reject_json if "claude" in model else f"{model} output"
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": content}}]}
            return mock

        with patch("requests.post", side_effect=side_effect):
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
        """Circuit breaker blocks L0 → skips to L1."""
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        # Block L0, allow L1
        cb_mock_l0 = MagicMock()
        cb_mock_l0.can_execute.return_value = False
        cb_mock_l1 = MagicMock()
        cb_mock_l1.can_execute.return_value = True
        self.orchestrator.circuit_breaker_registry.get.side_effect = [cb_mock_l0, cb_mock_l1]

        responses = {
            "x-ai/grok-4.3": ("L1 output", 200),
            "anthropic/claude-sonnet-4.6": (accept_json, 200),
        }

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            result = self.orchestrator.execute_with_judge(
                task_id="test_cb",
                context={"task_spec": "Task"},
                tiers=["L0-Coder", "L1-Coder"],
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        assert "L0-Coder" in result["escalation_path"]

    # ── Scenario 11: FailUp bumps exactly one tier ─────────────────

    def test_fail_up_bumps_one_tier(self):
        """FailUp active → L0 aborted immediately, L1 runs normal escalation."""
        accept_json = json.dumps({
            "score": 0.9, "critique": "Good",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        set_fail_up()
        try:
            responses = {
                "x-ai/grok-4.3": ("L1 output", 200),
                "anthropic/claude-sonnet-4.6": (accept_json, 200),
            }

            with patch("requests.post", side_effect=_mock_post_for_models(responses)):
                result = self.orchestrator.execute_with_judge(
                    task_id="test_fail_up",
                    context={"task_spec": "Task"},
                    tiers=["L0-Coder", "L1-Coder", "L2-Coder"],
                )

            assert result["success"] is True
            assert result["tier_used"] == "L1-Coder"
            # L0 should be in escalation_path but no attempts on it
            assert "L0-Coder" in result["escalation_path"]
            assert result["retries_per_tier"].get("L0-Coder", 0) == 0
        finally:
            clear_fail_up()
            if "MRKRABS_FAIL_UP" in os.environ:
                del os.environ["MRKRABS_FAIL_UP"]

    # ── Scenario 12: All L0/L1/L2 exhausted → Principal escalation ─

    def test_all_tiers_exhausted_escalates_to_principal(self):
        """L0, L1, L2 all fail → control returns to Principal Agent."""
        reject_json = json.dumps({
            "score": 0.2, "critique": "Bad",
            "checks_passed": [], "checks_failed": ["correctness"],
        })

        def side_effect(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            content = reject_json if "claude" in model else f"{model} output"
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {"choices": [{"message": {"content": content}}]}
            return mock

        with patch("requests.post", side_effect=side_effect):
            result = self.orchestrator.execute_with_judge(
                task_id="test_principal",
                context={"task_spec": "Solve P vs NP"},
                tiers=["L0-Coder", "L1-Coder", "L2-Coder", "Principal"],
                max_retries_per_tier=1,
            )

        assert result["success"] is False
        assert result.get("escalated_to_principal") is True
        assert result["tier_used"] == "Principal"
        assert "Principal" in result["escalation_path"]
        assert result["escalation_context"]["task"] == "Solve P vs NP"
        assert len(result["escalation_context"]["tiers_attempted"]) == 3


    # ── Test 1: Judge model routing respects judge_model_param ──────────────

    def test_judge_model_routing_respects_judge_model_param(self):
        """Judge uses a different model than the agent tier."""
        judge_json = json.dumps({
            "score": 0.9, "critique": "Excellent",
            "checks_passed": ["correctness", "completeness"],
            "checks_failed": [],
        })
        l0_output = "def solve(x): return x * 2"

        # Capture all requests.post calls to inspect model names
        calls = []

        def capturing_post(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            calls.append({"url": url, "model": model})

            # Route to correct mock response
            mock = MagicMock()
            if "qwen3-coder" in model:
                content = l0_output
                mock.status_code = 200
            elif "claude" in model:
                content = judge_json
                mock.status_code = 200
            else:
                content = judge_json
                mock.status_code = 200
            mock.json.return_value = {
                "choices": [{"message": {"content": content}}],
                "model": model,
            }
            return mock

        with patch("requests.post", side_effect=capturing_post):
            result = self.orchestrator.execute_with_judge(
                task_id="test_judge_routing",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        models_used = [c["model"] for c in calls]
        assert any("qwen3-coder" in m for m in models_used), \
            f"Expected qwen3-coder model in {models_used}"
        assert any("claude" in m for m in models_used), \
            f"Expected claude model in {models_used}"

    # ── Test 2: Tool executor invoked before judge ────────────────────────

    def test_tool_executor_invoked_before_judge(self):
        """Tool executor parses and executes file_write before judge evaluation."""
        judge_json = json.dumps({
            "score": 0.9, "critique": "Excellent",
            "checks_passed": ["correctness", "completeness"],
            "checks_failed": [],
        })
        # Output with a plain-text file_write pattern the tool executor recognizes
        l0_output = 'file_write("test_output.py", "def solve(): return 42")'

        responses = {
            "qwen3-coder-30b": (l0_output, 200),
            "anthropic/claude-sonnet": (judge_json, 200),
        }

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            result = self.orchestrator.execute_with_judge(
                task_id="test_tool_execution",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        # Tool executor either parsed tools or returned empty results
        assert result.get("tool_results") is not None

    # ── Test 3: Cost tracker receives token estimates ──────────────────────

    def test_cost_tracker_receives_token_estimates(self):
        """Cost tracker records token estimates for prompt and completion."""
        judge_json = json.dumps({
            "score": 0.9, "critique": "Excellent",
            "checks_passed": ["correctness", "completeness"],
            "checks_failed": [],
        })
        l0_output = "A" * 100

        responses = {
            "qwen3-coder-30b": (l0_output, 200),
            "anthropic/claude-sonnet": (judge_json, 200),
        }

        # Create a fresh MagicMock that will track record() calls
        mock_ct = MagicMock()
        mock_ct.get_summary.return_value = {"daily_total": 0.0}
        self.orchestrator.cost_tracker = mock_ct

        with patch("requests.post", side_effect=_mock_post_for_models(responses)):
            result = self.orchestrator.execute_with_judge(
                task_id="test_cost_tracking",
                context={"task_spec": "Write a function"},
                tiers=["L0-Coder"],
            )

        assert result["success"] is True
        # cost_tracker.record should have been called for the agent call
        assert mock_ct.record.called, "Expected cost_tracker.record to be called"

    # ── Test 4: Notifier fires on escalation with correct urgency ───────────

    def test_notifier_fires_on_escalation_with_correct_urgency(self):
        """Notifier fires per-tier with urgency='normal' when escalating.

        After the fix, failure_action dispatches inside the for-tier loop.
        L0 fails → notifier fires → escalation continues to L1 which succeeds.
        """
        reject_json = json.dumps({
            "score": 0.3, "critique": "Bad",
            "checks_passed": [], "checks_failed": ["correctness"],
        })
        accept_json = json.dumps({
            "score": 0.9, "critique": "Excellent",
            "checks_passed": ["correctness"], "checks_failed": [],
        })

        # Track call order so judge returns reject first, accept second
        judge_calls = [0]

        def sequential_post(url, **kwargs):
            payload = kwargs.get("json", {})
            model = payload.get("model", "")
            mock = MagicMock()
            mock.status_code = 200

            if "qwen3-coder" in model:
                content = "L0 output"
            elif "grok" in model:
                content = "L1 output"
            elif "claude" in model:
                # First judge call: reject, second: accept
                judge_calls[0] += 1
                content = reject_json if judge_calls[0] == 1 else accept_json
            else:
                content = accept_json

            mock.json.return_value = {
                "choices": [{"message": {"content": content}}],
                "model": model,
            }
            return mock

        mock_notifier = MagicMock()
        self.orchestrator.notifier = mock_notifier

        with patch("src.core.orchestrator.get_tier_failure_action",
                   return_value=FailureAction.NOTIFY_AND_ESCALATE), \
             patch("requests.post", side_effect=sequential_post):
            result = self.orchestrator.execute_with_judge(
                task_id="test_notifier_urgency",
                context={"task_spec": "Complex task"},
                tiers=["L0-Coder", "L1-Coder"],
                max_retries_per_tier=1,
            )

        assert result["success"] is True
        assert result["tier_used"] == "L1-Coder"
        mock_notifier.send.assert_called()
        call_kwargs = mock_notifier.send.call_args.kwargs
        assert call_kwargs.get("urgency") == "normal", \
            f"Expected urgency='normal', got {call_kwargs.get('urgency')}"


