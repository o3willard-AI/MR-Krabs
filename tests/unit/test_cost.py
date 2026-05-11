#!/usr/bin/env python3
"""Unit tests for cost tracking, budget reservation, and currency precision."""

import sys
import threading
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.cost import CostTracker, Budget, TokenCount, BudgetExceededError, FailureMode, Reservation


class TestTokenCount:
    def test_auto_total(self):
        t = TokenCount(prompt_tokens=100, completion_tokens=50)
        assert t.total_tokens == 150

    def test_explicit_total(self):
        t = TokenCount(prompt_tokens=100, completion_tokens=50, total_tokens=200)
        assert t.total_tokens == 200


class TestBudget:
    def test_default_values(self):
        b = Budget()
        assert b.daily_limit_usd == Decimal("10.00")
        assert b.failure_mode == FailureMode.FAIL_OPEN_WITH_ALERT
        assert b.emergency_cap_usd == Decimal("5.00")

    def test_is_exceeded(self):
        b = Budget(daily_limit_usd=Decimal("10.00"))
        assert not b.is_exceeded(Decimal("5.00"))
        assert b.is_exceeded(Decimal("10.00"))
        assert b.is_exceeded(Decimal("15.00"))

    def test_is_warning(self):
        b = Budget(daily_limit_usd=Decimal("10.00"), warning_threshold=Decimal("0.8"))
        assert not b.is_warning(Decimal("7.00"))
        assert b.is_warning(Decimal("8.00"))

    def test_emergency_exceeded(self):
        b = Budget(daily_limit_usd=Decimal("10.00"), emergency_cap_usd=Decimal("5.00"))
        assert not b.is_emergency_exceeded(Decimal("14.00"))
        assert b.is_emergency_exceeded(Decimal("15.00"))


class TestCostTracker:
    def test_calculate_cost(self):
        tracker = CostTracker()
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)
        cost = tracker.calculate_cost("x-ai/grok-4.1-fast", tokens)
        assert isinstance(cost, Decimal)
        assert cost == Decimal("0.0000050")

    def test_decimal_precision(self):
        tracker = CostTracker()
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=0)
        cost = tracker.calculate_cost("x-ai/grok-4.1-fast", tokens)
        assert isinstance(cost, Decimal)

    def test_record_and_total(self):
        tracker = CostTracker()
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)
        tracker.record("task-1", "L0", "x-ai/grok-4.1-fast", tokens, 1.0)
        assert tracker.get_daily_total() > Decimal("0")
        assert tracker.get_task_total("task-1") > Decimal("0")

    def test_budget_exceeded(self):
        budget = Budget(daily_limit_usd=Decimal("0.000001"))
        tracker = CostTracker(budget=budget)
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)
        try:
            tracker.record("task-1", "L0", "x-ai/grok-4.1-fast", tokens, 1.0)
            assert False, "Should have raised BudgetExceededError"
        except BudgetExceededError:
            pass

    def test_get_summary(self):
        tracker = CostTracker()
        tokens = TokenCount(prompt_tokens=1000, completion_tokens=500)
        tracker.record("task-1", "L0", "x-ai/grok-4.1-fast", tokens, 1.0)
        summary = tracker.get_summary()
        assert "daily_total" in summary
        assert "budget_remaining" in summary
        # Note: get_summary returns floats for serialization purposes, not Decimals
        assert isinstance(summary["daily_total"], float)

    def test_reservation_pattern(self):
        tracker = CostTracker(budget=Budget(daily_limit_usd=Decimal("10.00"), task_limit_usd=Decimal("5.00")))
        r = tracker.reserve_budget("task-1", Decimal("3.00"))
        assert isinstance(r, Reservation)
        assert tracker.reserved_total == Decimal("3.00")
        tracker.finalize_spending(r.id, Decimal("2.50"))
        assert tracker.daily_total == Decimal("2.50")
        assert tracker.reserved_total == Decimal("0.00")

    def test_reservation_release(self):
        tracker = CostTracker(budget=Budget(daily_limit_usd=Decimal("10.00"), task_limit_usd=Decimal("5.00")))
        r = tracker.reserve_budget("task-1", Decimal("3.00"))
        tracker.release_reservation(r.id)
        assert tracker.reserved_total == Decimal("0.00")
        assert tracker.daily_total == Decimal("0.00")

    def test_reservation_budget_limit(self):
        tracker = CostTracker(budget=Budget(daily_limit_usd=Decimal("5.00"), task_limit_usd=Decimal("5.00")))
        tracker.reserve_budget("task-1", Decimal("3.00"))
        tracker.reserve_budget("task-2", Decimal("1.00"))
        try:
            tracker.reserve_budget("task-3", Decimal("2.00"))
            assert False, "Should have raised BudgetExceededError"
        except BudgetExceededError:
            pass

    def test_per_task_cost_limit(self):
        tracker = CostTracker(budget=Budget(daily_limit_usd=Decimal("10.00"), task_limit_usd=Decimal("1.00")))
        try:
            tracker.reserve_budget("task-1", Decimal("3.00"))
            assert False, "Should have raised BudgetExceededError"
        except BudgetExceededError as e:
            assert "per-task limit" in str(e).lower()

    def test_concurrent_reservation_safety(self):
        tracker = CostTracker(budget=Budget(daily_limit_usd=Decimal("10.00"), task_limit_usd=Decimal("5.00")))
        errors = []
        success_count = [0]
        lock = threading.Lock()

        def task(i):
            try:
                r = tracker.reserve_budget(f"task-{i}", Decimal("0.50"))
                with lock:
                    success_count[0] += 1
                tracker.finalize_spending(r.id, Decimal("0.40"))
            except BudgetExceededError:
                pass
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=task, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert tracker.daily_total <= Decimal("10.50")


def test_decimal_precision():
    from decimal import Decimal
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


def test_no_float_drift():
    from decimal import Decimal
    total = Decimal("0")
    increment = Decimal("0.0001")
    for _ in range(10000):
        total += increment
    assert total == Decimal("1.0000")


class TestFailureMode:
    def test_fail_open_with_alert_default(self):
        b = Budget()
        assert b.failure_mode == FailureMode.FAIL_OPEN_WITH_ALERT

    def test_fail_closed(self):
        b = Budget(failure_mode=FailureMode.FAIL_CLOSED)
        assert b.failure_mode == FailureMode.FAIL_CLOSED