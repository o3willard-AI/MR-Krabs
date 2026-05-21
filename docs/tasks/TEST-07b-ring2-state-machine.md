# TEST-07b: Ring 2 — State Machine Path Unit Tests

**Phase:** Tech Debt Cleanup — Item 7 (Orchestrator Unit Tests)
**Priority:** P0 (blocking architecture validation)
**Estimated effort:** 75m
**Dependencies:** None (tests existing code, mocking LLM calls)

## Goal

Write unit tests for every **control-flow branch** in `execute_with_judge()` that currently only has coverage at the integration/e2e level. These tests mock `call_llm_with_retry` and `Judge.evaluate` so they run in milliseconds with no network.

## File to create

`tests/unit/test_orchestrator_state_machine.py`

## Test class: `TestOrchestratorStateMachine`

Use `unittest.TestCase` style (matches existing test_judge_escalation.py pattern). Follow the same mocking patterns used there — mock `cost_tracker`, `circuit_breaker_registry`, `call_llm_with_retry`, and `Judge.evaluate`.

Each test uses `setUp` to create `LLMOrchestrator()`, then replaces `cost_tracker` and `circuit_breaker_registry` with mocks (identical to `_mock_cost_tracker` and `_mock_circuit_breaker` helpers from test_judge_escalation.py — copy those helper methods).

**CRITICAL**: For tests involving `FailureAction`, use `patch('src.core.orchestrator.get_tier_failure_action', return_value=...)` so you control the action without modifying tier config.

For `NOTIFY_AND_WAIT` tests, also patch `src.core.orchestrator.write_pending_file` and `src.core.orchestrator.wait_for_human`.

For `FailNow` tests, use `patch('src.core.orchestrator.get_fail_now')` and `patch('src.core.orchestrator.clear_fail_now')`.
For `FailUp` tests, use `patch('src.core.orchestrator.is_fail_up_active')` and `patch('src.core.orchestrator.clear_fail_up')`.

### Tests to write

#### 1. `test_principal_escalation_when_tiers_exhausted`
- Tiers: `["L0-Coder", "L1-Coder", "Principal"]` — the `Principal` tier config has `role: "principal"` in model_config.py
- Mock `call_llm_with_retry` side_effect: 6 failures (3 L0 + 3 L1, all rejections from Judge)
- Mock `Judge.evaluate` to return 6 rejections
- Assert result has `"success": False`
- Assert result has `"escalated_to_principal": True`
- Assert result has `"tier_used": "Principal"`
- Assert `"escalation_context"` key exists in result with keys `task`, `tiers_attempted`, `retries_per_tier`, `last_feedback`
- Assert `call_llm_with_retry` was called exactly 6 times (never called for Principal tier)

#### 2. `test_principal_escalation_direct`
- Tiers: `["Principal"]` — skip straight to Principal
- Assert result has `"escalated_to_principal": True`
- Assert `call_llm_with_retry` was NEVER called

#### 3. `test_fail_now_preemption_success`
- Tiers: `["L0-Coder", "L1-Coder"]`
- Mock `get_fail_now()` returns `"L1-Coder"` (valid tier)
- Mock `call_llm_with_retry` returns success with output
- Assert result has `"success": True`
- Assert result has `"fail_now": True`
- Assert result has `"tier_used": "L1-Coder"`
- Assert `clear_fail_now` was called
- Assert `Judge.evaluate` was NEVER called (fail_now skips judge)

#### 4. `test_fail_now_falls_through_on_failure`
- Tiers: `["L0-Coder", "L2-Coder"]`
- Mock `get_fail_now()` returns `"L0-Coder"`
- Mock `call_llm_with_retry` returns failure (success=False)
- Mock `Judge.evaluate` returns acceptance for L2-Coder call
- Assert result has `"success": True`
- Assert result has `"tier_used": "L2-Coder"` (fell through to next tier)
- Assert `clear_fail_now` was called

