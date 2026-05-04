#!/usr/bin/env python3
"""
Tests for P4-1: Enhanced Cost Tracking with Real-time Alerts

Tests:
- Multi-level budget warnings (50%, 75%, 90%)
- CostAlertHandler callback system
- Budget.get_warning_level() method
- Daily reset of warning levels
- Alert history tracking
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.cost import (
    Budget,
    CostTracker,
    CostAlert,
    CostAlertHandler,
    TokenCount,
    BudgetExceededError,
)


class TestBudgetGetWarningLevel:
    """Test the new get_warning_level method on Budget."""

    def test_returns_none_below_all_thresholds(self):
        """Should return None when below all warning thresholds."""
        budget = Budget(daily_limit_usd=Decimal("10.00"))
        result = budget.get_warning_level(Decimal("0.00"))
        assert result is None

    def test_returns_50_threshold_at_halfway(self):
        """Should return 0.5 when at 50% of budget."""
        budget = Budget(daily_limit_usd=Decimal("10.00"))
        result = budget.get_warning_level(Decimal("5.00"))
        assert result == Decimal("0.5")

    def test_returns_75_threshold_at_three_quarters(self):
        """Should return 0.75 when at 75% of budget."""
        budget = Budget(daily_limit_usd=Decimal("10.00"))
        result = budget.get_warning_level(Decimal("7.50"))
        assert result == Decimal("0.75")

    def test_returns_90_threshold_at_ninety_percent(self):
        """Should return 0.90 when at 90% of budget."""
        budget = Budget(daily_limit_usd=Decimal("10.00"))
        result = budget.get_warning_level(Decimal("9.00"))
        assert result == Decimal("0.90")

    def test_returns_highest_exceeded_threshold(self):
        """Should return the highest threshold that's exceeded."""
        budget = Budget(daily_limit_usd=Decimal("10.00"))
        result = budget.get_warning_level(Decimal("8.00"))
        assert result == Decimal("0.75")  # 80% exceeds 75% but not 90%

    def test_custom_thresholds(self):
        """Should respect custom warning thresholds."""
        budget = Budget(
            daily_limit_usd=Decimal("10.00"),
            warn_thresholds=[Decimal("0.3"), Decimal("0.6"), Decimal("0.8")]
        )
        result = budget.get_warning_level(Decimal("7.00"))  # 70% exceeds 30% and 60%
        assert result == Decimal("0.6")  # Return highest exceeded threshold
    
    def test_exactly_at_threshold(self):
        """Should return threshold when exactly at that percentage."""
        budget = Budget(
            daily_limit_usd=Decimal("10.00"),
            warn_thresholds=[Decimal("0.3"), Decimal("0.5"), Decimal("0.9")]
        )
        result = budget.get_warning_level(Decimal("3.00"))
        assert result == Decimal("0.3")


class TestCostAlertHandler:
    """Test the CostAlertHandler callback system."""

    def test_no_alerts_when_initialized(self):
        """Should start with no callbacks and empty history."""
        handler = CostAlertHandler()
        assert handler.callbacks == []
        assert handler.alert_history == []

    def test_add_callback(self):
        """Should be able to add callbacks."""
        handler = CostAlertHandler()

        def my_callback(alert):
            pass

        handler.add_callback(my_callback)
        assert len(handler.callbacks) == 1
        assert my_callback in handler.callbacks

    def test_invokes_callback_on_alert(self):
        """Should invoke callback when alert is handled."""
        handler = CostAlertHandler()
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        handler.add_callback(capture_alert)

        # Create a mock tracker
        tracker = CostTracker()
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))

        handler.handle_warning("warning_50", tracker)

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == "warning_50"
        assert alerts_received[0].daily_total == Decimal("5.00")

    def test_invokes_all_callbacks(self):
        """Should invoke all registered callbacks."""
        handler = CostAlertHandler()
        callback1_called = []
        callback2_called = []

        def cb1(alert):
            callback1_called.append(alert)

        def cb2(alert):
            callback2_called.append(alert)

        handler.add_callback(cb1)
        handler.add_callback(cb2)

        tracker = CostTracker()
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))

        handler.handle_warning("warning_50", tracker)

        assert len(callback1_called) == 1
        assert len(callback2_called) == 1

    def test_alert_history_updated(self):
        """Should append alerts to history."""
        handler = CostAlertHandler()

        tracker = CostTracker()
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))

        handler.handle_warning("warning_50", tracker)
        handler.handle_warning("warning_75", tracker)

        assert len(handler.alert_history) == 2
        assert handler.alert_history[0].alert_type == "warning_50"
        assert handler.alert_history[1].alert_type == "warning_75"

    def test_callback_exception_handling(self):
        """Should not break on callback exceptions."""
        handler = CostAlertHandler()

        def bad_callback(alert):
            raise ValueError("Test error")

        def good_callback(alert):
            pass

        handler.add_callback(bad_callback)
        handler.add_callback(good_callback)

        tracker = CostTracker()
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))

        # Should not raise
        handler.handle_warning("warning_50", tracker)


