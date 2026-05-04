# Story P1-3: Auto-Escalation Logic

**Priority**: P0 (Critical - Core Value Proposition)  
**Estimate**: 5 days  
**Phase**: Week 2

---

## User Story

As a developer  
I want the system to automatically escalate from cheap to expensive models when a task fails  
So that I get reliable results without manual configuration or wasted spending

---

## Acceptance Criteria

### AC1: Tier Hierarchy Definition
- [ ] Clear cost hierarchy defined: L0 (cheapest) → L1 → L2 → L3 (most expensive)
- [ ] Each tier maps to a specific model:
  - L0-Coder: `qwen/qwen3-coder-30b` (LM Studio, free/local)
  - L1-Coder: `x-ai/grok-4.1-fast` (OpenRouter, cheap cloud)
  - L2-Coder: `minimax/minimax-m2.7` (OpenRouter, mid-tier)
  - L3-Coder: `anthropic/claude-sonnet-4.6` (OpenRouter, premium)
- [ ] Model costs documented in `CostTracker.MODEL_COSTS`

### AC2: Escalation Trigger Conditions
- [ ] Escalate on LLM response failure (exception raised)
- [ ] Escalate on tool execution failure (file_write failed)
- [ ] Escalate on timeout (task exceeds max duration)
- [ ] Do NOT escalate on budget exceeded (raise error immediately)
- [ ] Track escalation reasons in execution log

### AC3: Retry with Simplification First
- [ ] Before escalating, retry same tier with simplified context
- [ ] Simplification reduces context to 70%, then 40% on second retry
- [ ] Simplification preserves instruction, truncates from end
- [ ] Maximum 3 retries per tier (original + 2 simplifications)
- [ ] Record `context_simplified: true` in result when applicable

### AC4: Escalation Flow
- [ ] Start with L0-Coder (or L0-Planner for complex tasks)
- [ ] On failure after 3 retries, escalate to next tier
- [ ] Each new tier starts fresh (no simplification needed)
- [ ] Stop escalation when task succeeds
- [ ] Stop escalation at L3-Coder (max tier)
- [ ] Log escalation decision with reason

### AC5: Result Aggregation
- [ ] Return the SUCCESSFUL result (not the final failed attempt)
- [ ] Include all tier attempts in `execution_history`
- [ ] Total cost = sum of ALL attempts (including failed ones)
- [ ] Return `tier_used`: which tier ultimately succeeded

### AC6: Execution Logging
- [ ] Log each attempt: tier, success/failure, reason, duration
- [ ] Log escalation decisions: from_tier → to_tier, reason
- [ ] Log simplified contexts: multiplier used, lines reduced
- [ ] Save execution log to `docs/workflow/escalations/`

---

## Technical Implementation

### Files to Modify
1. `src/core/orchestrator.py` - Add `execute_task_auto()` with escalation
2. `src/core/cost.py` - Add escalation tracking to `CostEntry`
3. Create `src/core/tier_manager.py` - Tier configuration and hierarchy

### Tier Manager Implementation

```python
# src/core/tier_manager.py

from dataclasses import dataclass
from enum import Enum
from typing import list

class TierLevel(Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"

@dataclass
class Tier:
    """Configuration for a single tier."""
    level: TierLevel
    name: str  # e.g., "L0-Coder"
    model: str
    base_url: str
    api_key_env: str | None
    temperature: float
    cost_per_1k_tokens: dict  # {"prompt": Decimal, "completion": Decimal}
    supports_tools: bool

class TierManager:
    """Manages tier hierarchy and escalation logic."""
    
    # Predefined tier hierarchy
    TIER_ORDER = [
        Tier(
            level=TierLevel.L0,
            name="L0-Coder",
            model="qwen/qwen3-coder-30b",
            base_url="http://192.168.101.21:1234/v1",  # LM Studio
            api_key_env=None,  # Free/local
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0"), "completion": Decimal("0.0")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L1,
            name="L1-Coder",
            model="x-ai/grok-4.1-fast",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.002"), "completion": Decimal("0.006")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L2,
            name="L2-Coder",
            model="minimax/minimax-m2.7",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0002"), "completion": Decimal("0.0006")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L3,
            name="L3-Coder",
            model="anthropic/claude-sonnet-4.6",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.003"), "completion": Decimal("0.015")},
            supports_tools=True
        ),
    ]
    
    @classmethod
    def get_tier(cls, level: TierLevel) -> Tier:
        for tier in cls.TIER_ORDER:
            if tier.level == level:
                return tier
        raise ValueError(f"Unknown tier level: {level}")
    
    @classmethod
    def get_next_tier(cls, current_tier: Tier) -> Tier | None:
        """Get next more expensive tier, or None if already at L3."""
        current_index = cls.TIER_ORDER.index(current_tier)
        if current_index < len(cls.TIER_ORDER) - 1:
            return cls.TIER_ORDER[current_index + 1]
        return None
    
    @classmethod
    def get_all_tiers(cls) -> list[Tier]:
        return cls.TIER_ORDER.copy()
```

### Auto-Escalation in Orchestrator