#### 5. `test_fail_up_at_tier_entry_skips_tier`
- Tiers: `["L0-Coder", "L1-Coder"]`
- Mock `is_fail_up_active()` returns True on first call, False after
- Mock `call_llm_with_retry` returns success for L1-Coder
- Mock `Judge.evaluate` returns acceptance for L1-Coder
- Assert result has `"success": True`
- Assert result has `"tier_used": "L1-Coder"` (L0 was skipped)
- Assert `"L0-Coder"` appears in `escalation_path`
- Assert `clear_fail_up` was called

#### 6. `test_fail_up_mid_retry_aborts_tier`
- Tiers: `["L0-Coder", "L1-Coder"]`
- Mock `is_fail_up_active()` returns [False, True, False] (triggers during retry loop of L0, not at tier entry)
- Mock `call_llm_with_retry` side_effect: one successful L0 call, then L1-Coder success
- Mock `Judge.evaluate` returns rejection for L0 call (to trigger retry loop) then acceptance for L1
- Assert result has `"success": True`, `"tier_used": "L1-Coder"`
- Assert `retries_per_tier["L0-Coder"]` equals 1 (aborted mid-retry)
- Assert `call_llm_with_retry.call_count` equals 2 (one L0 call, one L1 call)

#### 7. `test_failure_action_log_only`
- Tiers: `["L0-Coder", "L1-Coder"]` with max_retries_per_tier=1
- Mock `get_tier_failure_action(return_value=FailureAction.LOG_ONLY)`
- Mock `call_llm_with_retry` side_effect: L0 success but rejected, L1 success accepted
- Mock `Judge.evaluate` side_effect: reject, accept
- Assert result has `"success": True`, `"tier_used": "L1-Coder"`
- Assert escalation continues silently after L0 failure (no exception)

#### 8. `test_failure_action_notify_and_escalate`
- Tiers: `["L0-Coder", "L1-Coder"]` with max_retries_per_tier=1
- Mock `get_tier_failure_action(return_value=FailureAction.NOTIFY_AND_ESCALATE)`
- Mock `call_llm_with_retry` side_effect: L0 rejected, L1 accepted
- Mock `Judge.evaluate` side_effect: reject, accept
- Mock `self.orchestrator.notifier.send`
- Assert `self.orchestrator.notifier.send` was called (at least once)
- Assert result has `"success": True`, `"tier_used": "L1-Coder"`

#### 9. `test_failure_action_notify_and_wait_confirmed`
- Tiers: `["L0-Coder", "L1-Coder"]` with max_retries_per_tier=1
- Mock `get_tier_failure_action(return_value=FailureAction.NOTIFY_AND_WAIT)`
- Mock `write_pending_file` (no-op)
- Mock `wait_for_human` returns `(True, "")` — confirmed
- Mock `call_llm_with_retry` side_effect: L0 rejected, L1 rejected, L2 accepted
- Mock `Judge.evaluate` side_effect: reject, reject, accept
- Use tiers: `["L0-Coder", "L1-Coder", "L2-Coder"]`
- Assert `wait_for_human` was called
- Assert `self.orchestrator.notifier.send` was called
- Assert result has `"success": True` (escalation continued after confirmation)

#### 10. `test_failure_action_notify_and_wait_aborted`
- Tiers: `["L0-Coder"]` with max_retries_per_tier=1
- Mock `get_tier_failure_action(return_value=FailureAction.NOTIFY_AND_WAIT)`
- Mock `write_pending_file` (no-op)
- Mock `wait_for_human` returns `(False, "user declined")`
- Mock `call_llm_with_retry` returns L0 success
- Mock `Judge.evaluate` returns rejection
- Assert result has `"success": False`
- Assert result has `"reason": "user declined"`
- Assert result has `"tier_used": None`

### Verification
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/unit/test_orchestrator_state_machine.py -v
```
All 10 tests must pass. No regressions on existing suite.
