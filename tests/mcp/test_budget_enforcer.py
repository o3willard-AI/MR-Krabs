"""
Unit tests for MR-Krabs MCP Server - Budget Enforcer

Tests cover:
- All four enforcement modes (notify_only, fail, notify_then_fail, fail_with_notification)
- Budget checking and spending recording
- Edge cases (unlimited budget, zero budget)
- Status reporting
"""

import pytest
from decimal import Decimal

from src.mcp.budget_enforcer import BudgetEnforcer, EnforcementMode, BudgetCheckResult


class TestBudgetEnforcerInit:
    """Test BudgetEnforcer initialization."""
    
    def test_default_values(self):
        """Test default configuration values."""
        enforcer = BudgetEnforcer()
        
        assert enforcer.budget_limit == 10.0
        assert enforcer.enforcement_mode == EnforcementMode.NOTIFY_THEN_FAIL
        assert enforcer.warning_threshold == 80.0
        assert enforcer.spent == 0.0
    
    def test_custom_values(self):
        """Test custom configuration values."""
        enforcer = BudgetEnforcer(
            budget_limit=25.0,
            enforcement_mode="fail",
            warning_threshold=90.0,
        )
        
        assert enforcer.budget_limit == 25.0
        assert enforcer.enforcement_mode == EnforcementMode.FAIL
        assert enforcer.warning_threshold == 90.0
    
    def test_unlimited_budget(self):
        """Test unlimited budget (None)."""
        enforcer = BudgetEnforcer(budget_limit=None)
        
        assert enforcer.budget_limit is None
        assert enforcer.remaining == float('inf')


class TestBudgetEnforcerProperties:
    """Test BudgetEnforcer properties."""
    
    def test_remaining_budget(self):
        """Test remaining budget calculation."""
        enforcer = BudgetEnforcer(budget_limit=10.0)
        enforcer._spent = 3.5
        
        assert enforcer.remaining == 6.5
    
    def test_remaining_budget_zero(self):
        """Test remaining budget when fully spent."""
        enforcer = BudgetEnforcer(budget_limit=10.0)
        enforcer._spent = 10.0
        
        assert enforcer.remaining == 0.0
    
    def test_remaining_budget_unlimited(self):
        """Test remaining budget with no limit."""
        enforcer = BudgetEnforcer(budget_limit=None)
        enforcer._spent = 100.0
        
        assert enforcer.remaining == float('inf')
    
    def test_percentage_used(self):
        """Test percentage used calculation."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        enforcer._spent = 25.0
        
        assert enforcer.percentage_used == 25.0
    
    def test_percentage_used_over_100(self):
        """Test percentage used when over budget."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        enforcer._spent = 150.0
        
        assert enforcer.percentage_used == 100.0  # Capped at 100%
    
    def test_percentage_used_unlimited(self):
        """Test percentage used with no limit."""
        enforcer = BudgetEnforcer(budget_limit=None)
        enforcer._spent = 100.0
        
        assert enforcer.percentage_used == 0.0


class TestNotifyOnlyMode:
    """Test NOTIFY_ONLY enforcement mode."""
    
    def test_below_threshold(self):
        """Test spending below warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_only",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=50.0)
        
        assert result.can_proceed is True
        assert result.warning is None
        assert result.error is None
    
    def test_at_threshold(self):
        """Test spending at warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_only",
            warning_threshold=80.0,
        )
        enforcer._spent = 40.0
        
        result = enforcer.check_budget(would_spend=40.0)  # Total = 80%
        
        assert result.can_proceed is True
        assert result.warning is not None
        assert "80.0%" in result.warning
        assert result.error is None
    
    def test_above_threshold(self):
        """Test spending above warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_only",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=90.0)  # Total = 90%
        
        assert result.can_proceed is True
        assert result.warning is not None
        assert "90.0%" in result.warning
    
    def test_exceeds_budget(self):
        """Test spending that exceeds budget (still allowed)."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_only",
        )
        
        result = enforcer.check_budget(would_spend=150.0)  # Would exceed
        
        assert result.can_proceed is True  # Still allowed in notify_only mode


class TestFailMode:
    """Test FAIL enforcement mode."""
    
    def test_within_budget(self):
        """Test spending within budget."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="fail",
        )
        
        result = enforcer.check_budget(would_spend=50.0)
        
        assert result.can_proceed is True
        assert result.warning is None
        assert result.error is None
    
    def test_exceeds_budget(self):
        """Test spending that exceeds budget."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="fail",
        )
        
        result = enforcer.check_budget(would_spend=150.0)
        
        assert result.can_proceed is False
        assert result.error is not None
        assert "Budget exceeded" in result.error
    
    def test_exact_budget(self):
        """Test spending exactly equal to budget."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="fail",
        )
        
        result = enforcer.check_budget(would_spend=100.0)
        
        assert result.can_proceed is True  # Exactly at limit is OK


class TestNotifyThenFailMode:
    """Test NOTIFY_THEN_FAIL enforcement mode (default)."""
    
    def test_below_threshold(self):
        """Test spending below warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=50.0)
        
        assert result.can_proceed is True
        assert result.warning is None
    
    def test_at_warning_threshold(self):
        """Test spending at warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=80.0)
        
        assert result.can_proceed is True
        assert result.warning is not None
        assert "80.0%" in result.warning
    
    def test_above_warning_below_limit(self):
        """Test spending above warning but below limit."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=95.0)
        
        assert result.can_proceed is True
        assert result.warning is not None
    
    def test_exceeds_budget(self):
        """Test spending that exceeds budget."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
        )
        
        result = enforcer.check_budget(would_spend=150.0)
        
        assert result.can_proceed is False
        assert result.error is not None
    
    def test_with_existing_spending(self):
        """Test with existing spending."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=80.0,
        )
        enforcer._spent = 70.0
        
        result = enforcer.check_budget(would_spend=20.0)  # Total = 90%
        
        assert result.can_proceed is True
        assert result.warning is not None
        
        result = enforcer.check_budget(would_spend=35.0)  # Total = 105%
        
        assert result.can_proceed is False


