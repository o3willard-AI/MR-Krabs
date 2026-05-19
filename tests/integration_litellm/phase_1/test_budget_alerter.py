"""Phase 1: Budget alerter tests."""

import pytest
from decimal import Decimal
from src.metrics.budget_alerter import BudgetAlerter, BudgetStatus


@pytest.fixture
def alerter():
    """Create a BudgetAlerter with default $10/day limit."""
    return BudgetAlerter(config={"budget_daily_limit": 10.00})


@pytest.fixture
def tight_alerter():
    """Create a BudgetAlerter with $1/day limit for threshold testing."""
    return BudgetAlerter(config={
        "budget_daily_limit": 1.00,
        "budget_warning_threshold_pct": 20,
        "budget_critical_threshold_pct": 10,
    })


class TestBudgetAlerter:
    """Core budget alerter tests."""
    
    def test_default_level_is_normal(self, alerter):
        assert alerter.level == "normal"
        assert alerter.percent_remaining == 100.0
    
    def test_spend_reduces_remaining(self, alerter):
        alerter.record_spend(2.50)
        assert alerter.remaining == Decimal("7.50")
        assert alerter.percent_remaining == 75.0
    
    def test_spend_exact_limit(self, alerter):
        alerter.record_spend(10.00)
        assert alerter.remaining == Decimal("0")
        assert alerter.level == "exhausted"
    
    def test_spend_beyond_limit(self, alerter):
        alerter.record_spend(15.00)
        assert alerter.remaining == Decimal("0")
        assert alerter.level == "exhausted"
    
    def test_warning_level(self, alerter):
        alerter.record_spend(8.50)  # 15% remaining → warning (below 20%)
        assert alerter.level == "warning"
    
    def test_critical_level(self, alerter):
        alerter.record_spend(9.50)  # 5% remaining → critical (below 10%)
        assert alerter.level == "critical"
    
    def test_multiple_spends(self, alerter):
        alerter.record_spend(3.00)
        alerter.record_spend(4.00)
        alerter.record_spend(1.50)
        assert alerter.remaining == Decimal("1.50")
        assert alerter.level == "warning"  # 15% → warning
    
    def test_can_proceed_normal(self, alerter):
        ok, reason = alerter.can_proceed(1.00)
        assert ok is True
        assert reason == "ok"
    
    def test_can_proceed_insufficient(self, alerter):
        ok, reason = alerter.can_proceed(11.00)
        assert ok is False
    
    def test_can_proceed_exhausted(self, alerter):
        alerter.record_spend(10.00)
        ok, reason = alerter.can_proceed(0.01)
        assert ok is False
        assert "exhausted" in reason.lower()
    
    def test_critical_blocks_l2_tier(self, tight_alerter):
        tight_alerter.record_spend(0.95)  # 5% remaining → critical
        ok, reason = tight_alerter.can_proceed(0.01, tier="L2")
        assert ok is False
        assert "critical" in reason.lower()
    
    def test_critical_allows_l0_tier(self, tight_alerter):
        tight_alerter.record_spend(0.95)  # 5% remaining → critical
        ok, reason = tight_alerter.can_proceed(0.01, tier="L0")
        assert ok is True
    
    def test_routing_normal(self, alerter):
        assert alerter.get_routing_recommendation() == "smart"
    
    def test_routing_warning(self, alerter):
        alerter.record_spend(8.50)  # warning
        assert alerter.get_routing_recommendation() == "cost_aware"
    
    def test_routing_exhausted(self, alerter):
        alerter.record_spend(10.00)  # exhausted
        assert alerter.get_routing_recommendation() == "none"


class TestBudgetStatus:
    """BudgetStatus dataclass tests."""
    
    def test_budget_status_defaults(self):
        status = BudgetStatus()
        assert status.remaining == Decimal("10.00")
        assert status.level == "normal"
    
    def test_budget_status_critical(self):
        status = BudgetStatus(
            remaining=Decimal("0.50"),
            daily_limit=Decimal("10.00"),
            percent_remaining=5.0,
            level="critical",
        )
        assert status.level == "critical"


class TestCustomThresholds:
    """Custom threshold configuration tests."""
    
    def test_custom_warning_threshold(self):
        alerter = BudgetAlerter(config={
            "budget_daily_limit": 100.00,
            "budget_warning_threshold_pct": 50,
            "budget_critical_threshold_pct": 25,
        })
        alerter.record_spend(60.00)  # 40% remaining → below 50% warning
        assert alerter.level == "warning"
    
    def test_custom_critical_threshold(self):
        alerter = BudgetAlerter(config={
            "budget_daily_limit": 100.00,
            "budget_warning_threshold_pct": 50,
            "budget_critical_threshold_pct": 25,
        })
        alerter.record_spend(80.00)  # 20% remaining → below 25% critical
        assert alerter.level == "critical"
