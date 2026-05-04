#!/usr/bin/env python3
"""Unit tests for metrics.py - Metrics collection and reporting.

P1-11: Unit tests for Phase 1 features
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.metrics import MetricsCollector, TaskMetrics, TierMetrics


class TestTaskMetrics:
    """Tests for TaskMetrics dataclass."""

    def test_task_metrics_creation(self):
        """Test creating task metrics."""
        from datetime import datetime, timezone
        
        metrics = TaskMetrics(
            task_id="test-1",
            tier="L1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            duration_seconds=5.5,
            attempts=2,
            tools_executed=3,
            tools_succeeded=2
        )
        
        assert metrics.task_id == "test-1"
        assert metrics.tier == "L1"
        assert metrics.success is True
        assert metrics.duration_seconds == 5.5
        assert metrics.attempts == 2
        assert metrics.tools_executed == 3
        assert metrics.tools_succeeded == 2

    def test_task_metrics_defaults(self):
        """Test task metrics default values."""
        from datetime import datetime, timezone
        
        metrics = TaskMetrics(
            task_id="test-2",
            tier="L0",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            duration_seconds=2.0,
            attempts=1,
            tools_executed=0,
            tools_succeeded=0
        )
        
        assert metrics.tokens_estimate == 0
        assert metrics.cost_estimate_usd == 0.0

    def test_task_metrics_all_fields(self):
        """Test creating task metrics with all fields."""
        from datetime import datetime, timezone
        
        metrics = TaskMetrics(
            task_id="test-3",
            tier="L2-Coder",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            duration_seconds=10.0,
            attempts=1,
            tools_executed=5,
            tools_succeeded=4,
            tokens_estimate=1000,
            cost_estimate_usd=0.003
        )
        
        assert metrics.task_id == "test-3"
        assert metrics.tier == "L2-Coder"
        assert metrics.tokens_estimate == 1000
        assert metrics.cost_estimate_usd == 0.003


class TestTierMetrics:
    """Tests for TierMetrics dataclass."""

    def test_tier_metrics_creation(self):
        """Test creating tier metrics."""
        tm = TierMetrics(tier="L1-Coder")
        
        assert tm.tier == "L1-Coder"
        assert tm.total_tasks == 0
        assert tm.successful_tasks == 0
        assert tm.failed_tasks == 0
        assert tm.total_duration == 0.0
        assert tm.total_attempts == 0

    def test_tier_metrics_success_rate(self):
        """Test success rate calculation."""
        tm = TierMetrics(tier="L1")
        tm.total_tasks = 10
        tm.successful_tasks = 8
        
        assert tm.success_rate == 0.8

    def test_tier_metrics_success_rate_zero(self):
        """Test success rate when no tasks."""
        tm = TierMetrics(tier="L1")
        
        assert tm.success_rate == 0.0

    def test_tier_metrics_avg_duration(self):
        """Test average duration calculation."""
        tm = TierMetrics(tier="L1")
        tm.total_tasks = 3
        tm.total_duration = 60.0
        
        assert tm.avg_duration == 20.0

    def test_tier_metrics_avg_duration_zero(self):
        """Test average duration when no tasks."""
        tm = TierMetrics(tier="L1")
        
        assert tm.avg_duration == 0.0

    def test_tier_metrics_avg_attempts(self):
        """Test average attempts calculation."""
        tm = TierMetrics(tier="L1")
        tm.total_tasks = 2
        tm.total_attempts = 6
        
        assert tm.avg_attempts == 3.0


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_collector_initialization(self):
        """Test metrics collector initialization."""
        collector = MetricsCollector()
        
        assert collector.task_metrics == []
        assert collector.tier_metrics == {}
        assert collector.metrics_dir is not None

    def test_collector_initialization_with_dir(self):
        """Test metrics collector with custom directory."""
        collector = MetricsCollector(metrics_dir="/tmp/test_metrics")
        
        assert collector.metrics_dir == Path("/tmp/test_metrics")

    def test_record_task_success(self):
        """Test recording a successful task."""
        collector = MetricsCollector()
        
        collector.record_task(
            task_id="task-1",
            tier="L1-Coder",
            success=True,
            duration=10.5,
            attempts=1,
            tools_executed=2,
            tools_succeeded=2,
            tokens=100
        )
        
        assert len(collector.task_metrics) == 1
        assert collector.task_metrics[0].task_id == "task-1"
        assert collector.task_metrics[0].success is True

    def test_record_task_failure(self):
        """Test recording a failed task."""
        collector = MetricsCollector()
        
        collector.record_task(
            task_id="task-2",
            tier="L0-Planner",
            success=False,
            duration=5.0,
            attempts=3,
            tools_executed=0,
            tools_succeeded=0,
            tokens=10
        )
        
        assert len(collector.task_metrics) == 1
        assert collector.task_metrics[0].task_id == "task-2"
        assert collector.task_metrics[0].success is False

    def test_record_multiple_tasks(self):
        """Test recording multiple tasks."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L1", True, 15.0, 2, 3, 3, 100)
        collector.record_task("t3", "L0", False, 5.0, 3, 0, 0, 10)
        
        assert len(collector.task_metrics) == 3
        assert collector.tier_metrics["L1"].total_tasks == 2
        assert collector.tier_metrics["L0"].total_tasks == 1

    def test_get_summary(self):
        """Test getting metrics summary."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L1", True, 10.0, 1, 2, 2, 100)
        
        summary = collector.get_summary()
        
        assert summary["total_tasks"] == 2
        assert summary["overall_success_rate"] == 1.0  # 100%
        assert "tiers" in summary

    def test_get_summary_empty(self):
        """Test getting summary with no tasks."""
        collector = MetricsCollector()
        
        summary = collector.get_summary()
        
        assert summary["total_tasks"] == 0
        assert summary["overall_success_rate"] == 0.0
        assert summary["total_cost_usd"] == 0.0
        assert summary["successful_tasks"] == 0

    def test_get_summary_partial_success(self):
        """Test summary with partial success rate."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L1", False, 5.0, 2, 0, 0, 100)
        
        summary = collector.get_summary()
        
        assert summary["total_tasks"] == 2
        assert summary["overall_success_rate"] == 0.5  # 50%

    def test_tier_metrics_tracking(self):
        """Test that tier metrics are properly tracked."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1-Coder", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L1-Coder", True, 15.0, 2, 3, 3, 100)
        collector.record_task("t3", "L2-Coder", False, 5.0, 3, 0, 0, 100)
        
        assert "L1-Coder" in collector.tier_metrics
        assert "L2-Coder" in collector.tier_metrics
        assert collector.tier_metrics["L1-Coder"].total_tasks == 2
        assert collector.tier_metrics["L2-Coder"].total_tasks == 1

    def test_tier_metrics_properties(self):
        """Test TierMetrics properties."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L1", True, 20.0, 2, 3, 3, 100)
        collector.record_task("t3", "L1", False, 5.0, 3, 0, 0, 100)
        
        tm = collector.tier_metrics["L1"]
        
        assert tm.success_rate == 2/3  # 66.7%
        assert abs(tm.avg_duration - 11.67) < 0.01  # (10 + 20 + 5) / 3
        assert tm.avg_attempts == 2.0  # (1 + 2 + 3) / 3

    def test_save_metrics(self):
        """Test saving metrics to file."""
        import tempfile
        
        collector = MetricsCollector()
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            collector.metrics_dir = Path(tmpdir)
            filepath = collector.save_metrics()
            
            assert filepath.exists()
            assert filepath.suffix == ".json"

    def test_save_metrics_custom_filename(self):
        """Test saving metrics with custom filename."""
        import tempfile
        
        collector = MetricsCollector()
        collector.record_task("t1", "L1", True, 10.0, 1, 2, 2, 100)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            collector.metrics_dir = Path(tmpdir)
            filepath = collector.save_metrics("custom_test.json")
            
            assert filepath.name == "custom_test.json"

    def test_get_summary_tier_breakdown(self):
        """Test tier breakdown in summary."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1-Coder", True, 10.0, 1, 2, 2, 100)
        collector.record_task("t2", "L2-Coder", True, 15.0, 1, 3, 3, 100)
        collector.record_task("t3", "L1-Coder", False, 5.0, 2, 0, 0, 100)
        
        summary = collector.get_summary()
        
        assert "L1-Coder" in summary["tiers"]
        assert "L2-Coder" in summary["tiers"]
        assert summary["tiers"]["L1-Coder"]["tasks"] == 2
        assert summary["tiers"]["L2-Coder"]["tasks"] == 1

    def test_cost_calculation(self):
        """Test cost calculation based on tier and tokens."""
        collector = MetricsCollector()
        
        # L1-Coder has cost multiplier of 0.000002
        collector.record_task("t1", "L1-Coder", True, 10.0, 1, 2, 2, 1000)
        
        summary = collector.get_summary()
        # Cost = 0.000002 * 1000 = 0.002
        assert summary["tiers"]["L1-Coder"]["cost"] == 0.002

    def test_cost_calculation_different_tiers(self):
        """Test cost calculation with different tiers."""
        collector = MetricsCollector()
        
        # L0-Planner has cost multiplier of 0.000001
        collector.record_task("t1", "L0-Planner", True, 10.0, 1, 2, 2, 1000)
        # L2-Coder has cost multiplier of 0.000003
        collector.record_task("t2", "L2-Coder", True, 10.0, 1, 3, 3, 1000)
        
        summary = collector.get_summary()
        
        # L0-Planner: 0.000001 * 1000 = 0.001
        assert summary["tiers"]["L0-Planner"]["cost"] == 0.001
        # L2-Coder: 0.000003 * 1000 = 0.003
        assert summary["tiers"]["L2-Coder"]["cost"] == 0.003

    def test_get_summary_total_cost(self):
        """Test total cost in summary."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1-Coder", True, 10.0, 1, 2, 2, 1000)
        collector.record_task("t2", "L2-Coder", True, 10.0, 1, 3, 3, 1000)
        
        summary = collector.get_summary()
        
        # Total = 0.002 + 0.003 = 0.005
        assert summary["total_cost_usd"] == 0.005

    def test_start_time_tracking(self):
        """Test that start time is tracked."""
        collector = MetricsCollector()
        
        assert collector.start_time is not None
        summary = collector.get_summary()
        
        assert "session_start" in summary

    def test_record_task_no_tokens(self):
        """Test recording task with no tokens provided."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "L1-Coder", True, 10.0, 1, 2, 2)
        
        # Should default to 0 tokens
        assert collector.task_metrics[0].tokens_estimate == 0
        assert collector.task_metrics[0].cost_estimate_usd == 0.0

    def test_unknown_tier_cost(self):
        """Test cost calculation for unknown tier."""
        collector = MetricsCollector()
        
        collector.record_task("t1", "Unknown-Tier", True, 10.0, 1, 2, 2, 1000)
        
        # Unknown tiers should have 0 cost
        assert collector.task_metrics[0].cost_estimate_usd == 0.0
        assert collector.tier_metrics["Unknown-Tier"].total_tasks == 1
