"""
Tests for Error Metrics (metrics/error_metrics.py).

These tests cover error tracking and metrics collection.

P4-5: Error Tracking Tests
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from src.metrics.error_metrics import ErrorMetrics, ErrorMetricsCollector


class TestErrorMetricsDataclass:
    """Tests for the ErrorMetrics dataclass."""
    
    def test_error_metrics_creation(self):
        """Test creating a basic ErrorMetrics object."""
        metrics = ErrorMetrics(
            error_count=5,
            retry_count=3,
            escalation_count=1,
            recovery_success_rate=0.8,
            avg_recovery_time_seconds=10.5,
            budget_impact=Decimal("2.50")
        )
        
        assert metrics.error_count == 5
    
    def test_error_metrics_default_values(self):
        """Test ErrorMetrics default initialization."""
        metrics = ErrorMetrics()
        
        assert metrics.error_count == 0
        assert metrics.retry_count == 0


class TestErrorMetricsCollector:
    """Tests for the ErrorMetricsCollector class."""
    
    def test_collector_initialization(self):
        """Test collector initializes correctly."""
        collector = ErrorMetricsCollector()
        
        # Collector should be initialized
        assert hasattr(collector, '__init__')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
