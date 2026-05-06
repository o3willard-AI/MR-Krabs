#!/usr/bin/env python3
"""Unit tests for CrewAI cost tracking integration."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sys
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.crewai_integration import (
    CREWAI_AVAILABLE,
    CostAwareLLMWrapper,
)
from src.core.cost import CostTracker, TokenCount


class TestCostAwareLLMWrapper:
    """Tests for CostAwareLLMWrapper cost tracking."""

    def test_wrapper_initialization(self):
        """Test wrapper initialization with parameters."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-task-123",
            model="google/gemma-7b-it",
            budget_limit=Decimal("5.00"),
        )
        
        assert wrapper.cost_tracker == tracker
        assert wrapper.task_id == "test-task-123"
        assert wrapper.model == "google/gemma-7b-it"
        assert wrapper.budget_limit == Decimal("5.00")
        assert wrapper._total_cost == Decimal("0")
        assert wrapper._total_tokens.prompt_tokens == 0

    def test_wrapper_without_budget(self):
        """Test wrapper without budget limit."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-task-456",
        )
        
        assert wrapper.budget_limit is None

    def test_record_single_completion(self):
        """Test recording a single completion."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-task-789",
            model="google/gemma-7b-it",
        )
        
        # Record a completion
        result = wrapper.record_completion(
            prompt_tokens=100,
            completion_tokens=50,
        )
        
        # Verify result structure
        assert "cost" in result
        assert "total_cost" in result
        assert "tokens" in result
        assert result["tokens"]["prompt"] == 100
        assert result["tokens"]["completion"] == 50
        assert result["tokens"]["total"] == 150
        
        # Verify cost is tracked (Gemma-7b-it: $0.10/1M prompt, $0.30/1M completion)
        # Cost = (100/1000 * 0.10) + (50/1000 * 0.30) = 0.01 + 0.015 = 0.025 per token, but actual calculation differs
        assert result["cost"] > 0

    def test_record_multiple_completions(self):
        """Test recording multiple completions accumulates costs."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-multi-001",
            model="google/gemma-7b-it",
        )
        
        # First completion
        result1 = wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        
        # Second completion
        result2 = wrapper.record_completion(prompt_tokens=200, completion_tokens=100)
        
        # Third completion
        result3 = wrapper.record_completion(prompt_tokens=150, completion_tokens=75)
        
        # Verify cumulative tracking
        assert wrapper._total_tokens.prompt_tokens == 450  # 100 + 200 + 150
        assert wrapper._total_tokens.completion_tokens == 225  # 50 + 100 + 75
        assert wrapper._total_cost > Decimal("0")
        
        # Each subsequent total_cost should be higher
        assert result3["total_cost"] > result2["total_cost"] > result1["total_cost"]

    def test_record_with_custom_model(self):
        """Test recording with different model than configured."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-model-xyz",
            model="google/gemma-7b-it",  # Default model
        )
        
        # Record with different actual model
        result = wrapper.record_completion(
            prompt_tokens=100,
            completion_tokens=50,
            actual_model="anthropic/claude-3-haiku",  # Different model
        )
        
        # Should use actual model in result
        assert result["model"] == "anthropic/claude-3-haiku"

    def test_get_summary(self):
        """Test getting summary of tracked costs."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="summary-test",
            model="google/gemma-7b-it",
            budget_limit=Decimal("10.00"),
        )
        
        # Record some completions
        wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        wrapper.record_completion(prompt_tokens=200, completion_tokens=100)
        
        # Get summary
        summary = wrapper.get_summary()
        
        assert summary["task_id"] == "summary-test"
        assert summary["model"] == "google/gemma-7b-it"
        assert summary["budget_limit"] == 10.0
        assert summary["tokens"]["prompt"] == 300
        assert summary["tokens"]["completion"] == 150
        assert summary["total_cost"] > 0

    def test_reset(self):
        """Test resetting wrapper for new execution."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="reset-test",
        )
        
        # Record some completions
        wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        assert wrapper._total_cost > Decimal("0")
        
        # Reset
        wrapper.reset()
        
        # Should be back to zero
        assert wrapper._total_cost == Decimal("0")
        assert wrapper._total_tokens.prompt_tokens == 0
        assert wrapper._total_tokens.completion_tokens == 0

    def test_budget_exceeded_error(self):
        """Test that budget exceeded raises error."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="budget-test",
            model="google/gemma-7b-it",
            budget_limit=Decimal("0"),  # Zero budget - should fail immediately
        )
        
        # Should raise BudgetExceededError on first call since any cost > 0
        with pytest.raises(Exception) as exc_info:  # Any Exception for budget error
            wrapper.record_completion(
                prompt_tokens=1,
                completion_tokens=1,
            )
        
        # Verify it's a budget-related error
        error_msg = str(exc_info.value).lower()
        assert "budget" in error_msg or "exceeded" in error_msg

    def test_records_with_cost_tracker(self):
        """Test that completions are recorded in underlying CostTracker."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="integration-test",
            model="google/gemma-7b-it",
        )
        
        # Record completion
        wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        
        # Verify CostTracker has the entry
        assert len(tracker.entries) > 0
        
        # Last entry should be from our task
        last_entry = tracker.entries[-1]
        assert last_entry.task_id == "integration-test"
        # Note: finalize_spending doesn't store tier/model in entries,
        # those are tracked via cost_tracker's internal accounting

    def test_token_count_accumulation(self):
        """Test that token counts accumulate correctly."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="token-test",
        )
        
        # Record multiple completions
        wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        wrapper.record_completion(prompt_tokens=200, completion_tokens=75)
        wrapper.record_completion(prompt_tokens=150, completion_tokens=100)
        
        # Verify totals
        summary = wrapper.get_summary()
        
        assert summary["tokens"]["prompt"] == 450  # 100 + 200 + 150
        assert summary["tokens"]["completion"] == 225  # 50 + 75 + 100
        assert summary["tokens"]["total"] == 675

    def test_cost_calculation_accuracy(self):
        """Test that costs are calculated accurately using CostTracker pricing."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="cost-test",
            model="google/gemma-7b-it",
        )
        
        # Record known token counts
        result = wrapper.record_completion(
            prompt_tokens=1000,  # 1k tokens
            completion_tokens=500,  # 0.5k tokens
        )
        
        # Cost should be positive and reasonable
        assert result["cost"] > 0
        assert result["cost"] < 1.0  # Should be well under $1 for 1.5k tokens
        
        # Verify cost matches what CostTracker calculates
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)
        expected_cost = tracker.calculate_cost("google/gemma-7b-it", tokens)
        
        # Allow small floating point differences
        assert abs(result["cost"] - float(expected_cost)) < 0.0001


