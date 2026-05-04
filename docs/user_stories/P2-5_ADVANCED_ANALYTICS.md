# Story P2-5: Advanced Analytics & Success Rates

**Priority**: P2 (Medium - Enhances Intelligence)  
**Estimate**: 1 week  
**Phase**: Week 15

---

## User Story

As a developer  
I want detailed analytics on tier performance and success rates  
So that I can make informed decisions about tier assignments and optimize my costs further

---

## Acceptance Criteria

### AC1: Tier Success Rates

- [ ] Success rate calculated per tier
- [ ] Success rate updated after each task
- [ ] Minimum 10 samples for statistical significance
- [ ] Success rate visible in `orchestrator stats`
- [ ] Success rate available via API

### AC2: Cost Breakdown by Tier

- [ ] Total cost per tier tracked
- [ ] Average cost per tier calculated
- [ ] Cost variance tracked (std dev)
- [ ] Tier cost breakdown in stats output
- [ ] Cost savings vs. premium-only calculated

### AC3: Tier Effectiveness Recommendations

- [ ] "Best tier for task type" suggestions
- [ ] "Escalation patterns" analysis
- [ ] "Over-provisioning" detection
- [ ] "Under-provisioning" detection
- [ ] Recommendations actionable and clear

### AC4: Provider Comparison

- [ ] Success rate by provider
- [ ] Cost by provider
- [ ] Provider efficiency metrics
- [ ] Provider comparison in analytics
- [ ] Provider recommendations

### AC5: Historical Trends

- [ ] Success rate trends over time
- [ ] Cost trends over time
- [ ] Usage patterns by day/hour
- [ ] Weekly and monthly summaries
- [ ] Trend visualizations (text-based)

### AC6: Export & Integration

- [ ] Analytics exportable to JSON
- [ ] CSV export for spreadsheet analysis
- [ ] API endpoint for analytics data
- [ ] Compatible with BI tools
- [ ] Custom date range support

---

## Technical Implementation

### Files to Create/Modify

1. `src/core/analytics.py` - New analytics module
2. `src/core/cost.py` - Extend with analytics tracking
3. `src/cli/commands.py` - Add `orchestrator analytics` command
4. `docs/analytics.md` - Analytics documentation

### Implementation Plan

```python
# src/core/analytics.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

@dataclass
class TierAnalytics:
    """Analytics for a single tier."""
    tier: str
    total_attempts: int
    successful_attempts: int
    failed_attempts: int
    total_cost: Decimal
    total_tokens: int
    avg_success_rate: float = 0.0
    avg_cost_per_success: Decimal = Decimal("0.0")
    
    def update(self, success: bool, cost: Decimal, tokens: int):
        """Update analytics with new data."""
        self.total_attempts += 1
        self.total_cost += cost
        self.total_tokens += tokens
        
        if success:
            self.successful_attempts += 1
        else:
            self.failed_attempts += 1
        
        self.avg_success_rate = (
            self.successful_attempts / self.total_attempts * 100
            if self.total_attempts > 0 else 0
        )
        
        self.avg_cost_per_success = (
            self.total_cost / self.successful_attempts
            if self.successful_attempts > 0 else Decimal("0")
        )

@dataclass
class AnalyticsSummary:
    """Overall analytics summary."""
    generated_at: str
    total_tasks: int
    overall_success_rate: float
    total_cost: Decimal
    avg_cost_per_task: Decimal
    
    # Tier analytics
    tier_analytics: dict[str, TierAnalytics] = field(default_factory=dict)
    
    # Provider analytics
    provider_analytics: dict[str, dict] = field(default_factory=dict)
    
    # Recommendations
    recommendations: list[str] = field(default_factory=list)
    
    def add_tier_analytics(self, tier: str, analytics: TierAnalytics):
        """Add tier analytics."""
        self.tier_analytics[tier] = analytics
    
    def generate_recommendations(self):
        """Generate actionable recommendations."""
        recommendations = []
        
        # Detect over-provisioning
        for tier, analytics in self.tier_analytics.items():
            if tier != "L0" and analytics.avg_success_rate > 95:
                recommendations.append(
                    f"{tier} has {analytics.avg_success_rate:.1f}% success rate. "
                    f"Consider starting at {self._get_lower_tier(tier)} to save costs."
                )
        
        # Detect under-provisioning
        for tier, analytics in self.tier_analytics.items():
            if tier != "L3" and analytics.avg_success_rate < 70:
                recommendations.append(
                    f"{tier} has {analytics.avg_success_rate:.1f}% success rate. "
                    f"Consider starting at {self._get_higher_tier(tier)} to improve success."
                )
        
        # Cost optimization
        if self.tier_analytics.get("L0"):
            l0_analytics = self.tier_analytics["L0"]
            if l0_analytics.avg_success_rate > 85:
                recommendations.append(
                    f"L0 has {l0_analytics.avg_success_rate:.1f}% success rate. "
                    f"Most tasks complete at L0, saving {self._calculate_l0_savings():.2f}"
                )
        
        self.recommendations = recommendations
    
    def _get_lower_tier(self, tier: str) -> str:
        """Get lower tier name."""
        tier_map = {"L1-Coder": "L0-Coder", "L2-Coder": "L1-Coder", 
                   "L3-Coder": "L2-Coder"}
        return tier_map.get(tier, "L0-Coder")
    
    def _get_higher_tier(self, tier: str) -> str:
        """Get higher tier name."""
        tier_map = {"L0-Coder": "L1-Coder", "L1-Coder": "L2-Coder",
                   "L2-Coder": "L3-Coder"}
        return tier_map.get(tier, "L3-Coder")
    
    def _calculate_l0_savings(self) -> float:
        """Calculate savings from L0 usage."""
        if not self.tier_analytics.get("L0"):
            return 0.0
        
        l0_cost = self.tier_analytics["L0"].total_cost
        l1_cost = self.tier_analytics.get("L1-Coder", 
                            TierAnalytics("L1-Coder", 0, 0, 0, Decimal("0"), 0)).total_cost
        l3_cost = Decimal("0.12")  # GPT-4o cost
        
        # If all tasks used L3, cost would be:
        all_l3_cost = Decimal(str(self.total_tasks * 0.12))
        
        return float(all_l3_cost - self.total_cost)
```

