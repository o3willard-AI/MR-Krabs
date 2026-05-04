# Story P1-5: Budget Warning Alerts

**Priority**: P2 (Medium)  
**Estimate**: 1 day  
**Phase**: Week 3

---

## User Story

As a developer  
I want to receive warnings when I've used 80% of my daily budget  
So that I can monitor spending and avoid unexpected budget exhaustion

---

## Acceptance Criteria

### AC1: Warning Threshold
- [ ] Default warning threshold: 80% of daily budget (`budget.warning_threshold = 0.8`)
- [ ] Warning triggered when `daily_total >= daily_limit * warning_threshold`
- [ ] Warning printed to console immediately (no delay)

### AC2: Warning Message Format
- [ ] Clear message showing: current cost, budget limit, percentage used
- [ ] Example: "Budget warning: $8.00 / $10.00 (80.0%)"
- [ ] Green color when approaching warning, yellow/orange at warning
- [ ] Includes timestamp in log output

### AC3: Multiple Warnings
- [ ] Warning shown only once per day (not on every cost entry)
- [ ] Reset warning flag when new day starts (midnight UTC)
- [ ] No warning spam if multiple costs push past threshold

### AC4: Emergency Cap Warning
- [ ] Separate warning at emergency cap level (daily + emergency_cap_usd)
- [ ] Emergency warning message: "EMERGENCY: Budget exceeded $5.00 cap! ($15.00 / $10.00 + $5.00)"
- [ ] Emergency warning does NOT block execution (fail_open_with_alert)
- [ ] Logs emergency warning to execution history

### AC5: Programmatic Access
- [ ] `CostTracker.is_warning(current)` method available
- [ ] `CostTracker.is_emergency_exceeded(current)` method available
- [ ] These methods can be called externally if needed

---

## Technical Implementation

### Files to Modify
1. `src/core/cost.py` - Add warning tracking

### Implementation Details

```python
# src/core/cost.py

import threading
from datetime import UTC, datetime

class CostTracker:
    def __init__(self, budget: Budget | None = None):
        self.budget = budget or Budget()
        self.entries: list[CostEntry] = []
        self.daily_total = Decimal("0.00")
        self.reserved_total = Decimal("0.00")
        self.task_totals: dict[str, Decimal] = {}
        self.tier_totals: dict[str, Decimal] = {}
        self._reservations: dict[str, Reservation] = {}
        self._lock = threading.Lock()
        self._emergency_calls = 0
        
        # Warning tracking
        self._warning_shown_today = False
        self._emergency_shown_today = False
        self._current_date = datetime.now(UTC).date()
    
    def _check_and_reset_daily_flags(self):
        """Reset warning flags if new day."""
        today = datetime.now(UTC).date()
        if today != self._current_date:
            self._warning_shown_today = False
            self._emergency_shown_today = False
            self._current_date = today
    
    def _emit_warning(self, level: str = "warning"):
        """Emit budget warning if not already shown today."""
        self._check_and_reset_daily_flags()
        
        if level == "warning" and self._warning_shown_today:
            return
        
        if level == "emergency" and self._emergency_shown_today:
            return
        
        threshold = self.budget.daily_limit_usd * self.budget.warning_threshold
        
        if level == "warning":
            if self.daily_total >= threshold and not self._warning_shown_today:
                self._warning_shown_today = True
                msg = f"[BUDGET WARNING] ${float(self.daily_total):.4f} / ${float(self.budget.daily_limit_usd):.2f} ({float(self.daily_total / self.budget.daily_limit_usd * 100):.1f}%)"
                print(f"\n{msg}\n")
        
        elif level == "emergency":
            emergency_threshold = self.budget.daily_limit_usd + self.budget.emergency_cap_usd
            if self.daily_total >= emergency_threshold and not self._emergency_shown_today:
                self._emergency_shown_today = True
                msg = f"\n*** EMERGENCY BUDGET ALERT *** ${float(self.daily_total):.4f} / ${float(emergency_threshold):.2f} ***\n"
                print(msg)
    
    def finalize_spending(self, reservation_id: str, actual_cost: Decimal) -> CostEntry:
        """Finalize a reservation with the actual cost."""
        with self._lock:
            # ... existing logic ...
            
            if self.budget.is_warning(self.daily_total):
                self._emit_warning("warning")
            
            if self.budget.is_emergency_exceeded(self.daily_total):
                self._emit_warning("emergency")
            
            return entry
```

---

## Testing Requirements

### Unit Tests (test_cost_warnings.py)
1. `test_warning_at_80_percent` - Warning triggered at 80%
2. `test_no_duplicate_warning` - Warning shown only once per day
3. `test_warning_resets_midnight` - Flag resets at UTC midnight
4. `test_emergency_warning_separate` - Emergency warning distinct from regular warning
5. `test_warning_does_not_block` - Execution continues after warning

---

## Out of Scope
- Email/SMS alerts (Phase 3)
- Configurable warning thresholds per project (Phase 2)
- Warning history logging to file

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass
- [ ] Warning appears at correct threshold
- [ ] No spamming of warnings
