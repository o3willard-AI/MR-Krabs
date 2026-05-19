"""Budget-aware alerting and auto-response.

Monitors budget levels and automatically adjusts routing behavior,
logs warnings, and triggers alerts before budget thresholds are breached.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any


@dataclass
class BudgetStatus:
    """Current budget status."""
    remaining: Decimal = Decimal("10.00")
    daily_limit: Decimal = Decimal("10.00")
    percent_remaining: float = 100.0
    level: str = "normal"  # normal, warning, critical, exhausted
    projected_exhaustion: Optional[str] = None  # ISO timestamp


class BudgetAlerter:
    """Monitors budget and adjusts behavior at warning/critical/exhausted thresholds.
    
    Thresholds (configurable):
    - warning (default 20%): Log warnings, downgrade routing to cost_aware
    - critical (default 10%): Block L2+ tiers
    - exhausted (0%): Block all ask() calls
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._warning_threshold = float(self._config.get("budget_warning_threshold_pct", 20))
        self._critical_threshold = float(self._config.get("budget_critical_threshold_pct", 10))
        self._daily_limit = Decimal(str(self._config.get("budget_daily_limit", 10.00)))
        self._remaining = self._daily_limit
        self._spent = Decimal("0")
    
    @property
    def remaining(self) -> Decimal:
        return self._remaining
    
    @property
    def percent_remaining(self) -> float:
        if self._daily_limit == 0:
            return 0.0
        return float(self._remaining / self._daily_limit * 100)
    
    @property
    def level(self) -> str:
        if self._remaining <= 0:
            return "exhausted"
        if self.percent_remaining <= self._critical_threshold:
            return "critical"
        if self.percent_remaining <= self._warning_threshold:
            return "warning"
        return "normal"
    
    def record_spend(self, amount: float) -> None:
        """Record spending against the budget."""
        self._spent += Decimal(str(amount))
        self._remaining = max(Decimal("0"), self._daily_limit - self._spent)
    
    def can_proceed(self, estimated_cost: float, tier: str = "L0") -> tuple[bool, str]:
        """Check if a request can proceed based on budget and tier.
        
        Returns:
            (allowed, reason) tuple
        """
        if self._remaining <= 0:
            return (False, "Budget exhausted")
        
        cost = Decimal(str(estimated_cost))
        
        if self.level == "critical":
            if tier in ("L2", "L3"):
                return (False, f"Budget critical ({self.percent_remaining:.0f}%) — tier {tier} blocked")
            if cost > self._remaining:
                return (False, f"Budget critical — cost ${estimated_cost} exceeds remaining ${self._remaining}")
        
        if self.level == "warning":
            if cost > self._remaining:
                return (False, f"Budget warning — cost ${estimated_cost} exceeds remaining ${self._remaining}")
        
        if cost > self._remaining:
            return (False, f"Cost ${estimated_cost} exceeds remaining budget ${self._remaining}")
        
        return (True, "ok")
    
    def get_routing_recommendation(self) -> str:
        """Get recommended routing strategy based on budget level."""
        if self.level == "exhausted":
            return "none"  # Block all
        if self.level == "critical":
            return "cost_aware"  # Only cheapest providers
        if self.level == "warning":
            return "cost_aware"  # Prefer cost over latency
        return "smart"  # Normal multi-factor routing
    
    def get_budget_status(self) -> BudgetStatus:
        """Get full budget status for monitoring."""
        status = BudgetStatus(
            remaining=self._remaining,
            daily_limit=self._daily_limit,
            percent_remaining=self.percent_remaining,
            level=self.level,
        )
        
        # Project exhaustion time based on current spend rate
        if self._spent > 0 and self.level != "exhausted":
            # Simple linear projection — in production, use rolling window
            pass
        
        return status
