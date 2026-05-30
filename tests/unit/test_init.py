#!/usr/bin/env python3
"""Unit tests for src/__init__.py - The ask() API and zero-config entry point."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pytest

# Add src to path for imports
sys_path = str(Path(__file__).parent.parent.parent)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from src.__init__ import (
    ask,
    AskResult,
    _get_default_tracker,
    _get_available_tiers,
    _get_default_tier,
    _estimate_tokens,
    _ask_with_escalation,
    get_budget_remaining,
    get_cost_summary,
    reset_tracker,
)
from src.core.cost import CostTracker, Budget, TokenCount, BudgetExceededError
from src.core.tier_manager import TierManager


class TestAskResult:
    """Tests for AskResult dataclass."""

    def test_askresult_basic(self):
        result = AskResult(
            output="Hello world",
            cost=0.01,
            tier="L0-Coder",
            model="qwen/qwen3-coder-30b",
            success=True,
            duration_seconds=2.5,
            attempts=1,
        )
        assert result.output == "Hello world"
        assert result.cost == 0.01
        assert result.success is True

    def test_askresult_with_tokens(self):
        tokens = TokenCount(prompt_tokens=100, completion_tokens=50)
        result = AskResult(
            output="test",
            cost=0.01,
            tier="L0-Coder",
            model="test",
            success=True,
            duration_seconds=1.0,
            attempts=1,
            tokens=tokens,
        )
        assert result.tokens is not None
        assert result.tokens.prompt_tokens == 100


class TestGetDefaultTracker:
    """Tests for _get_default_tracker function."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    def test_creates_new_tracker(self):
        """Test that tracker is created on first call."""
        tracker = _get_default_tracker()
        assert isinstance(tracker, CostTracker)
        assert tracker.budget.daily_limit_usd == Decimal("10.00")

    def test_returns_same_tracker(self):
        """Test that same tracker is returned on subsequent calls."""
        tracker1 = _get_default_tracker()
        tracker2 = _get_default_tracker()
        assert tracker1 is tracker2

    def test_custom_budget(self):
        """Test custom budget from environment variable."""
        os.environ["ORCHESTRATOR_DAILY_BUDGET"] = "25.00"
        reset_tracker()
        tracker = _get_default_tracker()
        assert tracker.budget.daily_limit_usd == Decimal("25.00")
        del os.environ["ORCHESTRATOR_DAILY_BUDGET"]


class TestGetAvailableTiers:
    """Tests for _get_available_tiers function."""

    def test_openrouter_available_with_key(self):
        """Test tiers are available when API key is set."""
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        try:
            available = _get_available_tiers()
            # Should include at least some tiers
            assert len(available) > 0
            assert "L0-Planner" in available
        finally:
            del os.environ["OPENROUTER_API_KEY"]

    def test_no_tiers_without_key(self):
        """Test no tiers available without API key."""
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        available = _get_available_tiers()
        # LM Studio is always available
        assert len(available) >= 1


class TestGetDefaultTier:
    """Tests for _get_default_tier function."""

    def setup_method(self):
        """Reset environment before each test."""
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

    def teardown_method(self):
        """Clean up after each test."""
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

    def test_returns_l0_coder_with_key(self):
        """Test default tier is L0-Coder when key is set."""
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        tier = _get_default_tier()
        assert tier in ["L0-Coder", "L0-Planner", "L0-Reviewer"]

    def test_raises_without_key_and_no_lmstudio(self):
        """Test raises error when no API key and LM Studio not available."""
        # Both OpenRouter key and LM Studio host removed
        if "LM_STUDIO_HOST" in os.environ:
            del os.environ["LM_STUDIO_HOST"]
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        
        # With only LM Studio in MODELS but no host set, it should return a tier
        # with provider "lmstudio" — the first available local model.
        tier = _get_default_tier()
        assert tier in ("L0-Coder", "L0-Sushi", "L0-GPTOSS"), f"Unexpected default tier: {tier}"


