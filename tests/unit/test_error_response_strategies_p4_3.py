"""
Tests for ErrorResponseStrategy and strategy selector (P4-3: Cost-Aware Error Handling)
"""

import pytest
from src.classifiers.error_classifier import ErrorClassifier, ErrorClassification, ErrorCategory
from src.strategies.error_response import (
    ErrorResponseStrategy,
    ErrorResponseStrategySelector,
    ResponseAction
)


class TestErrorResponseStrategy:
    """Test ErrorResponseStrategy dataclass."""

    def test_response_strategy_retry_backoff(self):
        """Test retry with backoff strategy."""
        strategy = ErrorResponseStrategy(
            action=ResponseAction.RETRY_WITH_BACKOFF,
            max_retries=3,
            base_delay=1.0,
            jitter=True,
            escalate_after_retries=2
        )
        
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        assert strategy.max_retries == 3
        assert strategy.base_delay == 1.0
        assert strategy.jitter is True
        assert strategy.escalate_after_retries == 2

    def test_response_strategy_immediate_escalation(self):
        """Test immediate escalation strategy."""
        strategy = ErrorResponseStrategy(
            action=ResponseAction.IMMEDIATE_ESCALATION,
            max_retries=0,
            base_delay=0.0,
            jitter=False,
            escalate_after_retries=0
        )
        
        assert strategy.action == ResponseAction.IMMEDIATE_ESCALATION
        assert strategy.max_retries == 0


class TestErrorResponseStrategySelector:
    """Test ErrorResponseStrategySelector class."""

    def test_select_retry_low_cost_strategy(self):
        """Test strategy selection for low cost retryable errors."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        strategy = selector.get_response_strategy(classification, budget_remaining=0.8)
        
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        assert strategy.max_retries >= 3

    def test_select_retry_high_cost_strategy(self):
        """Test strategy selection for high cost retryable errors."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_HIGH_COST,
            confidence=0.8,
            estimated_cost_impact=0.1
        )
        
        strategy = selector.get_response_strategy(classification, budget_remaining=0.8)
        
        # High cost errors should have conservative retry settings
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        assert strategy.max_retries <= 3

    def test_select_immediate_escalation_strategy(self):
        """Test strategy selection for errors requiring immediate escalation."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.ESCALATE_IMMEDIATELY,
            confidence=0.95,
            estimated_cost_impact=0.0
        )
        
        strategy = selector.get_response_strategy(classification, budget_remaining=0.8)
        
        assert strategy.action in [ResponseAction.IMMEDIATE_ESCALATION, ResponseAction.FAIL_IMMEDIATELY]
        assert strategy.max_retries == 0

    def test_select_static_failure_strategy(self):
        """Test strategy selection for static failures (no retry)."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.STATIC_FAILURE,
            confidence=0.9,
            estimated_cost_impact=0.0
        )
        
        strategy = selector.get_response_strategy(classification, budget_remaining=0.8)
        
        assert strategy.action == ResponseAction.FAIL_IMMEDIATELY
        assert strategy.max_retries == 0

    def test_select_strategy_budget_constrained(self):
        """Test strategy selection when budget is constrained."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        # With only 10% budget remaining
        strategy = selector.get_response_strategy(classification, budget_remaining=0.1)
        
        # Should reduce or eliminate retries
        assert strategy.max_retries <= 1

    def test_select_strategy_budget_depleted(self):
        """Test strategy selection when budget is nearly depleted."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        # With only 5% budget remaining
        strategy = selector.get_response_strategy(classification, budget_remaining=0.05)
        
        # Should not allow retries
        assert strategy.action == ResponseAction.IMMEDIATE_ESCALATION
        assert strategy.max_retries == 0

    def test_select_strategy_budget_healthy(self):
        """Test strategy selection when budget is healthy."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        # With 95% budget remaining
        strategy = selector.get_response_strategy(classification, budget_remaining=0.95)
        
        # Should allow aggressive retries
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        assert strategy.max_retries >= 5

    def test_get_retry_config(self):
        """Test retry configuration from classification."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        retry_config = selector.get_retry_config(classification, budget_remaining=0.8)
        
        assert retry_config["max_retries"] >= 3
        assert retry_config["base_delay"] > 0
        assert retry_config["exponential_backoff"] is True

    def test_select_strategy_unknown_error(self):
        """Test strategy selection for unknown errors."""
        selector = ErrorResponseStrategySelector()
        
        # Unknown errors get low confidence but same default category
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,  # Default
            confidence=0.3,
            estimated_cost_impact=0.05
        )
        
        strategy = selector.get_response_strategy(classification, budget_remaining=0.8)
        
        # Low confidence doesn't limit retries by itself - budget does
        # The strategy will be RETRY_WITH_BACKOFF but budget will determine retry count
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        # Retry count depends on budget multiplier, not confidence


class TestErrorResponseStrategyIntegration:
    """Test error response strategy integration scenarios."""

    def test_budget_aware_strategy_sequence(self):
        """Test strategy changes based on budget progression."""
        selector = ErrorResponseStrategySelector()
        
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.9,
            estimated_cost_impact=0.01
        )
        
        # Start with healthy budget
        strategy_90 = selector.get_response_strategy(classification, budget_remaining=0.9)
        
        # Then moderate budget
        strategy_50 = selector.get_response_strategy(classification, budget_remaining=0.5)
        
        # Then low budget
        strategy_10 = selector.get_response_strategy(classification, budget_remaining=0.1)
        
        # Verify strategy becomes more conservative
        assert strategy_90.max_retries >= strategy_50.max_retries
        assert strategy_50.max_retries >= strategy_10.max_retries

    def test_different_categories_different_strategies(self):
        """Test that different error categories get different strategies."""
        selector = ErrorResponseStrategySelector()
        
        categories = [
            ErrorCategory.RETRYABLE_LOW_COST,
            ErrorCategory.RETRYABLE_HIGH_COST,
            ErrorCategory.ESCALATE_IMMEDIATELY,
            ErrorCategory.STATIC_FAILURE,
        ]
        
        strategies = [
            selector.get_response_strategy(
                ErrorClassification(category=cat, confidence=0.8),
                budget_remaining=0.8
            )
            for cat in categories
        ]
        
        # Each category should have appropriate strategy
        assert strategies[0].action == ResponseAction.RETRY_WITH_BACKOFF  # Low cost
        assert strategies[1].action == ResponseAction.RETRY_WITH_BACKOFF  # High cost
        assert strategies[2].max_retries == 0  # Escalate
        assert strategies[3].action == ResponseAction.FAIL_IMMEDIATELY  # Static
