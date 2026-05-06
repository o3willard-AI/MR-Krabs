"""
Budget Enforcement for MR-Krabs MCP Server

Implements configurable budget enforcement modes:
- notify_only: Warn when threshold reached, continue execution
- fail: Immediately fail when budget would be exceeded
- notify_then_fail: Warn at 80%, fail at 100% (DEFAULT)
- fail_with_notification: Fail with detailed error message

Usage:
    enforcer = BudgetEnforcer(budget_limit=10.0, enforcement_mode="notify_then_fail")
    
    # Check before spending
    result = enforcer.check_budget(spent=5.0, would_spend=2.0)
    if result.warning:
        print(f"Warning: {result.warning}")
    
    # Record actual spending
    enforcer.record_spending(2.0)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EnforcementMode(Enum):
    """Budget enforcement modes."""
    NOTIFY_ONLY = "notify_only"
    FAIL = "fail"
    NOTIFY_THEN_FAIL = "notify_then_fail"
    FAIL_WITH_NOTIFICATION = "fail_with_notification"


@dataclass
class BudgetCheckResult:
    """Result of a budget check operation."""
    
    can_proceed: bool
    remaining_budget: float
    spent: float
    budget_limit: Optional[float]
    warning: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "can_proceed": self.can_proceed,
            "remaining_budget": self.remaining_budget,
            "spent": self.spent,
            "budget_limit": self.budget_limit,
            "warning": self.warning,
            "error": self.error,
        }


class BudgetEnforcer:
    """
    Enforces budget limits with configurable modes.
    
    Supports four enforcement strategies:
    1. notify_only: Warn at threshold but always allow execution
    2. fail: Immediately deny if budget would be exceeded
    3. notify_then_fail: Warn at 80%, deny at 100% (default)
    4. fail_with_notification: Deny with detailed error message
    
    Environment Variables:
        BUDGET_LIMIT: Default budget limit in USD (default: 10.0)
        WARNING_THRESHOLD: Warning threshold percentage (default: 80)
        ENFORCEMENT_MODE: Default enforcement mode (default: notify_then_fail)
    """
    
    def __init__(
        self,
        budget_limit: Optional[float] = None,
        enforcement_mode: str = "notify_then_fail",
        warning_threshold: float = 80.0,
    ):
        """
        Initialize budget enforcer.
        
        Args:
            budget_limit: Maximum budget in USD. None means unlimited.
                         Overrides BUDGET_LIMIT env var if provided.
            enforcement_mode: One of 'notify_only', 'fail', 'notify_then_fail', 
                            'fail_with_notification'. Default: notify_then_fail.
            warning_threshold: Percentage at which to issue warnings (default: 80).
        """
        self.budget_limit = budget_limit
        self._spent = 0.0
        self.warning_threshold = warning_threshold
        self.enforcement_mode = EnforcementMode(enforcement_mode)
    
    @property
    def spent(self) -> float:
        """Get total amount spent."""
        return self._spent
    
    @property
    def remaining(self) -> float:
        """Get remaining budget."""
        if self.budget_limit is None:
            return float('inf')
        return max(0.0, self.budget_limit - self._spent)
    
    @property
    def percentage_used(self) -> float:
        """Get percentage of budget used."""
        if self.budget_limit is None or self.budget_limit == 0:
            return 0.0
        return min(100.0, (self._spent / self.budget_limit) * 100)
    
    def check_budget(self, would_spend: float) -> BudgetCheckResult:
        """
        Check if a spending operation can proceed.
        
        Args:
            would_spend: Amount that would be spent
            
        Returns:
            BudgetCheckResult with can_proceed flag and optional warning/error
        """
        # No limit means always proceed
        if self.budget_limit is None:
            return BudgetCheckResult(
                can_proceed=True,
                remaining_budget=float('inf'),
                spent=self._spent,
                budget_limit=None,
            )
        
        total_after = self._spent + would_spend
        percentage_after = (total_after / self.budget_limit) * 100
        
        # Determine behavior based on enforcement mode
        if self.enforcement_mode == EnforcementMode.NOTIFY_ONLY:
            # Always allow, but warn at threshold
            warning = None
            if percentage_after >= self.warning_threshold:
                warning = f"Warning: {percentage_after:.1f}% of budget used"
            
            return BudgetCheckResult(
                can_proceed=True,
                remaining_budget=max(0.0, self.budget_limit - total_after),
                spent=total_after,
                budget_limit=self.budget_limit,
                warning=warning,
            )
        
        elif self.enforcement_mode == EnforcementMode.FAIL:
            # Fail immediately if would exceed budget
            if total_after > self.budget_limit:
                return BudgetCheckResult(
                    can_proceed=False,
                    remaining_budget=self.remaining,
                    spent=self._spent,
                    budget_limit=self.budget_limit,
                    error=f"Budget exceeded: would spend ${total_after:.2f} of ${self.budget_limit:.2f}",
                )
            return BudgetCheckResult(
                can_proceed=True,
                remaining_budget=max(0.0, self.budget_limit - total_after),
                spent=total_after,
                budget_limit=self.budget_limit,
            )
        
        elif self.enforcement_mode == EnforcementMode.NOTIFY_THEN_FAIL:
            # Warn at threshold, fail at 100%
            if total_after > self.budget_limit:
                return BudgetCheckResult(
                    can_proceed=False,
                    remaining_budget=self.remaining,
                    spent=self._spent,
                    budget_limit=self.budget_limit,
                    error=f"Budget exceeded: would spend ${total_after:.2f} of ${self.budget_limit:.2f}",
                )
            
            warning = None
            if percentage_after >= self.warning_threshold:
                warning = f"Warning: {percentage_after:.1f}% of budget used. ${self.budget_limit:.2f} limit."
            
            return BudgetCheckResult(
                can_proceed=True,
                remaining_budget=max(0.0, self.budget_limit - total_after),
                spent=total_after,
                budget_limit=self.budget_limit,
                warning=warning,
            )
        
        elif self.enforcement_mode == EnforcementMode.FAIL_WITH_NOTIFICATION:
            # Same as FAIL but with more detailed error
            if total_after > self.budget_limit:
                return BudgetCheckResult(
                    can_proceed=False,
                    remaining_budget=self.remaining,
                    spent=self._spent,
                    budget_limit=self.budget_limit,
                    error=(
                        f"BUDGET EXCEEDED - Execution blocked.\n"
                        f"Current spend: ${self._spent:.2f}\n"
                        f"Would spend: ${would_spend:.2f}\n"
                        f"Total would be: ${total_after:.2f}\n"
                        f"Budget limit: ${self.budget_limit:.2f}\n"
                        f"Remaining: ${self.remaining:.2f}"
                    ),
                )
            return BudgetCheckResult(
                can_proceed=True,
                remaining_budget=max(0.0, self.budget_limit - total_after),
                spent=total_after,
                budget_limit=self.budget_limit,
            )
        
        # Default: allow
        return BudgetCheckResult(
            can_proceed=True,
            remaining_budget=max(0.0, self.budget_limit - total_after) if self.budget_limit else float('inf'),
            spent=total_after,
            budget_limit=self.budget_limit,
        )
    
    def record_spending(self, amount: float) -> None:
        """
        Record actual spending.
        
        Args:
            amount: Amount actually spent
        """
        self._spent += amount
    
    def reset(self) -> None:
        """Reset spending tracker."""
        self._spent = 0.0
    
    def get_status(self) -> dict:
        """Get current budget status."""
        return {
            "budget_limit": self.budget_limit,
            "spent": self._spent,
            "remaining": self.remaining,
            "percentage_used": self.percentage_used,
            "enforcement_mode": self.enforcement_mode.value,
            "warning_threshold": self.warning_threshold,
        }