class TestCostAlert:
    """Test CostAlert dataclass."""

    def test_alert_has_all_fields(self):
        """Should have all required fields."""
        alert = CostAlert(
            timestamp="2026-04-28T12:00:00+00:00",
            alert_type="warning_50",
            daily_total=Decimal("5.00"),
            budget_limit=Decimal("10.00"),
            percentage=Decimal("50"),
            message="Test message"
        )

        assert alert.timestamp == "2026-04-28T12:00:00+00:00"
        assert alert.alert_type == "warning_50"
        assert alert.daily_total == Decimal("5.00")
        assert alert.budget_limit == Decimal("10.00")
        assert alert.percentage == Decimal("50")
        assert alert.message == "Test message"

    def test_alert_message_format(self):
        """Should have properly formatted messages."""
        tracker = CostTracker()
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))

        handler = CostAlertHandler()
        alert = handler._create_alert("warning_50", tracker)

        assert "BUDGET WARNING" in alert.message
        assert "50%" in alert.message
        assert "$5.00" in alert.message


class TestCostTrackerRealTimeAlerts:
    """Test real-time alert functionality in CostTracker."""

    def test_add_alert_callback(self):
        """Should be able to register alert callbacks."""
        tracker = CostTracker()

        def my_callback(alert):
            pass

        tracker.add_alert_callback(my_callback)
        assert len(tracker.alert_handler.callbacks) == 1

    def test_get_alert_history(self):
        """Should return a copy of alert history."""
        tracker = CostTracker()

        initial_count = len(tracker.get_alert_history())
        assert initial_count == 0

        # Trigger an alert by setting daily_total to 50%
        tracker.daily_total = Decimal("5.00")
        tracker.budget = Budget(daily_limit_usd=Decimal("10.00"))
        tracker._emit_warning("warning")

        history = tracker.get_alert_history()
        assert len(history) == 1
        assert history[0].alert_type == "warning_50"

    def test_multi_level_warnings_triggered(self):
        """Should trigger warnings at 50%, 75%, 90% thresholds."""
        tracker = CostTracker()
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Simulate spending at each threshold
        tracker.daily_total = Decimal("5.00")  # 50%
        tracker._emit_warning("warning")

        tracker.daily_total = Decimal("7.50")  # 75%
        tracker._emit_warning("warning")

        tracker.daily_total = Decimal("9.00")  # 90%
        tracker._emit_warning("warning")

        assert len(alerts_received) == 3
        assert alerts_received[0].alert_type == "warning_50"
        assert alerts_received[1].alert_type == "warning_75"
        assert alerts_received[2].alert_type == "warning_90"

    def test_each_warning_level_once_per_day(self):
        """Should only show each warning level once per day."""
        tracker = CostTracker()
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Trigger 50% warning
        tracker.daily_total = Decimal("5.00")
        tracker._emit_warning("warning")

        # Try to trigger again (should not duplicate)
        tracker._emit_warning("warning")

        # Add another transaction
        tracker.record(
            task_id="test-task",
            tier="L0",
            model="test-model",
            tokens=TokenCount(prompt_tokens=1000, completion_tokens=500),
            duration=1.0
        )

        # Should still only have one 50% alert
        warning_50_alerts = [a for a in alerts_received if a.alert_type == "warning_50"]
        assert len(warning_50_alerts) == 1

    def test_daily_reset_of_warning_levels(self):
        """Should reset warning levels on new day."""
        tracker = CostTracker()
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Day 1: Trigger 50% warning
        tracker._current_date = datetime.now(UTC).date()
        tracker.daily_total = Decimal("5.00")
        tracker._emit_warning("warning")

        assert len(alerts_received) == 1

        # Day 2: Trigger 50% again (should work after reset)
        tracker._current_date = datetime.now(UTC).date() + timedelta(days=1)
        tracker.daily_total = Decimal("5.00")
        tracker._check_and_reset_daily_flags()
        tracker._emit_warning("warning")

        # Should have another 50% alert
        warning_50_alerts = [a for a in alerts_received if a.alert_type == "warning_50"]
        assert len(warning_50_alerts) == 2

    def test_emergency_alert(self):
        """Should trigger emergency alert."""
        tracker = CostTracker()
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Set daily total to exceed emergency threshold (10 + 5 = 15)
        tracker.daily_total = Decimal("15.00")
        tracker._emit_warning("emergency")

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == "emergency"

    def test_custom_warning_thresholds(self):
        """Should respect custom warning thresholds."""
        tracker = CostTracker(
            budget=Budget(
                daily_limit_usd=Decimal("10.00"),
                warn_thresholds=[Decimal("0.25"), Decimal("0.50"), Decimal("0.75")]
            )
        )
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Set daily total to 25% (should trigger custom threshold)
        tracker.daily_total = Decimal("2.50")
        tracker._emit_warning("warning")

        # Should not trigger 50% yet
        assert len(alerts_received) == 1

        # Set to 50%
        tracker.daily_total = Decimal("5.00")
        tracker._emit_warning("warning")

        assert len(alerts_received) == 2


class TestCostTrackingWithAlerts:
    """Integration tests for cost tracking with alert callbacks."""

    def test_record_triggers_warning(self):
        """Should trigger warning when recording crosses threshold."""
        tracker = CostTracker(
            budget=Budget(
                daily_limit_usd=Decimal("10.00"),
                warn_thresholds=[Decimal("0.5")]  # Trigger at 50%
            )
        )
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        tracker.add_alert_callback(capture_alert)

        # Manually set daily_total to 50% to trigger warning
        tracker.daily_total = Decimal("5.00")
        tracker._emit_warning("warning")

        # Should have triggered 50% warning
        warning_alerts = [a for a in alerts_received if a.alert_type.startswith("warning")]
        assert len(warning_alerts) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
