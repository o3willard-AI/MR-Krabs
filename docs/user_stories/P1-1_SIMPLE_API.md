# Story P1-1: Simple ask() API

**Priority**: P0 (Critical - Blocks all other stories)  
**Estimate**: 3 days  
**Phase**: Week 1

---

## User Story

As a developer  
I want to call a simple `ask()` function with a task description  
So that I can get AI-generated results with automatic cost optimization and zero configuration

---

## Acceptance Criteria

### AC1: Basic API Surface
- [ ] `from cost_orchestrator import ask` works without errors
- [ ] `ask(task: str)` returns a result object/dict with at least:
  - `output`: str - The LLM-generated result
  - `cost`: float - Total cost in USD
  - `success`: bool - Whether the task succeeded
  - `tier_used`: str - Which tier/model was ultimately used
  - `attempts`: int - Number of LLM attempts made
- [ ] Returns result within 30 seconds for simple tasks

### AC2: Zero-Config Defaults
- [ ] Works with only `OPENROUTER_API_KEY` environment variable
- [ ] Falls back to OpenRouter when `OPENROUTER_API_KEY` is set
- [ ] Falls back to LM Studio when `OPENROUTER_API_KEY` is NOT set (with warning)
- [ ] No config file required to function
- [ ] No additional dependencies required

### AC3: Automatic Tier Selection
- [ ] Starts with cheapest capable model (L0-Coder or equivalent)
- [ ] Automatically escalates to more expensive tiers on failure
- [ ] Stops escalation when task succeeds OR max tier reached
- [ ] Returns the best successful result (not the failed attempt)

### AC4: Cost Tracking
- [ ] Tracks cost for each LLM call made during task execution
- [ ] Returns total cumulative cost in result
- [ ] Cost is accurate to 4 decimal places

### AC5: Error Handling
- [ ] Raises `ApiError` when API key is missing/invalid
- [ ] Raises `BudgetExceededError` when cost would exceed daily limit
- [ ] Returns `success: False` with error message when task fails
- [ ] Logs all attempts to stdout/console

---

## Technical Implementation

### Files to Create/Modify
1. `src/__init__.py` - Create new file with `ask()` function
2. `src/core/orchestrator.py` - Add `_auto_select_tier()` helper
3. `src/core/exceptions.py` - Add `ApiError`, `ModelError`

### Implementation Plan
```python
# src/__init__.py
from dataclasses import dataclass
from src.core.orchestrator import LLMOrchestrator
from src.core.cost import CostTracker, Budget
from src.core.exceptions import ApiError, BudgetExceededError

@dataclass
class AskResult:
    output: str
    cost: float
    success: bool
    tier_used: str
    attempts: int
    error: str = None

def ask(task: str, budget: float = 10.0) -> AskResult:
    """
    Simple API for cost-optimized LLM task execution.
    
    Args:
        task: Task description string
        budget: Daily budget in USD (default: 10.0)
    
    Returns:
        AskResult with output, cost, and metadata
    
    Raises:
        ApiError: When API key missing/invalid
        BudgetExceededError: When budget limit reached
    """
    # Validate API key
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise ApiError("OPENROUTER_API_KEY environment variable not set")
    
    # Initialize orchestrator with auto-escalation
    orchestrator = LLMOrchestrator(project_root="...")
    tracker = CostTracker(budget=Budget(daily_limit_usd=budget))
    
    # Try tiers in order from cheap to expensive
    tiers = ["L0-Coder", "L1-Coder", "L2-Coder", "L3-Coder"]
    
    for tier in tiers:
        # Reserve budget before attempt
        reservation = tracker.reserve_budget(task, estimated_cost=Decimal("0.01"))
        
        try:
            result = orchestrator.execute_task(task, tier, {"task": task})
            
            if result["success"]:
                # Finalize spending with actual cost
                actual_cost = tracker.calculate_cost(...)
                tracker.finalize_spending(reservation.id, actual_cost)
                return AskResult(
                    output=result["output"],
                    cost=tracker.get_daily_total(),
                    success=True,
                    tier_used=tier,
                    attempts=result["attempts"]
                )
            else:
                # Release reservation on failure
                tracker.release_reservation(reservation.id)
                
        except BudgetExceededError:
            raise
    
    # All tiers failed
    return AskResult(
        output="",
        cost=tracker.get_daily_total(),
        success=False,
        tier_used="none",
        attempts=sum(r["attempts"] for r in attempts),
        error="All tiers failed"
    )
```

### Dependencies
- Requires `src/core/exceptions.py` to define custom exceptions
- Requires `orchestrator.execute_task()` to work correctly
- Relies on existing provider implementations (OpenRouter, LM Studio)

---

## Testing Requirements

### Unit Tests (test_ask_api.py)
1. `test_ask_basic_success` - Simple task succeeds at L0
2. `test_ask_auto_escalates` - Task escalates when L0 fails
3. `test_ask_budget_enforced` - Respects daily budget limit
4. `test_ask_api_key_missing` - Raises ApiError without key
5. `test_ask_cost_tracking` - Accurate cost calculation
6. `test_ask_timeout` - Handles timeout gracefully

### Integration Tests
1. Real OpenRouter API call with valid key
2. Verify cost is tracked and returned correctly

---

## Out of Scope
- Multi-task batch execution
- Streaming responses
- Custom model selection
- Prompt customization

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage for this module)
- [ ] Integration tests pass
- [ ] Documentation updated (README + API docs)
- [ ] No console errors or warnings
- [ ] Code reviewed and approved