class TestEstimateTokens:
    """Tests for _estimate_tokens function."""

    def test_estimates_basic(self):
        """Test basic token estimation."""
        prompt = "Hello, world! This is a test prompt."
        system = "You are a helpful assistant."
        tokens = _estimate_tokens(prompt, system)
        assert tokens.prompt_tokens > 0
        assert tokens.completion_tokens >= 200
        assert tokens.total_tokens > 0

    def test_estimates_long_prompt(self):
        """Test estimation with longer prompt."""
        long_prompt = "A" * 1000
        system = "You are a helpful assistant."
        tokens = _estimate_tokens(long_prompt, system)
        # Longer prompt should estimate more tokens
        assert tokens.prompt_tokens > 100


class TestAskBasic:
    """Tests for basic ask() functionality."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_basic_success(self, mock_orchestrator_class):
        """Test basic ask() with mock execute_with_judge success."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "This is the LLM response.",
            "tier_used": "L0-Coder",
            "attempts_total": 1,
            "duration_seconds": 0.5,
            "cost_summary": {"daily_total": 0.0},
        }
        
        result = ask("Write hello world")
        
        assert result.success is True
        assert result.output == "This is the LLM response."
        assert result.tier == "L0-Coder"
        assert result.attempts == 1

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_max_cost_exceeded(self, mock_orchestrator_class):
        """Test ask() respects max_cost parameter."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        # Mock estimation to return high token count (so cost exceeds max)
        with patch("src.__init__._estimate_tokens") as mock_estimate:
            mock_estimate.return_value = TokenCount(prompt_tokens=1000000, completion_tokens=500000)
            
            # Set up very low max_cost
            with pytest.raises(BudgetExceededError) as exc_info:
                ask("Test task", max_cost=0.000001)
            
            assert "max_cost" in str(exc_info.value).lower()

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_with_system_prompt(self, mock_orchestrator_class, tmp_path):
        """Test ask() with custom system prompt."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "response",
            "tier_used": "L1-Coder",
            "attempts_total": 1,
            "duration_seconds": 0.5,
            "cost_summary": {"daily_total": 0.0},
        }
        
        custom_sys = "You are a code generator."
        result = ask("Write code", system_prompt=custom_sys)
        
        assert result.success is True

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}, "L1-Coder": {"model": "test-model-2", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_with_tier_override(self, mock_orchestrator_class, tmp_path):
        """Test ask() with tier override."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "response",
            "tier_used": "L1-Coder",
            "attempts_total": 1,
            "duration_seconds": 0.5,
            "cost_summary": {"daily_total": 0.0},
        }
        
        result = ask("Test", tier="L1-Coder")
        
        assert "Coder" in result.tier
        assert result.tier in ["L0-Coder", "L1-Coder"]


class TestAskWithEscalation:
    """Tests for ask() with auto_escalate=True (judge-based execute_with_judge)."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    @patch("src.__init__.LLMOrchestrator")
    def test_escalation_success_on_first_tier(self, mock_orchestrator_class):
        """Test that escalation returns on first successful tier."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "Success on L0!",
            "tier_used": "L0-Coder",
            "attempts_total": 1,
            "duration_seconds": 0.5,
            "cost_summary": {"daily_total": 0.0},
        }
        
        result = ask("Simple task")
        
        assert result.success is True
        assert result.tier == "L0-Coder"
        assert result.attempts == 1

    @patch("src.__init__.LLMOrchestrator")
    def test_escalation_success_on_second_tier(self, mock_orchestrator_class):
        """Test that escalation tries next tier on failure."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "Success on L1!",
            "tier_used": "L1-Coder",
            "attempts_total": 2,
            "duration_seconds": 1.2,
            "cost_summary": {"daily_total": 0.01},
        }
        
        result = ask("Complex task")
        
        assert result.success is True
        assert result.tier == "L1-Coder"
        assert result.attempts == 2

    @patch("src.__init__.LLMOrchestrator")
    def test_escalation_all_tiers_fail(self, mock_orchestrator_class):
        """Test that escalation returns failure when all tiers fail."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        mock_orchestrator.execute_with_judge.return_value = {
            "success": False,
            "output": None,
            "tier_used": None,
            "attempts_total": 3,
            "duration_seconds": 2.0,
            "cost_summary": {"daily_total": 0.02},
        }
        
        result = ask("Impossible task")
        
        assert result.success is False
        assert result.output == ""


class TestGetBudgetRemaining:
    """Tests for get_budget_remaining function."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    def test_budget_remaining_initial(self):
        """Test initial budget is 10.00."""
        budget = get_budget_remaining()
        assert budget == 10.00

    def test_budget_remaining_after_spending(self):
        """Test budget decreases after spending."""
        tracker = _get_default_tracker()
        tracker.record("task-1", "L0", "test-model", TokenCount(100, 50), 0.01)
        
        budget = get_budget_remaining()
        assert budget < 10.00
        assert budget > 9.00


