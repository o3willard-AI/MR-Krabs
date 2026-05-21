# TEST-07c: Ring 3 — Integration Test Augmentation

**Phase:** Tech Debt Cleanup — Item 7 (Orchestrator Unit Tests)
**Priority:** P1 (nice-to-have, fills integration gaps)
**Estimated effort:** 45m
**Dependencies:** None

## Goal

Add 4 integration tests to the existing `tests/integration/test_judge_escalation_e2e.py` file to fill gaps in the HTTP-mocked full-pipeline coverage. These tests mock `requests.post` (using the existing `_mock_post_for_models` helper) to exercise the full pipeline: LLM call → tool execution → judge evaluation → escalation decision.

## File to modify

`tests/integration/test_judge_escalation_e2e.py`

Add tests to the existing `TestJudgeEscalationE2E` class. Use the existing `setup_method` and `teardown_method` infrastructure — no new fixtures needed.

### Tests to add

#### 1. `test_judge_model_routing_respects_judge_model_param`
- L0-Coder model: `"qwen3-coder-30b"`
- Judge model: `"anthropic/claude-sonnet-4.6"` (the default "Judge" model)
- L0 returns good output, Judge returns acceptance verdict
- Use `patch("requests.post", wraps=...)` to capture all calls
- After `execute_with_judge(task_id="test_routing", tiers=["L0-Coder"])`:
  - Assert `requests.post` was called at least 2 times (one for L0, one for Judge)
  - Extract the model names from the payloads — at least one call had `model` matching `"qwen3-coder-30b"` and at least one had `model` matching `"anthropic/claude-sonnet"` (the Judge model)
  - This verifies the agent and judge use different models

#### 2. `test_tool_executor_invoked_before_judge`
- L0 output contains valid tool syntax: `file_write("test_output.py", "def solve(): return 42")`
- Set up responses so L0 returns this tool-call output, Judge returns acceptance
- After execution, assert result has `"tool_results"` key with non-None value
- Assert `result["tool_results"]["tools_executed"]` > 0
- Assert result has `"success": True`

Implementation note: The `_mock_post_for_models` helper takes `{model_substring: (content, status_code)}`. You'll need the L0 response to include a recognizable tool invocation pattern. The orchestrator's `ToolExecutor.parse_and_execute_tools` handles `file_write("path", "...")` — include that in the mock L0 output.

#### 3. `test_cost_tracker_receives_token_estimates`
- L0 returns a 100-character output, Judge returns acceptance
- Mock `cost_tracker` with `MagicMock(wraps=...)` to track calls
- After execution, assert `cost_tracker.record` was called
- Extract the `TokenCount` from the call args — assert `prompt_tokens > 0` and `completion_tokens > 0`
- (TokenCount is estimated as len(prompt)//4 and len(output)//4 — both should be positive for non-trivial prompts/outputs)

#### 4. `test_notifier_fires_on_escalation_with_correct_urgency`
- Tiers: `["L0-Coder", "L1-Coder"]` with max_retries_per_tier=1
- L0 returns output, Judge rejects, L1 returns output, Judge accepts
- Mock `self.orchestrator.notifier` with `MagicMock()`
- The tier config for "L0-Coder" has `failure_action: "notify_and_escalate"` in tier_config.py — use `patch('src.core.orchestrator.get_tier_failure_action', return_value=FailureAction.NOTIFY_AND_ESCALATE)` to ensure this triggers
- After execution, assert `self.orchestrator.notifier.send` was called
- Assert the `urgency` parameter was `"normal"`

### Verification
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/integration/test_judge_escalation_e2e.py -v
```
All 4 new tests + all existing 500-line tests must pass. No regressions on existing suite.

### Post-completion
After all 3 rings pass, run the full test suite:
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/ -v --tb=short
```
Expected: 849 + 14 + 10 + 4 = **877 pass**, 0 fail.
