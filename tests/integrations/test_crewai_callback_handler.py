#!/usr/bin/env python3
"""Unit tests for CostTrackingCallbackHandler - automatic cost tracking."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sys
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.crewai_integration import (
    CostTrackingCallbackHandler,
    CostAwareLLMWrapper,
    CREWAI_AVAILABLE,
)
from src.core.cost import CostTracker


@pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
class TestCostTrackingCallbackHandler:
    """Tests for automatic cost tracking via CrewAI callbacks."""

    @pytest.fixture
    def wrapper(self):
        """Create a CostAwareLLMWrapper for testing."""
        tracker = CostTracker()
        return CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="test-crew-callback",
            model="google/gemma-7b-it",
        )

    @pytest.fixture
    def callback(self, wrapper):
        """Create a callback handler."""
        return CostTrackingCallbackHandler(wrapper)

    def test_callback_initializes_with_wrapper(self, wrapper):
        """Test that callback stores the wrapper reference."""
        callback = CostTrackingCallbackHandler(wrapper)
        assert callback.wrapper == wrapper

    def test_on_llm_start_does_nothing(self, callback):
        """Test that on_llm_start is a no-op."""
        result = callback.on_llm_start(task="test")
        assert result is None

    def test_on_llm_end_tracks_dict_usage(self, callback, wrapper):
        """Test tracking when llm_output is a dictionary with usage."""
        # Simulate CrewAI callback with dict output
        callback.on_llm_end(
            llm_output={
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                },
                "model": "google/gemma-7b-it",
            }
        )

        # Check that wrapper recorded it
        assert wrapper._total_tokens.prompt_tokens == 100
        assert wrapper._total_tokens.completion_tokens == 50
        assert wrapper._total_tokens.total_tokens == 150
        assert wrapper._total_cost > Decimal("0")

    def test_on_llm_end_tracks_kwargs_usage(self, callback, wrapper):
        """Test tracking when usage is in kwargs."""
        callback.on_llm_end(
            prompt_tokens=200,
            completion_tokens=100,
            model="google/gemma-7b-it",
        )

        assert wrapper._total_tokens.prompt_tokens == 200
        assert wrapper._total_tokens.completion_tokens == 100
        assert wrapper._total_tokens.total_tokens == 300

    def test_on_llm_end_tracks_positional_arg(self, callback, wrapper):
        """Test tracking with positional argument (older CrewAI versions)."""
        llm_output = MagicMock()
        llm_output.usage.prompt_tokens = 150
        llm_output.usage.completion_tokens = 75
        llm_output.model = "google/gemma-7b-it"

        callback.on_llm_end(llm_output)

        assert wrapper._total_tokens.prompt_tokens == 150
        assert wrapper._total_tokens.completion_tokens == 75
        assert wrapper._total_cost > Decimal("0")

    def test_on_llm_end_ignores_zero_tokens(self, callback, wrapper):
        """Test that zero token calls are ignored."""
        initial_cost = wrapper._total_cost
        initial_tokens = wrapper._total_tokens.total_tokens

        callback.on_llm_end(
            llm_output={
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            }
        )

        # Should not update tracking if no tokens
        assert wrapper._total_cost == initial_cost
        assert wrapper._total_tokens.total_tokens == initial_tokens

    def test_on_llm_end_accumulates_multiple_calls(self, callback, wrapper):
        """Test that multiple LLM calls accumulate correctly."""
        # First call
        callback.on_llm_end(
            llm_output={"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        )

        # Second call
        callback.on_llm_end(
            llm_output={"usage": {"prompt_tokens": 200, "completion_tokens": 100}}
        )

        # Third call
        callback.on_llm_end(
            prompt_tokens=300,
            completion_tokens=150,
        )

        # Totals should be cumulative
        assert wrapper._total_tokens.prompt_tokens == 600  # 100 + 200 + 300
        assert wrapper._total_tokens.completion_tokens == 300  # 50 + 100 + 150
        assert len(wrapper.cost_tracker.entries) == 3

    def test_on_llm_end_handles_alternative_key_formats(self, callback, wrapper):
        """Test handling of camelCase vs snake_case token keys."""
        # Test camelCase (some API responses use this)
        callback.on_llm_end(
            llm_output={
                "usage": {
                    "promptTokens": 100,
                    "completionTokens": 50,
                }
            }
        )

        assert wrapper._total_tokens.prompt_tokens == 100
        assert wrapper._total_tokens.completion_tokens == 50

    def test_on_llm_end_uses_wrapper_model_if_not_specified(self, callback, wrapper):
        """Test that default model from wrapper is used when not in output."""
        callback.on_llm_end(
            llm_output={
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }
        )

        # Should use the wrapper's configured model
        assert wrapper._total_cost > Decimal("0")

    def test_on_error_logs_error(self, callback):
        """Test that errors are logged."""
        error = Exception("Test error")
        callback.on_error(error)
        # Just verify it doesn't crash - logging is side effect

    def test_budget_exceeded_raises_from_callback(self, callback, wrapper):
        """Test that budget exceeded errors propagate from callback."""
        from src.core.cost import BudgetExceededError

        # Set a zero budget
        wrapper.budget_limit = Decimal("0")

        # Try to track some tokens
        with pytest.raises(BudgetExceededError):
            callback.on_llm_end(
                llm_output={
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50}
                }
            )


class TestCostTrackingCallbackHandlerIntegration:
    """Integration tests for callback handler with real CrewAI flow."""

    @pytest.fixture
    def crew_with_callback(self):
        """Create a crew that uses callback tracking."""
        from src.core.crewai_integration import (
            CostAwareCrew,
            CostAwareAgent,
            CostAwareTask,
        )

        agent = CostAwareAgent(
            role="Tester",
            goal="Test callback integration",
        )

        task = CostAwareTask(
            description="Simple test task",
            expected_output="Result",
            agent=agent,
        )

        crew = CostAwareCrew(
            tasks=[task],
            agents=[agent],
            cost_tracker=CostTracker(),
        )

        # Verify callback is set up
        assert crew._crew is None  # Not created yet

        # Force crew creation
        crew._create_crew()

        return crew

    def test_crew_uses_callback_handler(self, crew_with_callback):
        """Test that crew has callback handler configured."""
        assert crew_with_callback._crew is not None
        assert hasattr(crew_with_callback._crew, "callback_handlers")
        assert len(crew_with_callback._crew.callback_handlers) > 0

    def test_callback_handler_linked_to_wrapper(self, crew_with_callback):
        """Test that callback handler is linked to crew's LLM wrapper."""
        callback = crew_with_callback._crew.callback_handlers[0]
        assert isinstance(callback, CostTrackingCallbackHandler)
        assert callback.wrapper == crew_with_callback.llm_wrapper

    def test_crew_task_id_matches_wrapper(self, crew_with_callback):
        """Test that task IDs are consistent."""
        assert crew_with_callback.task_id.startswith("crew-")
        assert crew_with_callback.llm_wrapper.task_id == crew_with_callback.task_id


