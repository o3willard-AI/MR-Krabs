# Story P1-2: Integrate CostTracker with Orchestrator

**Priority**: P0 (Critical)  
**Estimate**: 4 days  
**Phase**: Week 1-2

---

## User Story

As a developer  
I want the orchestrator to automatically track costs and enforce budgets during task execution  
So that I never exceed my spending limit and can see the cost breakdown per task

---

## Acceptance Criteria

### AC1: Budget Reservation Pattern
- [ ] `CostTracker.reserve_budget()` is called BEFORE each LLM attempt
- [ ] Reservation fails immediately if budget would be exceeded (check-then-act prevention)
- [ ] Returns unique `reservation_id` for tracking
- [ ] Reserved budget is included in `get_effective_total()`

### AC2: Cost Finalization
- [ ] `CostTracker.finalize_spending()` called AFTER successful LLM call
- [ ] Adjusts for difference between estimated and actual cost
- [ ] Records `CostEntry` with timestamp, tier, model, tokens, cost, duration
- [ ] Updates `daily_total`, `task_totals`, `tier_totals`

### AC3: Cost Release on Failure
- [ ] `CostTracker.release_reservation()` called on LLM failure
- [ ] Reserved budget is freed for retry/escalation
- [ ] No cost entry created for failed attempts

### AC4: Budget Enforcement
- [ ] Per-task limit enforced (default: $1.00/task) via `budget.task_limit_usd`
- [ ] Daily limit enforced (default: $10.00/day) via `budget.daily_limit_usd`
- [ ] Warning threshold at 80% (`budget.warning_threshold`)
- [ ] Emergency cap at `budget.daily_limit_usd + budget.emergency_cap_usd`

### AC5: Integration Points
- [ ] Orchestrator receives `CostTracker` in constructor (dependency injection)
- [ ] Orchestrator calls `reserve_budget()` before executing each tier
- [ ] Orchestrator calls `finalize_spending()` on success
- [ ] Orchestrator calls `release_reservation()` on failure

### AC6: Cost Accuracy
- [ ] Token counting from LLM responses captured accurately
- [ ] Cost calculated using `CostTracker.MODEL_COSTS` pricing table
- [ ] Currency uses `Decimal` for all calculations (no floating point errors)
- [ ] Cost returned to 4 decimal places

---

## Technical Implementation

### Files to Modify
1. `src/core/orchestrator.py` - Add `CostTracker` integration
2. `src/core/cost.py` - Verify `CostEntry` includes all required fields
3. `src/core/exceptions.py` - Add `BudgetExceededError`

### Key Changes to Orchestrator

```python
# src/core/orchestrator.py

from dataclasses import dataclass
from src.core.cost import CostTracker, TokenCount, Budget

@dataclass
class ExecutionContext:
    """Context for orchestrator execution with cost tracking."""
    task_id: str
    cost_tracker: CostTracker
    tier_attempts: list[dict] = field(default_factory=list)

class LLMOrchestrator:
    def __init__(
        self, 
        project_root: str,
        budget: Budget = None,
        cost_tracker: CostTracker = None
    ):
        self.project_root = Path(project_root)
        self.cost_tracker = cost_tracker or CostTracker(budget=budget or Budget())
        # ... existing initialization
        ...
    
    def execute_task_with_cost(
        self,
        task_id: str,
        context: dict,
        tier: str,
        estimated_cost: Decimal = Decimal("0.01"),
    ) -> dict:
        """Execute task with budget reservation."""
        # Reserve budget before attempting
        reservation = self.cost_tracker.reserve_budget(
            scope=task_id,
            estimated_cost=estimated_cost
        )
        
        try:
            result = self.execute_task(task_id, tier, context)
            
            if result["success"]:
                # Calculate actual cost
                tokens = self._count_tokens(result["output"])
                actual_cost = self.cost_tracker.calculate_cost(
                    model=MODELS[tier]["model"],
                    tokens=tokens
                )
                
                # Finalize spending
                self.cost_tracker.finalize_spending(
                    reservation_id=reservation.id,
                    actual_cost=actual_cost
                )
                
                result["cost_usd"] = float(actual_cost)
                return result
            else:
                # Release reservation on failure
                self.cost_tracker.release_reservation(reservation.id)
                result["cost_usd"] = 0.0
                return result
                
        except BudgetExceededError:
            self.cost_tracker.release_reservation(reservation.id)
            raise

    def _count_tokens(self, text: str) -> TokenCount:
        """Estimate token count from text."""
        # TODO: Implement proper token counting or use OpenRouter response
        # For now, rough estimate: 1 token ≈ 4 characters
        tokens = len(text) // 4
        return TokenCount(
            prompt_tokens=tokens // 2,
            completion_tokens=tokens // 2,
            total_tokens=tokens
        )
```

### CostTracker Verification

Verify these methods work correctly:
- `reserve_budget(scope, estimated_cost)` - Returns `Reservation`
- `finalize_spending(reservation_id, actual_cost)` - Returns `CostEntry`
- `release_reservation(reservation_id)` - No return
- `calculate_cost(model, tokens)` - Returns `Decimal`
- `get_summary()` - Returns dict with all totals
- `save_report(filepath)` - Returns path to JSON file

---

## Testing Requirements

### Unit Tests (test_cost_integration.py)
1. `test_reserve_budget_success` - Reservation created correctly
2. `test_reserve_budget_exceeds_daily` - Raises BudgetExceededError
3. `test_reserve_budget_exceeds_task_limit` - Raises BudgetExceededError
4. `test_finalize_spending_under` - Correctly handles actual < estimated
5. `test_finalize_spending_over` - Correctly handles actual > estimated
6. `test_release_reservation` - Budget freed on failure
7. `test_cost_tracking_thread_safety` - Lock prevents race conditions
8. `test_decimal_accuracy` - No floating point errors in currency

### Integration Tests
1. Full execution flow: reserve → execute → finalize
2. Failure flow: reserve → execute(fail) → release
3. Budget exhaustion: multiple tasks hit daily limit
4. Cost summary accuracy: verify totals match entries

### Concurrency Tests
1. Two concurrent tasks, both try to reserve budget
2. Verify only one succeeds (race condition prevention)
3. Verify total never exceeds daily limit

---

## Performance Considerations

- Budget checks must be fast (<1ms)
- Use threading.Lock for atomic operations
- Avoid unnecessary Decimal conversions
- Batch cost entries when saving to disk

---

## Out of Scope
- Multi-currency support (USD only for Phase 1)
- Real-time token counting (estimate from text for now)
- Cost forecasting/prediction
- Multi-user budget sharing

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Concurrency tests pass
- [ ] No floating point currency errors
- [ ] Documentation updated
- [ ] Code reviewed and approved

---

## Dependencies
- Requires `src/core/cost.py` to be complete and tested
- Requires `src/core/exceptions.py` to define `BudgetExceededError`
- Requires `src/core/orchestrator.py` `execute_task()` to work
