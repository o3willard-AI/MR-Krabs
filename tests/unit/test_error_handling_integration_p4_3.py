"""
Integration tests for error handling workflow (P4-3: Cost-Aware Error Handling).
Tests end-to-end error classification, strategy selection, and metrics tracking.
"""

import pytest
from decimal import Decimal

from src.classifiers.error_classifier import ErrorClassifier, ErrorClassification, ErrorCategory
from src.strategies.error_response import (
    ErrorResponseStrategySelector,
    ResponseAction,
    ErrorResponseStrategy
)
from src.config.retry import RetryConfig, RetryConfigFactory
from src.metrics.error_metrics import ErrorMetricsCollector


class TestCompleteErrorHandlingWorkflow:
    """Test complete error handling workflow from classification to recovery."""

    def test_full_workflow_low_cost_error(self):
        """Test full workflow for low-cost retryable error."""
        # Setup
        classifier = ErrorClassifier()
        strategy_selector = ErrorResponseStrategySelector()
        retry_factory = RetryConfigFactory()
        metrics_collector = ErrorMetricsCollector()
        
        # Simulate connection error
        class ConnectionError(Exception):
            pass
        
        error = ConnectionError("Connection refused")
        
        # Step 1: Classify error
        classification = classifier.classify_error(error)
        
        # Step 2: Get response strategy
        strategy = strategy_selector.get_response_strategy(
            classification,
            budget_remaining=0.8
        )
        
        # Step 3: Get retry config
        retry_config = retry_factory.create_config_for_error_category(
            classification.category.value,
            budget_remaining=0.8
        )
        
        # Step 4: Simulate recovery attempt
        recovered = True
        recovery_time = 1.5
        cost_impact = Decimal("0.01")
        
        # Record metrics
        metrics_collector.record_error(
            error_type="connection",
            error_category=classification.category.value,
            recovered=recovered,
            recovery_time_seconds=recovery_time,
            cost_impact=cost_impact
        )
        
        # Verify workflow
        assert classification.category == ErrorCategory.RETRYABLE_LOW_COST
        assert strategy.action == ResponseAction.RETRY_WITH_BACKOFF
        assert strategy.max_retries >= 3
        assert retry_config.max_retries >= 3
        assert metrics_collector.get_metrics().error_count == 1

    def test_full_workflow_escalation_error(self):
        """Test full workflow for error requiring immediate escalation."""
        # Setup
        classifier = ErrorClassifier()
        strategy_selector = ErrorResponseStrategySelector()
        metrics_collector = ErrorMetricsCollector()
        
        # Simulate budget exceeded error
        class BudgetExceededError(Exception):
            pass
        
        error = BudgetExceededError("Budget limit exceeded")
        
        # Step 1: Classify error
        classification = classifier.classify_error(error)
        
        # Step 2: Get response strategy
        strategy = strategy_selector.get_response_strategy(
            classification,
            budget_remaining=0.5
        )
        
        # Step 3: Simulate escalation (no retry)
        recovered = False
        triggered_escalation = True
        
        # Record metrics
        metrics_collector.record_error(
            error_type="budget_exceeded",
            error_category=classification.category.value,
            recovered=recovered,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.00"),
            triggered_escalation=triggered_escalation
        )
        
        # Verify workflow
        assert classification.category == ErrorCategory.ESCALATE_IMMEDIATELY
        assert strategy.max_retries == 0
        assert strategy.action in [ResponseAction.IMMEDIATE_ESCALATION, ResponseAction.FAIL_IMMEDIATELY]
        metrics = metrics_collector.get_metrics()
        assert metrics.escalation_count == 1

    def test_full_workflow_budget_constrained(self):
        """Test workflow with budget constraints limiting retries."""
        # Setup
        classifier = ErrorClassifier()
        strategy_selector = ErrorResponseStrategySelector()
        
        # Simulate connection error
        class ConnectionError(Exception):
            pass
        
        error = ConnectionError("Connection timeout")
        
        # Classify error
        classification = classifier.classify_error(error)
        
        # Get strategy with constrained budget
        healthy_strategy = strategy_selector.get_response_strategy(
            classification,
            budget_remaining=0.9
        )
        
        constrained_strategy = strategy_selector.get_response_strategy(
            classification,
            budget_remaining=0.15
        )
        
        # Verify budget awareness
        assert healthy_strategy.max_retries >= constrained_strategy.max_retries
        assert constrained_strategy.max_retries <= 1