class TestFailWithNotificationMode:
    """Test FAIL_WITH_NOTIFICATION enforcement mode."""
    
    def test_within_budget(self):
        """Test spending within budget."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="fail_with_notification",
        )
        
        result = enforcer.check_budget(would_spend=50.0)
        
        assert result.can_proceed is True
        assert result.error is None
    
    def test_exceeds_budget_detailed_error(self):
        """Test spending that exceeds budget with detailed error."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="fail_with_notification",
        )
        enforcer._spent = 80.0
        
        result = enforcer.check_budget(would_spend=30.0)  # Would be 110%
        
        assert result.can_proceed is False
        assert result.error is not None
        assert "BUDGET EXCEEDED" in result.error
        assert "Current spend: $80.00" in result.error
        assert "Would spend: $30.00" in result.error
        assert "Total would be: $110.00" in result.error
        assert "Budget limit: $100.00" in result.error


class TestUnlimitedBudget:
    """Test behavior with unlimited budget."""
    
    def test_any_mode_allows(self):
        """Test that unlimited budget allows any spending."""
        enforcer = BudgetEnforcer(
            budget_limit=None,
            enforcement_mode="fail",  # Even strict mode
        )
        
        result = enforcer.check_budget(would_spend=999999.0)
        
        assert result.can_proceed is True
        assert result.budget_limit is None


class TestRecordSpending:
    """Test spending recording."""
    
    def test_record_single_spending(self):
        """Test recording a single spending."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        
        enforcer.record_spending(25.0)
        
        assert enforcer.spent == 25.0
        assert enforcer.remaining == 75.0
    
    def test_record_multiple_spending(self):
        """Test recording multiple spendings."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        
        enforcer.record_spending(25.0)
        enforcer.record_spending(30.0)
        enforcer.record_spending(15.0)
        
        assert enforcer.spent == 70.0
        assert enforcer.remaining == 30.0
    
    def test_reset(self):
        """Test resetting spending tracker."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        
        enforcer.record_spending(50.0)
        assert enforcer.spent == 50.0
        
        enforcer.reset()
        
        assert enforcer.spent == 0.0


class TestGetStatus:
    """Test status reporting."""
    
    def test_status_all_fields(self):
        """Test that status includes all required fields."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=85.0,
        )
        enforcer._spent = 25.0
        
        status = enforcer.get_status()
        
        assert status["budget_limit"] == 100.0
        assert status["spent"] == 25.0
        assert status["remaining"] == 75.0
        assert status["percentage_used"] == 25.0
        assert status["enforcement_mode"] == "notify_then_fail"
        assert status["warning_threshold"] == 85.0


class TestBudgetCheckResult:
    """Test BudgetCheckResult dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = BudgetCheckResult(
            can_proceed=True,
            remaining_budget=75.0,
            spent=25.0,
            budget_limit=100.0,
            warning="Warning message",
            error=None,
        )
        
        data = result.to_dict()
        
        assert data["can_proceed"] is True
        assert data["remaining_budget"] == 75.0
        assert data["spent"] == 25.0
        assert data["budget_limit"] == 100.0
        assert data["warning"] == "Warning message"
        assert data["error"] is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_zero_budget(self):
        """Test with zero budget."""
        enforcer = BudgetEnforcer(budget_limit=0.0, enforcement_mode="fail")
        
        result = enforcer.check_budget(would_spend=0.01)
        
        assert result.can_proceed is False
    
    def test_very_small_amount(self):
        """Test with very small spending amount."""
        enforcer = BudgetEnforcer(budget_limit=100.0)
        
        result = enforcer.check_budget(would_spend=0.001)
        
        assert result.can_proceed is True
    
    def test_exact_boundary(self):
        """Test exact boundary at warning threshold."""
        enforcer = BudgetEnforcer(
            budget_limit=100.0,
            enforcement_mode="notify_then_fail",
            warning_threshold=80.0,
        )
        
        result = enforcer.check_budget(would_spend=79.99)
        
        assert result.can_proceed is True
        assert result.warning is None  # Below threshold
        
        result = enforcer.check_budget(would_spend=80.0)
        
        assert result.warning is not None  # At threshold
