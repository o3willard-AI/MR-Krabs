# Story P4-5: Daily Cost Reporting

**Priority**: P1 (High)
**Estimate**: 1 day
**Phase**: Week 4

## User Story

As a developer using MR-Krabs
I want daily cost reports with tier efficiency analysis and trend tracking
So that I can understand cost patterns, optimize tier usage, and predict future spending

## Acceptance Criteria

### AC1: Daily Cost Report Generation
- [ ] `DailyCostReport` dataclass exists in `src/reports/daily_report.py`
- [ ] Contains: date, total_cost, task_count, tier_breakdown, model_breakdown
- [ ] `DailyCostReportGenerator` generates reports from cost tracker history
- [ ] Supports filtering by date range and tier

### AC2: Tier Efficiency Analysis
- [ ] `TierEfficiencyAnalysis` dataclass in `src/reports/efficiency.py`
- [ ] Calculates: usage_count, total_cost, avg_cost_per_task, success_rate
- [ ] Efficiency score (0-100) based on cost vs. outcome ratio
- [ ] Identifies overused and underused tiers

### AC3: Cost Breakdown View
- [ ] Cost breakdown by tier (L0, L1, L2, L3)
- [ ] Cost breakdown by model
- [ ] Cost breakdown by time period (hourly buckets)
- [ ] Breakdown includes cost, task count, percentage of total

### AC4: Trend Analysis and Recommendations
- [ ] `TrendAnalysis` dataclass in `src/reports/trend_analysis.py`
- [ ] Tracks 7-day and 30-day cost trends
- [ ] Calculates day-over-day and week-over-week percentage changes
- [ ] Generates cost optimization recommendations based on patterns
- [ ] Alerts for unusual spending spikes (>50% increase)

### AC5: CLI Integration for Reports
- [ ] CLI command `report` to generate daily cost reports
- [ ] `--date` flag for specific date
- [ ] `--format` flag for output format (text, json)
- [ ] `--summary` flag for concise summary only

## Technical Implementation

### Files to Create/Modify

1. **`src/reports/daily_report.py`** (Create)
   - `DailyCostReport` dataclass: date, total_cost, task_count, tier_breakdown, model_breakdown
   - `DailyCostReportGenerator` class with `generate_report()` method
   - Aggregates cost entries by date

2. **`src/reports/efficiency.py`** (Create)
   - `TierEfficiencyAnalysis` dataclass
   - `EfficiencyAnalyzer` class with `analyze_tier_efficiency()` method
   - Efficiency scoring algorithm
   - Tier usage optimization suggestions

3. **`src/reports/trend_analysis.py`** (Create)
   - `TrendAnalysis` dataclass: trends, recommendations, alerts
   - `TrendAnalyzer` class with `analyze_trends()` method
   - Trend calculation (7-day, 30-day moving averages)
   - Recommendation engine based on patterns

4. **`src/reports/__init__.py`** (Create)
   - Export report classes and generators

5. **`src/cli/commands.py`** (Modify)
   - Add `cmd_report()` command for generating reports
   - Integrate with existing CLI structure

6. **`src/core/cost.py`** (Modify)
   - Add methods to support report generation
   - `get_daily_summary()`, `get_tier_breakdown()`, `get_model_breakdown()`

7. **`src/__init__.py`** (Modify)
   - Export report classes for programmatic use

### Testing Requirements

**Unit Tests:**
- `tests/unit/test_daily_report_p4_5.py` - Test `DailyCostReport` and generator
- `tests/unit/test_efficiency_analysis_p4_5.py` - Test tier efficiency analysis
- `tests/unit/test_trend_analysis_p4_5.py` - Test trend calculations
- `tests/unit/test_report_cli_p4_5.py` - Test CLI report commands

**Test Count Target**: ~25-30 tests total

### Report Output Format

**Text Summary (default):**
```
Daily Cost Report - 2026-04-30
================================

Total Spend: $5.42
Tasks: 23

Tier Breakdown:
  L0-Coder: $1.20 (22%, 12 tasks)
  L1-Coder: $2.85 (53%, 8 tasks)
  L2-Coder: $1.37 (25%, 3 tasks)
  L3-Coder: $0.00 (0%, 0 tasks)

Model Breakdown:
  free-tier: $1.20
  economical: $2.85
  balanced: $1.37

Efficiency Score: 87/100
Recommendation: Consider using more L0-Coder for simple tasks
```

**JSON Output:**
```json
{
  "date": "2026-04-30",
  "total_cost": 5.42,
  "task_count": 23,
  "tier_breakdown": {...},
  "model_breakdown": {...},
  "efficiency_score": 87,
  "recommendations": [...]
}
```

## Trend Analysis Examples

**Day-over-Day Change:**
- Today: $5.42
- Yesterday: $4.87
- Change: +11.3% (within normal range)

**Week-over-Week Change:**
- This week (7 days): $32.15
- Last week (7 days): $28.50
- Change: +12.8% (slight increase, monitoring recommended)

**Spending Alert:**
- [ALERT] Today's spend $5.42 is 65% higher than yesterday's $3.25
- Possible causes: longer tasks, more complex prompts, tier changes

## Recommendations Engine

**Based on tier usage:**
- "Your L3-Coder usage is only 2% of total spend. Consider if this tier is needed."
- "70% of tasks used L1-Coder. Consider L0-Coder for simpler tasks to save 40%."

**Based on cost patterns:**
- "Cost increased 50% over past 3 days. Review task complexity."
- "Budget warning threshold reached 3 times this week. Consider reducing task frequency."

**Based on efficiency:**
- "L2-Coder has low success rate (60%). Review error patterns."
- "L0-Coder efficiency score: 95/100. Continue using for simple tasks."

## Notes

- Reports should be backward-compatible with existing cost tracker
- Support both in-memory and persisted cost data
- Report generation should be fast (<1 second for typical usage)
- Consider adding export to CSV/JSON for external analysis