class TestErrorHandlingConsistency:
    """Test consistency of error handling across multiple scenarios."""

    def test_same_error_same_classification(self):
        """Test that same error type gets consistent classification."""
        classifier = ErrorClassifier()
        
        errors = [
            ConnectionError("Connection refused"),
            ConnectionError("Connection reset"),
            ConnectionError("Network unreachable"),
        ]
        
        classifications = [classifier.classify_error(e) for e in errors]
        
        # All should be RETRYABLE_LOW_COST
        for c in classifications:
            assert c.category == ErrorCategory.RETRYABLE_LOW_COST

    def test_error_type_hierarchy_respected(self):
        """Test that error hierarchy is respected in classification."""
        classifier = ErrorClassifier()
        
        # Parent and child errors should be classified similarly
        parent_error = TimeoutError("Timeout")
        child_error = ConnectionTimeoutError("Connection timeout")
        
        parent_class = classifier.classify_error(parent_error)
        child_class = classifier.classify_error(child_error)
        
        # Both should have similar categories (either both RETRYABLE or both STATIC)
        assert parent_class.category == child_class.category


class ConnectionError(Exception):
    """Custom connection error for testing."""
    pass


class ConnectionTimeoutError(ConnectionError):
    """Custom connection timeout error for testing."""
    pass


class TestErrorMetricsIntegration:
    """Test error metrics integration with full workflow."""

    def test_metrics_through_retry_cycle(self):
        """Test metrics tracking through retry cycle."""
        classifier = ErrorClassifier()
        metrics_collector = ErrorMetricsCollector()
        
        # Simulate a connection error with retries
        error = ConnectionError("Connection refused")
        classification = classifier.classify_error(error)
        
        # First attempt fails
        metrics_collector.record_error(
            error_type="connection",
            error_category=classification.category.value,
            recovered=False,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.00")
        )
        
        # Retry 1 succeeds
        metrics_collector.record_error(
            error_type="connection",
            error_category=classification.category.value,
            recovered=True,
            recovery_time_seconds=1.0,
            cost_impact=Decimal("0.01")
        )
        
        # Record retry count
        metrics_collector.record_retry()
        metrics_collector.record_retry()  # 2 retries total
        
        # Check metrics
        metrics = metrics_collector.get_metrics()
        
        assert metrics.error_count == 2
        assert metrics.retry_count == 2
        assert metrics.recovery_success_rate >= 0.5  # 1/2 recovered

    def test_metrics_accumulation(self):
        """Test that metrics accumulate correctly across multiple errors."""
        metrics_collector = ErrorMetricsCollector()
        
        # Simulate 10 errors: 7 recovered, 3 escalated
        for i in range(10):
            recovered = i < 7
            triggered_escalation = not recovered
            
            metrics_collector.record_error(
                error_type="network" if i < 5 else "timeout",
                error_category="retryable_low_cost",
                recovered=recovered,
                recovery_time_seconds=1.5 if recovered else None,
                cost_impact=Decimal("0.01"),
                triggered_escalation=triggered_escalation
            )
        
        metrics = metrics_collector.get_metrics()
        
        assert metrics.error_count == 10
        assert metrics.escalation_count == 3
        assert 0.6 <= metrics.recovery_success_rate <= 0.8  # ~70%
        assert metrics.budget_impact == Decimal("0.10")


class TestBudgetAwareErrorHandling:
    """Test budget-aware error handling decisions."""

    def test_retry_policy_adapts_to_budget(self):
        """Test that retry policies adapt as budget depletes."""
        classifier = ErrorClassifier()
        strategy_selector = ErrorResponseStrategySelector()
        
        error = ConnectionError("Connection timeout")
        classification = classifier.classify_error(error)
        
        # Track strategy as budget depletes
        strategies = []
        for budget_remaining in [0.95, 0.8, 0.5, 0.3, 0.1]:
            strategy = strategy_selector.get_response_strategy(
                classification,
                budget_remaining=budget_remaining
            )
            strategies.append(strategy)
        
        # Verify retry count decreases as budget depletes
        retry_counts = [s.max_retries for s in strategies]
        assert retry_counts == sorted(retry_counts, reverse=True)  # Non-increasing

    def test_immediate_escalation_when_budget_exhausted(self):
        """Test immediate escalation when budget is nearly depleted."""
        classifier = ErrorClassifier()
        strategy_selector = ErrorResponseStrategySelector()
        
        error = ConnectionError("Connection timeout")
        classification = classifier.classify_error(error)
        
        # With critically low budget, should escalate immediately
        strategy = strategy_selector.get_response_strategy(
            classification,
            budget_remaining=0.05
        )
        
        assert strategy.action == ResponseAction.IMMEDIATE_ESCALATION
        assert strategy.max_retries == 0