class TestCostTrackingCallbackHandlerEdgeCases:
    """Edge case tests for callback handler."""

    def test_empty_llm_output(self):
        """Test handling of empty llm_output."""
        tracker = CostTracker()
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="edge-case",
        )
        callback = CostTrackingCallbackHandler(wrapper)

        # Should not crash on empty output
        callback.on_llm_end(llm_output={})
        callback.on_llm_end(llm_output=None)

    def test_missing_usage_field(self):
        """Test handling of missing usage field."""
        tracker = CostTracker()
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="edge-case",
        )
        callback = CostTrackingCallbackHandler(wrapper)

        # Output without usage should be handled gracefully
        callback.on_llm_end(llm_output={"text": "response"})
        assert wrapper._total_tokens.total_tokens == 0

    def test_very_large_token_counts(self):
        """Test handling of very large token counts."""
        tracker = CostTracker()
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="large-tokens",
            budget_limit=Decimal("100.00"),  # High limit for this test
        )
        callback = CostTrackingCallbackHandler(wrapper)

        # Large but reasonable token counts
        callback.on_llm_end(
            llm_output={
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 50000,
                }
            }
        )

        assert wrapper._total_tokens.total_tokens == 150000
        assert wrapper._total_cost > Decimal("0")

    def test_unicode_in_callback_data(self):
        """Test handling of unicode characters."""
        tracker = CostTracker()
        wrapper = CostAwareLLMWrapper(
            cost_tracker=tracker,
            task_id="unicode-test",
        )
        callback = CostTrackingCallbackHandler(wrapper)

        # Unicode in output (not tokens but other fields)
        callback.on_llm_end(
            llm_output={
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "text": "日本語の出力",
            }
        )

        assert wrapper._total_tokens.total_tokens == 150


# Run tests with: pytest tests/integrations/test_crewai_callback_handler.py -v