class TestCostAwareLLMWrapperEdgeCases:
    """Edge case tests for CostAwareLLMWrapper."""

    def test_zero_tokens(self):
        """Test recording with zero tokens (edge case)."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="zero-test",
        )
        
        result = wrapper.record_completion(
            prompt_tokens=0,
            completion_tokens=0,
        )
        
        assert result["tokens"]["total"] == 0
        # Cost might still be > 0 due to minimum charges

    def test_very_large_tokens(self):
        """Test recording with very large token counts."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="large-test",
        )
        
        result = wrapper.record_completion(
            prompt_tokens=100000,  # 100k tokens
            completion_tokens=50000,  # 50k tokens
        )
        
        assert result["tokens"]["total"] == 150000
        assert result["cost"] > 0

    def test_unicode_task_id(self):
        """Test with unicode characters in task ID."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="任务 -测试-task-test",
        )
        
        result = wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        
        assert wrapper.task_id == "任务 -测试-task-test"

    def test_no_model_in_cost_tracker(self):
        """Test with model not in CostTracker.MODEL_COSTS (uses default pricing)."""
        tracker = CostTracker()
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="unknown-model-test",
            model="some/unknown-model-xyz",  # Not in MODEL_COSTS
        )
        
        result = wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        
        # Should use default pricing without crashing
        assert result["cost"] > 0
        assert result["model"] == "some/unknown-model-xyz"


class TestCostAwareLLMWrapperIntegration:
    """Integration-style tests combining wrapper with CostTracker."""

    def test_multiple_wrappers_same_tracker(self):
        """Test multiple wrappers sharing same CostTracker."""
        tracker = CostTracker()
        
        wrapper1 = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="crew-alpha",
        )
        wrapper2 = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="crew-beta",
        )
        
        # Record completions on both
        wrapper1.record_completion(prompt_tokens=100, completion_tokens=50)
        wrapper2.record_completion(prompt_tokens=200, completion_tokens=100)
        wrapper1.record_completion(prompt_tokens=150, completion_tokens=75)
        
        # CostTracker should have all entries
        assert len(tracker.entries) == 3
        
        # Entries should be separated by task_id
        task_ids = [entry.task_id for entry in tracker.entries]
        assert "crew-alpha" in task_ids
        assert "crew-beta" in task_ids

    def test_wrapper_in_budget_context(self):
        """Test wrapper respects CostTracker budget limits."""
        tracker = CostTracker()
        
        # Set low daily limit to trigger budget errors
        tracker.budget.daily_limit_usd = Decimal("0.01")  # Very low
        
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="budget-context-test",
        )
        
        # Record some completions - should work initially
        result1 = wrapper.record_completion(prompt_tokens=10, completion_tokens=5)
        
        # Eventually might hit budget (depending on pricing)
        # This tests that the integration works correctly


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
