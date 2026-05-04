# Story P1-6: Cost Reporting and Export

**Priority**: P2 (Medium)  
**Estimate**: 2 days  
**Phase**: Week 3

---

## User Story

As a developer  
I want to export cost data to JSON/CSV files  
So that I can analyze spending patterns, share reports, or integrate with external tools

---

## Acceptance Criteria

### AC1: JSON Export
- [ ] `CostTracker.save_report(filepath)` exports to JSON
- [ ] Includes summary: daily_total, reserved_total, effective_total, budget_limit, budget_remaining
- [ ] Includes entries array: timestamp, task_id, tier, model, tokens, cost_usd, duration
- [ ] Includes tier_totals and task_totals breakdowns
- [ ] Human-readable formatting (indented JSON)

### AC2: CSV Export
- [ ] `CostTracker.export_csv(filepath)` exports to CSV
- [ ] Headers: timestamp, task_id, tier, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, duration_seconds
- [ ] One row per cost entry
- [ ] Decimal costs converted to float (max 6 decimal places)

### AC3: Automatic Report on Session End
- [ ] When `CostTracker` destructor called, save report automatically
- [ ] Report named: `cost_report_YYYYMMDD.json`
- [ ] Save to current working directory (or configurable location)

### AC4: Cost Summary Report
- [ ] `get_summary()` returns dict with all key metrics
- [ ] Summary includes:
  - Total spent today
  - Budget limit and remaining
  - Budget used percentage
  - Per-tier cost breakdown
  - Per-task cost breakdown
  - Total requests count
  - Active reservations count

### AC5: CLI Integration
- [ ] `orchestrator stats --export json` saves JSON report
- [ ] `orchestrator stats --export csv` saves CSV report
- [ ] `orchestrator stats --export both` saves both formats

---

## Technical Implementation

### Files to Modify
1. `src/core/cost.py` - Add `export_csv()` method
2. `src/cli/commands.py` - Add `--export` flag to `cmd_stats`

### Implementation Details

```python
# src/core/cost.py

import csv
from pathlib import Path

class CostTracker:
    def export_csv(self, filepath: str | None = None) -> Path:
        """Export cost data to CSV file."""
        if not filepath:
            filepath = f"cost_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
        path = Path(filepath)
        
        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'task_id', 'tier', 'model', 
                'prompt_tokens', 'completion_tokens', 'total_tokens',
                'cost_usd', 'duration_seconds'
            ])
            
            for entry in self.entries:
                writer.writerow([
                    entry.timestamp,
                    entry.task_id,
                    entry.tier,
                    entry.model,
                    entry.tokens.prompt_tokens,
                    entry.tokens.completion_tokens,
                    entry.tokens.total_tokens,
                    float(entry.cost_usd),
                    entry.duration_seconds
                ])
        
        return path
    
    def get_summary(self) -> dict:
        """Get cost summary with Decimal values converted to float."""
        effective = self.daily_total + self.reserved_total
        return {
            "daily_total": float(self.daily_total),
            "reserved_total": float(self.reserved_total),
            "effective_total": float(effective),
            "budget_limit": float(self.budget.daily_limit_usd),
            "budget_remaining": float(self.budget.daily_limit_usd - effective),
            "budget_used_percent": float(
                (effective / self.budget.daily_limit_usd * 100)
                if self.budget.daily_limit_usd > 0 else 0
            ),
            "task_totals": {k: float(v) for k, v in self.task_totals.items()},
            "tier_totals": {k: float(v) for k, v in self.tier_totals.items()},
            "total_requests": len(self.entries),
            "active_reservations": len(self._reservations),
        }
```

---

## Testing Requirements

### Unit Tests (test_cost_export.py)
1. `test_save_report_creates_json` - JSON file created with correct structure
2. `test_save_report_includes_entries` - All entries included
3. `test_export_csv_creates_file` - CSV file created with correct headers
4. `test_export_csv_data_accuracy` - CSV data matches entries
5. `test_get_summary_structure` - Returns dict with all expected keys

---

## Out of Scope
- Cloud storage integration (Phase 3)
- Real-time dashboard (Phase 3)
- Email reports (Phase 3)
- Custom report templates

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass
- [ ] JSON and CSV exports verified
- [ ] CLI integration tested
