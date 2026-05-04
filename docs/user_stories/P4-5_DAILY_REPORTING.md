# P4-5: Daily Cost Reporting

## Overview
Implement comprehensive daily cost reporting with summaries, trends, and actionable insights. Provide users with clear visibility into their AI spending patterns.

## Background
Currently, users can export cost data in JSON/CSV format, but don't have:
- Daily summaries with key metrics
- Trend analysis (week-over-week, month-over-month)
- Cost breakdown by tier/provider/task
- Cost optimization recommendations
- Budget projection to end-of-month

## User Story
**As a** cost-conscious user  
**I want** daily cost reports with actionable insights  
**So that** I can understand my spending patterns and optimize costs

## Acceptance Criteria

### AC1: Daily Summary Generation
- [ ] Automatic daily summary at UTC midnight
- [ ] Summary includes:
  - Total cost for the day
  - Task count by tier (L0, L1, L2, L3)
  - Cost per tier
  - Most expensive tasks
  - Tier efficiency scores
  - Budget remaining
- [ ] Summary stored in cost database

### AC2: Report Format Options
- [ ] **Console**: Quick summary printed on `orchestrator stats`
- [ ] **JSON**: Structured data for programmatic access
- [ ] **Markdown**: Human-readable for sharing
- [ ] **Email**: Optional daily email report (configurable)

### AC3: Tier Efficiency Analysis
- [ ] Calculate tier efficiency for each tier:
  - Formula: Successes / Total attempts
  - Cost per successful task
- [ ] Identify over-provisioned tiers (high success rate on expensive tier)
- [ ] Identify under-provisioned tiers (low success rate on cheap tier)
- [ ] Provide recommendations for tier optimization

### AC4: Cost Breakdown Views
- [ ] By tier: Cost distribution across L0-L3
- [ ] By provider: Cost distribution across OpenRouter, LM Studio, etc.
- [ ] By task type: Cost distribution by task complexity
- [ ] By hour: Cost patterns throughout the day
- [ ] Interactive breakdown in JSON output

### AC5: Trend Analysis
- [ ] Day-over-day cost comparison
- [ ] Week-over-week cost comparison
- [ ] Projected end-of-month cost (based on current rate)
- [ ] Alert if projected cost > budget

### AC6: Optimization Recommendations
- [ ] "Consider using L0 for 30% of simple tasks"
- [ ] "Your L2 success rate is 95%, consider L1"
- [ ] "Average cost per task: $0.15 (15% above target)"
- [ ] "Budget exhaustion risk: High (at 90% with 3 days remaining)"
- [ ] Recommendations logged with `orchestrator explain`

### AC7: Historical Access
- [ ] Store daily summaries for 30 days minimum
- [ ] `orchestrator stats --history` shows historical summaries
- [ ] `orchestrator stats --compare <date>` compares two dates

## Implementation Plan

### Phase 1: Summary Generation (1-2 days)
1. Add daily summary storage to CostTracker
2. Generate summary at task completion
3. Implement console summary display

### Phase 2: Report Formats (1 day)
1. JSON format implementation
2. Markdown format implementation
3. Export functionality

### Phase 3: Analysis & Trends (1-2 days)
1. Tier efficiency calculation
2. Cost breakdown analysis
3. Trend analysis implementation
4. Optimization recommendation engine

### Phase 4: Testing & Documentation (1 day)
1. Unit tests for summary generation
2. Integration tests
3. Documentation updates

## Testing Requirements

### Unit Tests
- [ ] `test_daily_summary_generation`
- [ ] `test_tier_efficiency_calculation`
- [ ] `test_cost_breakdown_generation`
- [ ] `test_trend_analysis`
- [ ] `test_optimization_recommendations`
- [ ] `test_summary_export_formats`

### Integration Tests
- [ ] End-to-end: Daily usage → summary generated → report created
- [ ] Historical access and comparison

## Report Format Examples

### Console Summary
```
=== Daily Cost Summary ===
Date: 2026-04-29
Total Cost: $8.45
Tasks: 47 (Success: 45, Failed: 2)

Tier Distribution:
  L0 (Cheap):    35 tasks, $0.35 (74.5%)
  L1 (Standard): 10 tasks, $2.50 (29.6%)
  L2 (Smart):    2 tasks, $3.00 (35.5%)
  L3 (Expert):   0 tasks, $0.00 (0.0%)

Budget Status: $1.55 remaining (15%)
Projected Month-End: $25.35 (Warning: Exceeds $10.00 budget)

Efficiency:
  L0: 97% success, $0.01/task
  L1: 90% success, $0.25/task
  L2: 50% success, $1.50/task

Recommendations:
  • Consider L1 for 30% of simple tasks (currently using L2)
  • Budget exhaustion risk: HIGH
```

### JSON Summary
```json
{
  "date": "2026-04-29",
  "summary": {
    "total_cost_usd": 8.45,
    "task_count": 47,
    "success_count": 45,
    "failure_count": 2,
    "success_rate": 0.957,
    "budget_remaining_usd": 1.55,
    "budget_used_percent": 0.85
  },
  "tier_breakdown": {
    "L0": {"tasks": 35, "cost": 0.35, "success_rate": 0.97},
    "L1": {"tasks": 10, "cost": 2.50, "success_rate": 0.90},
    "L2": {"tasks": 2, "cost": 3.00, "success_rate": 0.50},
    "L3": {"tasks": 0, "cost": 0.00, "success_rate": null}
  },
  "recommendations": [
    "Consider L1 for 30% of simple tasks",
    "Budget exhaustion risk: HIGH"
  ]
}
```

## Dependencies
- P4-1: Cost Alert System (for budget status)
- Core: cost.py, metrics.py

## Notes
- Daily summary should be automatic (no user action required)
- Historical data retention policy: 30 days minimum
- Email reports are optional and disabled by default
