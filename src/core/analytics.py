#!/usr/bin/env python3
"""Advanced analytics for tier performance and cost optimization.

P2-5: Advanced Analytics
Provides detailed analytics on tier performance, success rates, and cost optimization.

Features:
- Tier success rates tracking
- Cost breakdown by tier
- Tier effectiveness recommendations
- Provider comparison
- Historical trends
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TierAnalytics:
    """Analytics for a single tier."""
    
    tier: str
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    total_cost: Decimal = field(default_factory=lambda: Decimal("0.0"))
    total_tokens: int = 0
    avg_duration: float = 0.0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        self._success_rate = Decimal("0.0")
        self._avg_cost_per_success = Decimal("0.0")
        self._update_metrics()
    
    def update(
        self, 
        success: bool, 
        cost: Decimal, 
        tokens: int, 
        duration: float
    ):
        """Update analytics with new data."""
        self.total_attempts += 1
        self.total_cost += cost
        self.total_tokens += tokens
        self.avg_duration = (
            (self.avg_duration * (self.total_attempts - 1) + duration)
            / self.total_attempts
        )
        
        if success:
            self.successful_attempts += 1
        else:
            self.failed_attempts += 1
        
        self._update_metrics()
    
    def _update_metrics(self):
        """Update derived metrics."""
        if self.total_attempts > 0:
            self._success_rate = (
                Decimal(str(self.successful_attempts)) / Decimal(str(self.total_attempts)) * Decimal("100")
            )
        
        if self.successful_attempts > 0:
            self._avg_cost_per_success = (
                self.total_cost / self.successful_attempts
            )
        else:
            self._avg_cost_per_success = Decimal("0.0")
    
    @property
    def avg_success_rate(self) -> float:
        """Get average success rate."""
        return self._success_rate
    
    @property
    def avg_cost_per_success(self) -> Decimal:
        """Get average cost per successful attempt."""
        return self._avg_cost_per_success
    
    def __repr__(self) -> str:
        return (
            f"TierAnalytics("
            f"tier={self.tier}, "
            f"attempts={self.total_attempts}, "
            f"success_rate={self._success_rate:.1f}%, "
            f"cost=${float(self.total_cost):.4f}"
            f")"
        )


@dataclass
class AnalyticsSummary:
    """Overall analytics summary."""
    
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_tasks: int = 0
    overall_success_rate: float = 0.0
    total_cost: Decimal = field(default_factory=lambda: Decimal("0.0"))
    avg_cost_per_task: Decimal = field(default_factory=lambda: Decimal("0.0"))
    
    # Tier analytics
    tier_analytics: Dict[str, TierAnalytics] = field(default_factory=dict)
    
    # Provider analytics
    provider_analytics: Dict[str, Dict] = field(default_factory=dict)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Time range
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def add_tier_analytics(self, tier: str, analytics: TierAnalytics):
        """Add tier analytics."""
        self.tier_analytics[tier] = analytics
    
    def add_provider_analytics(self, provider: str, data: Dict):
        """Add provider analytics."""
        if provider not in self.provider_analytics:
            self.provider_analytics[provider] = {
                "total_cost": Decimal("0.0"),
                "total_tasks": 0,
                "success_rate": 0.0,
            }
        
        self.provider_analytics[provider]["total_cost"] += Decimal(str(data.get("cost", 0)))
        self.provider_analytics[provider]["total_tasks"] += 1
    
    def generate_recommendations(self):
        """Generate actionable recommendations."""
        recommendations = []
        
        # Detect over-provisioning (high success rate on expensive tiers)
        for tier, analytics in sorted(
            self.tier_analytics.items(),
            key=lambda x: x[1].avg_success_rate,
            reverse=True
        ):
            tier_number = self._get_tier_number(tier)
            
            # If L2 or L3 has very high success rate, suggest starting lower
            if tier_number >= 2 and analytics.avg_success_rate > 95:
                lower_tier = self._get_lower_tier(tier)
                savings = self._calculate_potential_savings(
                    tier, lower_tier
                )
                
                recommendations.append(
                    f"{tier} has {analytics.avg_success_rate:.1f}% success rate. "
                    f"Consider starting at {lower_tier} to save ~${savings:.2f}"
                )
        
        # Detect under-provisioning (low success rate, suggest higher tier)
        for tier, analytics in sorted(
            self.tier_analytics.items(),
            key=lambda x: x[1].avg_success_rate
        ):
            tier_number = self._get_tier_number(tier)
            
            # If L0 or L1 has low success rate, suggest starting higher
            if tier_number <= 1 and analytics.avg_success_rate < 70:
                higher_tier = self._get_higher_tier(tier)
                
                recommendations.append(
                    f"{tier} has {analytics.avg_success_rate:.1f}% success rate. "
                    f"Consider starting at {higher_tier} to improve success"
                )
        
        # Cost optimization suggestions
        if self.tier_analytics.get("L0-Planner"):
            l0_analytics = self.tier_analytics["L0-Planner"]
            if l0_analytics.avg_success_rate > 85:
                savings = self._calculate_l0_savings()
                recommendations.append(
                    f"L0-Planner has {l0_analytics.avg_success_rate:.1f}% success rate. "
                    f"Most tasks complete at L0, saving ~${savings:.2f}/day"
                )
        
        # Provider comparison
        if len(self.provider_analytics) >= 2:
            best_provider = max(
                self.provider_analytics.items(),
                key=lambda x: x[1].get("success_rate", 0) / max(x[1].get("total_cost", 0.01), 0.001)
            )
            recommendations.append(
                f"{best_provider[0]} provides best cost-effectiveness ratio"
            )
        
        self.recommendations = recommendations
    
    def _get_tier_number(self, tier: str) -> int:
        """Get tier number from tier name."""
        tier_map = {
            "L0-Planner": 0,
            "L1-Coder": 1,
            "L2-Coder": 2,
            "L3-Coder": 3,
        }
        return tier_map.get(tier, 0)
    
    def _get_lower_tier(self, tier: str) -> str:
        """Get lower tier name."""
        tier_map = {
            "L1-Coder": "L0-Planner",
            "L2-Coder": "L1-Coder",
            "L3-Coder": "L2-Coder",
        }
        return tier_map.get(tier, "L0-Planner")
    
    def _get_higher_tier(self, tier: str) -> str:
        """Get higher tier name."""
        tier_map = {
            "L0-Planner": "L1-Coder",
            "L1-Coder": "L2-Coder",
            "L2-Coder": "L3-Coder",
        }
        return tier_map.get(tier, "L3-Coder")
    
    def _calculate_potential_savings(
        self, 
        current_tier: str, 
        suggested_tier: str
    ) -> Decimal:
        """Calculate potential savings from tier change."""
        if current_tier not in self.tier_analytics:
            return Decimal("0.0")
        
        current_cost = self.tier_analytics[current_tier].total_cost
        
        # Estimate savings (very rough)
        # Convert to float first to avoid Decimal * float error
        return Decimal(str(current_cost)) * Decimal("0.7")  # Assume 70% savings
    
    def _calculate_l0_savings(self) -> Decimal:
        """Calculate savings from L0 usage."""
        if not self.tier_analytics.get("L0-Planner"):
            return Decimal("0.0")
        
        l0_cost = self.tier_analytics["L0-Planner"].total_cost
        l3_cost = Decimal("0.12")  # GPT-4o cost per task
        
        # If all tasks used L3, cost would be:
        all_l3_cost = Decimal(str(self.total_tasks * 0.12))
        
        return all_l3_cost - self.total_cost
    
    def get_tier_breakdown(self) -> Dict[str, Dict]:
        """Get tier breakdown for display."""
        breakdown = {}
        
        for tier, analytics in self.tier_analytics.items():
            breakdown[tier] = {
                "attempts": analytics.total_attempts,
                "success_rate": float(analytics._success_rate),
                "cost": float(analytics.total_cost),
                "avg_cost": float(analytics._avg_cost_per_success),
                "status": self._get_tier_status(analytics),
            }
        
        return breakdown
    
    def _get_tier_status(self, analytics: TierAnalytics) -> str:
        """Get tier status indicator."""
        if analytics.avg_success_rate >= 90:
            return "✓ Optimal"
        elif analytics.avg_success_rate >= 75:
            return "⚠ Good"
        else:
            return "✗ Needs adjustment"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "generated_at": self.generated_at,
            "total_tasks": self.total_tasks,
            "overall_success_rate": float(self.overall_success_rate),
            "total_cost": float(self.total_cost),
            "avg_cost_per_task": float(self.avg_cost_per_task),
            "tier_breakdown": self.get_tier_breakdown(),
            "provider_breakdown": {
                provider: {
                    "total_cost": float(data["total_cost"]),
                    "total_tasks": data["total_tasks"],
                    "success_rate": data["success_rate"],
                }
                for provider, data in self.provider_analytics.items()
            },
            "recommendations": self.recommendations,
        }


class AnalyticsCollector:
    """Collects and aggregates analytics data."""
    
    def __init__(self):
        self.tier_data: Dict[str, TierAnalytics] = {}
        self.provider_data: Dict[str, Dict] = {}
        self.total_tasks = 0
        self.total_cost = Decimal("0.0")
        self.successful_tasks = 0
        self.start_time = time.time()
    
    def record_tier_event(
        self,
        tier: str,
        success: bool,
        cost: Decimal,
        tokens: int,
        duration: float
    ):
        """Record a tier event for analytics."""
        # Ensure tier analytics exists
        if tier not in self.tier_data:
            self.tier_data[tier] = TierAnalytics(tier=tier)
        
        # Update tier analytics
        self.tier_data[tier].update(success, cost, tokens, duration)
        
        # Update totals
        self.total_tasks += 1
        self.total_cost += cost
        
        if success:
            self.successful_tasks += 1
    
    def record_provider_event(
        self,
        provider: str,
        cost: Decimal,
        success: bool
    ):
        """Record a provider event."""
        if provider not in self.provider_data:
            self.provider_data[provider] = {
                "total_cost": Decimal("0.0"),
                "total_tasks": 0,
                "successful_tasks": 0,
            }
        
        self.provider_data[provider]["total_cost"] += cost
        self.provider_data[provider]["total_tasks"] += 1
        
        if success:
            self.provider_data[provider]["successful_tasks"] += 1
    
    def get_summary(self) -> AnalyticsSummary:
        """Get analytics summary."""
        summary = AnalyticsSummary(
            total_tasks=self.total_tasks,
            total_cost=self.total_cost,
            overall_success_rate=(
                Decimal(str(self.successful_tasks)) / Decimal(str(self.total_tasks)) * Decimal("100")
                if self.total_tasks > 0 else Decimal("0.0")
            ),
            avg_cost_per_task=(
                self.total_cost / self.total_tasks
                if self.total_tasks > 0 else Decimal("0.0")
            ),
            start_time=self.start_time,
            end_time=time.time(),
        )
        
        # Add tier analytics
        for tier, analytics in self.tier_data.items():
            summary.add_tier_analytics(tier, analytics)
        
        # Add provider analytics
        for provider, data in self.provider_data.items():
            success_rate = (
                Decimal(str(data["successful_tasks"])) / Decimal(str(data["total_tasks"])) * Decimal("100")
                if data["total_tasks"] > 0 else Decimal("0.0")
            )
            
            summary.add_provider_analytics(provider, {
                "total_cost": data["total_cost"],
                "total_tasks": data["total_tasks"],
                "success_rate": float(success_rate),
            })
        
        # Generate recommendations
        summary.generate_recommendations()
        
        return summary


# Integration helper
def create_analytics_collector() -> AnalyticsCollector:
    """Create an analytics collector instance."""
    return AnalyticsCollector()
