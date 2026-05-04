# Story P1-7: Per-Task Budget Limits

**Priority**: P2 (Medium)  
**Estimate**: 1 day  
**Phase**: Week 3

---

## User Story

As a developer  
I want to limit cost per individual task  
So that one problematic task doesn't consume the entire daily budget

---

## Acceptance Criteria

### AC1: Per-Task Limit Enforcement
- [ ] `Budget.task_limit_usd` default: $1.00
- [ ] `reserve_budget()` checks if `estimated_cost > task_limit_usd`
- [ ] Raises `BudgetExceededError` with clear message if limit exceeded
- [ ] Error message includes: estimated cost, task limit, suggestion

### AC2: Limit Configuration
- [ ] Configurable per `Budget` instance
- [ ] Can be overridden in `pyproject.toml` under `[budget]`
- [ ] CLI: `orchestrator run --task-budget 0.50` (optional argument)

### AC3: Error Messages
- [ ] Clear error: "Task cost $X.XXXX exceeds per-task limit of $X.XX"
- [ ] Suggests: "Consider breaking task into smaller pieces"
- [ ] Logged to execution history

### AC4: Emergency Exception
- [ ] If `failure_mode == FAIL_CLOSED`, reject immediately
- [ ] If `failure_mode == FAIL_OPEN_WITH_ALERT`, allow with warning
- [ ] Emergency calls tracked separately (`_emergency_calls`)
- [ ] Emergency call limit: `budget.emergency_call_limit` (default: 10)

---

## Technical Implementation

### Files to Modify
1. `src/core/cost.py` - Already implements this in `reserve_budget()`

### Verification Needed
- [ ] Verify `reserve_budget()` checks `estimated_cost > budget.task_limit_usd`
- [ ] Verify error message is clear and actionable
- [ ] Verify emergency call tracking works

---

## Testing Requirements

### Unit Tests (test_task_limits.py)
1. `test_task_limit_enforced` - Task exceeding limit raises error
2. `test_task_limit_configurable` - Custom task limit accepted
3. `test_task_limit_error_message` - Error message is helpful
4. `test_emergency_override` - Emergency calls can exceed limit

---

## Out of Scope
- Per-tier task limits
- Dynamic task limit based on complexity (Phase 4)

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass
- [ ] Error messages tested