### Integration with CostTracker

```python
# src/core/cost.py

from src.core.analytics import TierAnalytics, AnalyticsSummary

class CostTracker:
    def __init__(self, budget: Budget | None = None):
        # ... existing code ...
        self.tier_analytics: dict[str, TierAnalytics] = {}
    
    def record_tier_success(
        self, 
        tier: str, 
        success: bool, 
        cost: Decimal, 
        tokens: int
    ):
        """Record tier performance for analytics."""
        if tier not in self.tier_analytics:
            self.tier_analytics[tier] = TierAnalytics(
                tier=tier,
                total_attempts=0,
                successful_attempts=0,
                failed_attempts=0,
                total_cost=Decimal("0.0"),
                total_tokens=0
            )
        
        self.tier_analytics[tier].update(success, cost, tokens)
    
    def get_analytics_summary(self) -> AnalyticsSummary:
        """Get comprehensive analytics summary."""
        total_cost = Decimal("0.0")
        total_tokens = 0
        successful_tasks = 0
        
        for analytics in self.tier_analytics.values():
            total_cost += analytics.total_cost
            total_tokens += analytics.total_tokens
            successful_tasks += analytics.successful_attempts
        
        total_tasks = sum(
            analytics.total_attempts 
            for analytics in self.tier_analytics.values()
        )
        
        summary = AnalyticsSummary(
            generated_at=datetime.now(UTC).isoformat(),
            total_tasks=total_tasks,
            overall_success_rate=successful_tasks / total_tasks * 100 if total_tasks > 0 else 0,
            total_cost=total_cost,
            avg_cost_per_task=total_cost / total_tasks if total_tasks > 0 else Decimal("0"),
            tier_analytics=self.tier_analytics.copy()
        )
        
        summary.generate_recommendations()
        
        return summary
```

### CLI Analytics Command

```python
# src/cli/commands.py

def cmd_analytics(days: int | None = None) -> int:
    """Display advanced analytics."""
    from src.core.config import config_to_budget, load_config
    
    config = load_config()
    budget = config_to_budget(config)
    tracker = CostTracker(budget=budget)
    
    summary = tracker.get_analytics_summary()
    
    print("=" * 70)
    print("  Advanced Analytics Summary")
    print("=" * 70)
    print()
    print(f"Generated: {summary.generated_at}")
    print(f"Total Tasks: {summary.total_tasks}")
    print(f"Overall Success Rate: {summary.overall_success_rate:.1f}%")
    print(f"Total Cost: ${float(summary.total_cost):.4f}")
    print(f"Avg Cost per Task: ${float(summary.avg_cost_per_task):.4f}")
    print()
    print("Tier Performance:")
    print("-" * 70)
    
    for tier, analytics in sorted(summary.tier_analytics.items()):
        status = "✓" if analytics.avg_success_rate > 90 else "⚠"
        print(f"{status} {tier:15} | Attempts: {analytics.total_attempts:4} | "
              f"Success: {analytics.avg_success_rate:5.1f}% | "
              f"Cost: ${float(analytics.total_cost):.4f} | "
              f"Avg: ${float(analytics.avg_cost_per_success):.4f}")
    
    print()
    print("Recommendations:")
    print("-" * 70)
    if summary.recommendations:
        for i, rec in enumerate(summary.recommendations, 1):
            print(f"{i}. {rec}")
    else:
        print("No recommendations at this time. Keep running tasks to collect data.")
    
    print()
    print("=" * 70)
    print("Export: orchestrator analytics --export json/csv")
    print()
    
    return 0
```

---

## Testing Requirements

### Unit Tests (test_analytics.py)

1. `test_tier_analytics_update` - Tier analytics updates correctly
2. `test_analytics_summary_calculation` - Summary calculations accurate
3. `test_recommendations_generation` - Recommendations generated correctly
4. `test_over_provisioning_detection` - Over-provisioning detected
5. `test_under_provisioning_detection` - Under-provisioning detected
6. `test_l0_savings_calculation` - Savings calculation accurate

### Integration Tests

1. Full workflow with analytics tracking
2. Real task execution updates analytics
3. Recommendations actionable and helpful
4. Export to JSON/CSV works

---

## Out of Scope

- Real-time dashboards (Phase 3)
- ML-based predictions (Phase 4)
- Custom report templates
- Automated optimization (recommendations only)
- Team-level analytics

---

## Dependencies

- P2-1 through P2-4 complete (data sources)
- Core cost tracking infrastructure

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Analytics Calculation** | <100ms |
| **Data Accuracy** | 100% |
| **Recommendations** | Actionable and clear |
| **Export Time** | <1s for 1000 tasks |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Recommendations tested with real data
- [ ] Documentation updated
- [ ] Example analytics output included
- [ ] Export formats verified

---

## Success Metrics

- **Accuracy**: 100% analytics calculation
- **Actionability**: 80%+ recommendations implemented by users
- **Adoption**: 5+ users using analytics features
- **Value**: Clear cost savings from recommendations

---

*Draft: April 26, 2026*
