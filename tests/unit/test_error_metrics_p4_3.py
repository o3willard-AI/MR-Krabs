"""
Tests for ErrorMetrics and ErrorMetricsCollector (P4-3: Cost-Aware Error Handling)
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from src.metrics.error_metrics import ErrorMetrics, ErrorMetricsCollector


class TestErrorMetrics:
    """Test ErrorMetrics dataclass."""

    def test_error_metrics_basic(self):
        """Test basic ErrorMetrics creation."""
        metrics = ErrorMetrics(
            error_count=10,
            retry_count=25,
            escalation_count=3,
            recovery_success_rate=0.75,
            avg_recovery_time_seconds=2.5,
            error_type_breakdown={
                "network": 5,
                "timeout": 3,
                "rate_limit": 2
            },
            budget_impact=Decimal("0.50")
        )
        
        assert metrics.error_count == 10
        assert metrics.retry_count == 25
        assert metrics.escalation_count == 3
        assert metrics.recovery_success_rate == 0.75
        assert metrics.avg_recovery_time_seconds == 2.5
        assert metrics.budget_impact == Decimal("0.50")

    def test_error_metrics_defaults(self):
        """Test ErrorMetrics with default values."""
        metrics = ErrorMetrics()
        
        assert metrics.error_count == 0
        assert metrics.retry_count == 0
        assert metrics.escalation_count == 0
        assert metrics.recovery_success_rate == 0.0
        assert metrics.avg_recovery_time_seconds == 0.0
        assert metrics.budget_impact == Decimal("0.00")

    def test_error_metrics_to_dict(self):
        """Test converting ErrorMetrics to dict."""
        metrics = ErrorMetrics(
            error_count=5,
            retry_count=10,
            escalation_count=1,
            recovery_success_rate=0.8,
            avg_recovery_time_seconds=1.5,
            error_type_breakdown={"network": 3, "timeout": 2},
            budget_impact=Decimal("0.25")
        )
        
        data = metrics.to_dict()
        
        assert data["error_count"] == 5
        assert data["retry_count"] == 10
        assert data["escalation_count"] == 1
        assert data["recovery_success_rate"] == 0.8
        assert data["budget_impact"] == "0.25"  # Decimal converts to string in JSON


class TestErrorMetricsCollector:
    """Test ErrorMetricsCollector class."""

    def test_collect_error_no_metrics(self):
        """Test collecting error with no prior metrics."""
        collector = ErrorMetricsCollector()
        
        collector.record_error(
            error_type="timeout",
            error_category="retryable_low_cost",
            recovered=False,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.01")
        )
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 1
        assert metrics.retry_count == 0
        assert metrics.escalation_count == 0
        assert metrics.recovery_success_rate == 0.0

    def test_collect_recovered_error(self):
        """Test collecting successfully recovered error."""
        collector = ErrorMetricsCollector()
        
        # Record 3 errors, 2 recovered
        collector.record_error(
            error_type="timeout",
            error_category="retryable_low_cost",
            recovered=True,
            recovery_time_seconds=2.0,
            cost_impact=Decimal("0.01")
        )
        collector.record_error(
            error_type="network",
            error_category="retryable_low_cost",
            recovered=True,
            recovery_time_seconds=1.5,
            cost_impact=Decimal("0.02")
        )
        collector.record_error(
            error_type="rate_limit",
            error_category="retryable_low_cost",
            recovered=False,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.00")
        )
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 3
        assert metrics.retry_count == 0  # Not tracking individual retries here
        assert metrics.recovery_success_rate == 0.667  # 2/3 recovered, rounded to 3 decimals
        assert metrics.budget_impact == Decimal("0.03")

    def test_collect_escalated_error(self):
        """Test collecting error that triggered escalation."""
        collector = ErrorMetricsCollector()
        
        collector.record_error(
            error_type="budget_exceeded",
            error_category="escalate_immediately",
            recovered=False,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.00"),
            triggered_escalation=True
        )
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 1
        assert metrics.escalation_count == 1

    def test_collect_multiple_errors_same_type(self):
        """Test collecting multiple errors of same type."""
        collector = ErrorMetricsCollector()
        
        # Record 5 timeout errors
        for _ in range(5):
            collector.record_error(
                error_type="timeout",
                error_category="retryable_low_cost",
                recovered=True,
                recovery_time_seconds=2.0,
                cost_impact=Decimal("0.01")
            )
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 5
        assert metrics.error_type_breakdown["timeout"] == 5
        assert metrics.recovery_success_rate == 1.0

    def test_reset_metrics(self):
        """Test resetting error metrics."""
        collector = ErrorMetricsCollector()
        
        # Record some errors
        collector.record_error(
            error_type="timeout",
            error_category="retryable_low_cost",
            recovered=True,
            recovery_time_seconds=1.0,
            cost_impact=Decimal("0.01")
        )
        
        # Reset
        collector.reset_metrics()
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 0
        assert metrics.retry_count == 0
        assert metrics.budget_impact == Decimal("0.00")

    def test_get_summary(self):
        """Test getting metrics summary."""
        collector = ErrorMetricsCollector()
        
        collector.record_error(
            error_type="timeout",
            error_category="retryable_low_cost",
            recovered=True,
            recovery_time_seconds=2.0,
            cost_impact=Decimal("0.01")
        )
        collector.record_error(
            error_type="network",
            error_category="retryable_low_cost",
            recovered=False,
            recovery_time_seconds=None,
            cost_impact=Decimal("0.02"),
            triggered_escalation=True
        )
        
        summary = collector.get_summary()
        
        assert "total_errors" in summary
        assert "recovery_success_rate" in summary
        assert "total_cost_impact" in summary
        assert summary["total_errors"] == 2

    def test_budget_impact_tracking(self):
        """Test tracking budget impact from error recovery."""
        collector = ErrorMetricsCollector()
        
        # Record errors with varying cost impacts
        costs = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]
        for cost in costs:
            collector.record_error(
                error_type="timeout",
                error_category="retryable_low_cost",
                recovered=True,
                recovery_time_seconds=1.0,
                cost_impact=cost
            )
        
        metrics = collector.get_metrics()
        
        expected_total = sum(costs)
        assert metrics.budget_impact == expected_total

    def test_concurrent_error_collection(self):
        """Test collecting errors concurrently."""
        import threading
        
        collector = ErrorMetricsCollector()
        errors_per_thread = 10
        
        def record_errors():
            for i in range(errors_per_thread):
                collector.record_error(
                    error_type=f"error_{i % 3}",
                    error_category="retryable_low_cost",
                    recovered=i % 2 == 0,
                    recovery_time_seconds=1.0,
                    cost_impact=Decimal("0.01")
                )
        
        threads = [threading.Thread(target=record_errors) for _ in range(3)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == errors_per_thread * 3


class TestErrorMetricsIntegration:
    """Test ErrorMetrics integration scenarios."""

    def test_metrics_with_error_workflow(self):
        """Test error metrics through complete error workflow."""
        collector = ErrorMetricsCollector()
        
        # Scenario: 10 errors, 7 recovered, 3 escalated
        for i in range(10):
            recovered = i < 7
            collector.record_error(
                error_type="timeout" if i < 5 else "network",
                error_category="retryable_low_cost",
                recovered=recovered,
                recovery_time_seconds=2.0 if recovered else None,
                cost_impact=Decimal("0.01"),
                triggered_escalation=not recovered
            )
        
        metrics = collector.get_metrics()
        
        assert metrics.error_count == 10
        assert metrics.escalation_count == 3
        assert 0.6 <= metrics.recovery_success_rate <= 0.8  # ~70%
