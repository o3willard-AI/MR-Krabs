# FIX-08: Per-Tier Failure Actions (Post-Loop Bug)

**Phase:** Tech Debt Cleanup — Follow-up to Item 7
**Priority:** P1 (silent notification drops in multi-tier runs)
**Estimated effort:** 30m
**Discovered by:** Item 7 unit test architecture (Ring 2)
**Commit:** Tests at `09e8c66`

## Bug

The `failure_action` if/elif block in `LLMOrchestrator.execute_with_judge()` runs **after** the `for tier in tiers:` loop exits (line 910), not inside the retry-exhaustion path per tier. This means:

- L0 fails all retries → `failure_action` set to e.g. `NOTIFY_AND_ESCALATE` (line 877)
- Loop continues to L1
- L1 **succeeds** on first try → `return` from line 851
- The `if failure_action == ...` at line 910 **is never reached**
- L0's notification, pending file, and human gate **are silently dropped**

### Concrete scenario

```python
tiers = ["L0-Coder", "L1-Coder"]
# L0: 3 retries, all rejected by Judge
#   → failure_action = NOTIFY_AND_ESCALATE (line 877)
# L1: 1 attempt, accepted by Judge
#   → return at line 851  ← never reaches line 910
# NOTIFIER NEVER FIRES for L0 escalation
```

## Root cause

Lines 910-958 are indented at 8 spaces — same level as `for tier in tiers:` at line 724 — placing the failure_action block **outside** the for loop. It executes once after all tiers are processed, checking only the `failure_action` value from the last iteration. A successful subsequent tier causes an early return that skips it entirely.

## Fix

Move the failure_action if/elif block (lines 910-958) **inside** the tier loop, right after `failure_action = get_tier_failure_action(tier)` at line 877. The nested `build_notification_message` function definition (lines 879-908) stays where it is or gets extracted to a method — the key change is that the action is dispatched immediately per tier, not deferred to post-loop.

### Structure after fix

```python
for tier in tiers:
    # ... retry loop ...
    
    # After retry exhaustion (or fail_up abort)
    if fail_up_aborted:
        escalation_path.append(tier)
        continue
    
    escalation_path.append(tier)
    failure_action = get_tier_failure_action(tier)
    
    # --- Execute failure action NOW, not after loop ---
    if failure_action == FailureAction.LOG_ONLY:
        print(f"Tier {tier} failed (log_only).")
    
    elif failure_action == FailureAction.NOTIFY_AND_ESCALATE:
        print(f"[ESCALATE] Tier {tier} failed. Spend: ...")
        self.notifier.send(
            message=build_notification_message(task_id, tier, ...),
            urgency="normal",
            context={"task_id": task_id, "tier": tier}
        )
    
    elif failure_action == FailureAction.NOTIFY_AND_WAIT:
        from src.core.human_gate import write_pending_file, wait_for_human
        write_pending_file(task_id, {...})
        self.notifier.send(...)
        confirmed, reason = wait_for_human(task_id)
        if not confirmed:
            return {...}  # abort
        # confirmed → continue to next tier
```

## Tests to update

The Ring 2 tests for failure actions (in `tests/unit/test_orchestrator_state_machine.py`) currently work around the bug by using single-tier failure to reach the post-loop block:

- `test_failure_action_notify_and_escalate` — uses ["L0-Coder"] only
- `test_failure_action_notify_and_wait_confirmed` — uses ["L0-Coder"] only
- `test_failure_action_notify_and_wait_aborted` — uses ["L0-Coder"] only

After the fix, these tests should be rewritten for multi-tier escalation:

| Test | Before fix | After fix |
|------|-----------|-----------|
| notify_and_escalate | ["L0"] fails → notifier fires, total failure | ["L0", "L1"] → L0 fails (notifier fires), L1 succeeds |
| notify_and_wait_confirmed | ["L0"] fails → human confirms → total failure | ["L0", "L1"] → L0 fails (human confirms), L1 succeeds |
| notify_and_wait_aborted | ["L0"] fails → human denies → abort | ["L0"] → human denies → abort (unchanged) |

## Verification

```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/unit/test_orchestrator_state_machine.py tests/integration/test_judge_escalation_e2e.py -v
```

All existing tests must pass; updated tests must reflect real multi-tier behavior.