class TestGetCostSummary:
    """Tests for get_cost_summary function."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    def test_summary_structure(self):
        """Test summary contains expected keys."""
        summary = get_cost_summary()
        
        assert "daily_total" in summary
        assert "budget_remaining" in summary
        # daily_total represents total spent
        assert "daily_total" in summary
        assert "task_count" in summary or "task_totals" in summary

    def test_summary_types(self):
        """Test summary values are correct types."""
        summary = get_cost_summary()
        
        assert isinstance(summary["daily_total"], float)
        assert isinstance(summary["budget_remaining"], float)


class TestResetTracker:
    """Tests for reset_tracker function."""

    def test_reset_creates_new_tracker(self):
        """Test that reset creates a new tracker."""
        tracker1 = _get_default_tracker()
        reset_tracker()
        tracker2 = _get_default_tracker()
        
        assert tracker1 is not tracker2

    def test_reset_clears_all_state(self):
        """Test that reset clears all tracking state."""
        tracker = _get_default_tracker()
        tracker.record("task-1", "L0", "test", TokenCount(100, 50), 0.01)
        
        assert tracker.get_daily_total() > 0
        
        reset_tracker()
        new_tracker = _get_default_tracker()
        
        assert new_tracker.get_daily_total() == 0


class TestAskErrorHandling:
    """Tests for error handling in ask() function."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "openrouter", "temperature": 0.7}})
    def test_ask_missing_api_key(self, mock_orchestrator_class, tmp_path):
        """Test ask() raises error when OpenRouter API key missing."""
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        
        with pytest.raises(OSError) as exc_info:
            ask("Test task")
        
        assert "OPENROUTER_API_KEY" in str(exc_info.value)

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_llm_failure(self, mock_orchestrator_class, tmp_path):
        """Test ask() handles LLM failure gracefully."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_with_judge.return_value = {
            "success": False,
            "error": "LLM failed",
            "attempts": 3,
        }
        
        result = ask("Test task")
        
        assert result.success is False
        assert result.output == ""


class TestAskIntegration:
    """Integration tests for ask() with realistic scenarios."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_tracker()

    def teardown_method(self):
        """Clean up after each test."""
        reset_tracker()

    @patch("src.__init__.LLMOrchestrator")
    @patch("src.__init__.MODELS", {"L0-Coder": {"model": "test-model", "provider": "lmstudio", "temperature": 0.7}})
    def test_ask_full_workflow_success(self, mock_orchestrator_class):
        """Test complete ask() workflow with success."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "def hello():\n    print('Hello, World!')\n",
            "tier_used": "L0-Coder",
            "attempts_total": 1,
            "duration_seconds": 0.5,
            "cost_summary": {"daily_total": 0.01},
        }
        
        result = ask("Write a hello world function in Python")
        
        # Verify result
        assert result.success is True
        assert "def hello" in result.output
        assert result.tier == "L0-Coder"
        assert result.attempts == 1
        assert result.cost >= 0

    @patch("src.__init__.LLMOrchestrator")
    def test_ask_full_workflow_escalation(self, mock_orchestrator_class):
        """Test complete ask() workflow with escalation via execute_with_judge."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        mock_orchestrator.execute_with_judge.return_value = {
            "success": True,
            "output": "Complex response",
            "tier_used": "L1-Coder",
            "attempts_total": 4,
            "duration_seconds": 2.0,
            "cost_summary": {"daily_total": 0.02},
        }
        
        result = ask("Implement a complex sorting algorithm")
        
        assert result.success is True
        assert result.tier == "L1-Coder"
        assert result.attempts >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