```python
# src/core/orchestrator.py (new method)

from src.core.tier_manager import TierManager, TierLevel

class LLMOrchestrator:
    def execute_task_auto(
        self,
        task_id: str,
        context: dict,
        max_retries_per_tier: int = 3,
    ) -> dict:
        """
        Execute task with automatic tier escalation.
        
        Flow:
        1. Start at L0-Coder
        2. Retry up to max_retries_per_tier times with context simplification
        3. If all retries fail, escalate to next tier
        4. Stop when task succeeds or L3 reached
        """
        execution_history = []
        current_tier = TierManager.get_tier(TierLevel.L0)
        
        while current_tier:
            tier_attempts = 0
            last_error = None
            
            while tier_attempts < max_retries_per_tier:
                # Reserve budget
                reservation = self.cost_tracker.reserve_budget(
                    scope=task_id,
                    estimated_cost=self._estimate_tier_cost(current_tier)
                )
                
                try:
                    # Simplify context if not first attempt
                    prompt_multiplier = 1.0
                    if tier_attempts > 0:
                        # 1.0 → 0.7 → 0.4
                        prompt_multiplier = [1.0, 0.7, 0.4][tier_attempts - 1]
                    
                    result = self.execute_task_with_context_simplification(
                        task_id=task_id,
                        tier=current_tier.name,
                        context=context,
                        context_multiplier=prompt_multiplier,
                        timeout_seconds=300
                    )
                    
                    tier_attempts += 1
                    
                    if result["success"]:
                        # Success! Finalize cost and return
                        actual_cost = self.cost_tracker.finalize_spending(
                            reservation.id,
                            self.cost_tracker.calculate_cost(
                                current_tier.model,
                                result["tokens"]
                            )
                        )
                        
                        return {
                            "success": True,
                            "output": result["output"],
                            "tier_used": current_tier.name,
                            "attempts": tier_attempts,
                            "execution_history": execution_history,
                            "cost_usd": float(actual_cost),
                        }
                    else:
                        # Failure, release reservation
                        self.cost_tracker.release_reservation(reservation.id)
                        last_error = result.get("error", "Unknown error")
                        execution_history.append({
                            "tier": current_tier.name,
                            "attempt": tier_attempts,
                            "success": False,
                            "error": last_error,
                            "reason": "execution_failed"
                        })
                        
                except BudgetExceededError:
                    raise
                except Exception as e:
                    last_error = str(e)
                    self.cost_tracker.release_reservation(reservation.id)
                    execution_history.append({
                        "tier": current_tier.name,
                        "attempt": tier_attempts,
                        "success": False,
                        "error": str(e),
                        "reason": "exception"
                    })
            
            # All retries at this tier failed - escalate
            if current_tier.level == TierLevel.L3:
                # Already at max tier, return failure
                return {
                    "success": False,
                    "output": "",
                    "tier_used": current_tier.name,
                    "attempts": sum(e["attempt"] for e in execution_history),
                    "execution_history": execution_history,
                    "error": f"All tiers failed. Last error: {last_error}",
                    "cost_usd": float(self.cost_tracker.get_daily_total())
                }
            
            # Escalate to next tier
            current_tier = TierManager.get_next_tier(current_tier)
            execution_history.append({
                "tier": current_tier.name if current_tier else None,
                "from_tier": execution_history[-1]["tier"] if execution_history else None,
                "reason": "tier_exhausted"
            })
        
        # Should never reach here, but handle gracefully
        return {
            "success": False,
            "output": "",
            "error": "Unexpected escalation loop termination"
        }
```

---

## Testing Requirements

### Unit Tests (test_auto_escalation.py)
1. `test_escalates_on_l0_failure` - L0 fails, escalates to L1
2. `test_succeeds_at_l1` - L1 succeeds, returns L1 result
3. `test_context_simplification` - Tries 3 retries with 1.0 → 0.7 → 0.4
4. `test_escapes_at_l3` - Returns failure when L3 also fails
5. `test_budget_prevents_escalation` - Budget exceeded stops escalation
6. `test_execution_history` - All attempts logged correctly
7. `test_cost_accumulation` - Cost includes all failed attempts

### Integration Tests
1. Real scenario: L0 fails, L1 succeeds
2. Real scenario: All tiers fail
3. Real scenario: L0 succeeds immediately
4. Verify cost tracking across multiple escalations

---

## Performance Considerations

- Each escalation adds ~1-5 seconds of latency
- Cache model configurations to avoid repeated lookups
- Log escalation decisions with timing for optimization

---

## Out of Scope
- ML-based tier prediction (Phase 4)
- User-configurable tier ordering (Phase 2)
- Parallel tier execution (try multiple tiers simultaneously)
- Early termination based on confidence scoring

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Escalation logic verified with real LLM calls
- [ ] Documentation updated
- [ ] Code reviewed and approved

---

## Dependencies
- Requires `src/core/tier_manager.py` to be implemented
- Requires `src/core/cost.py` `reserve_budget()` and `finalize_spending()`
- Requires `src/core/orchestrator.py` `execute_task()` to work

---

## Risk Mitigation

**Risk**: Escalation adds too much latency  
**Mitigation**: Add timeout per tier, log timing, optimize context simplification

**Risk**: Context simplification breaks some tasks  
**Mitigation**: Make simplification configurable, allow user to disable

**Risk**: Cost tracking inflated by failed attempts  
**Mitigation**: Document that cost includes all attempts, users can set task limits
