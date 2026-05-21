# TEST-07a: Ring 1 — Leaf Method Unit Tests

**Phase:** Tech Debt Cleanup — Item 7 (Orchestrator Unit Tests)
**Priority:** P0 (blocking architecture validation)
**Estimated effort:** 60m
**Dependencies:** None (tests the existing orchestrator code)

## Goal

Write unit tests for every **pure leaf method** in `LLMOrchestrator` that currently has zero coverage. These methods have no HTTP calls and no side effects beyond filesystem/env reads — they are testable with simple mocks.

## File to create

`tests/unit/test_orchestrator_leaf.py`

## Test class: `TestOrchestratorLeafMethods`

Use `unittest.TestCase` style (matches existing test_judge_escalation.py pattern). Use `setUp` to create a fresh `LLMOrchestrator()` instance with `project_root` pointing to a `tempfile.TemporaryDirectory`.

### Tests to write

#### 1. `test_get_api_key_env_var_set`
- Set `os.environ["OPENROUTER_API_KEY"] = "sk-test-123"`
- Call `self.orchestrator.get_api_key("L0-Coder")`
- Assert returns `"sk-test-123"`
- Cleanup env var in teardown

#### 2. `test_get_api_key_env_var_not_set`
- Ensure `OPENROUTER_API_KEY` is not in environ
- Call `self.orchestrator.get_api_key("L0-Coder")`
- Assert returns `None`

#### 3. `test_get_api_key_unknown_tier`
- Call `self.orchestrator.get_api_key("BOGUS_TIER")`
- Assert returns `None` (no crash)

#### 4. `test_simplify_context_no_truncation`
- Input: a 50-line prompt, multiplier=1.0
- Assert output equals input (pass-through)

#### 5. `test_simplify_context_truncation`
- Input: a 100-line prompt where each line is `f"line {i}"`, multiplier=0.5
- Assert output has fewer lines than input
- Assert output contains a truncation message (string "[Context truncated")
- Assert first 10 instruction lines are preserved (they contain "line 0" through "line 9")

#### 6. `test_simplify_context_short_prompt`
- Input: a 5-line prompt, multiplier=0.3
- Assert output equals input (short prompts pass through untouched)

#### 7. `test_truncate_file_small_file`
- Create a temp file with 20 lines of content
- Call `truncate_file(path, target_ratio=0.5)`
- Assert returns full content (files ≤50 lines pass through)

#### 8. `test_truncate_file_non_code_preserves_lines`
- Create a `.txt` file with 200 lines of content
- Call `truncate_file(path, target_ratio=0.3)`
- Assert result has roughly 60 lines
- Assert result contains truncation message

#### 9. `test_truncate_file_python_preserves_signatures`
- Create a `.py` file with 200 lines containing imports, `def` statements, and body lines
- Call `truncate_file(path, target_ratio=0.5)`
- Assert all `def` and `class` signatures appear in output
- Assert `import` statements appear in output
- Assert truncation message present

#### 10. `test_get_agent_system_prompt_template_exists`
- Create `docs/workflow/templates/agent-system-prompt.md` inside the temp project root with content "You are an expert developer. Use tools."
- Re-create orchestrator with that project root
- Call `_get_agent_system_prompt()`
- Assert returns "You are an expert developer. Use tools."

#### 11. `test_get_agent_system_prompt_fallback`
- Ensure no `agent-system-prompt.md` file exists in the temp tree
- Call `_get_agent_system_prompt()`
- Assert returns a string containing "file_read" and "file_write" (the fallback prompt includes tool names)

#### 12. `test_build_user_prompt_placeholder_replacement`
- Context: `{"task_spec": "Write a fib function", "existing_context": "def fib(n): pass"}`
- Template: a string containing `{INSERT: Full task specification from Mid-Tier Planner}` and `{INSERT: Relevant existing files, interfaces, patterns}`
- Call `_build_user_prompt("task-1", "L0-Coder", context, template)`
- Assert `"Write a fib function"` appears in output
- Assert `"def fib(n): pass"` appears in output
- Assert `"## Current Task: task-1"` appears in output

#### 13. `test_build_user_prompt_extra_context_keys`
- Context: `{"task_spec": "test", "extra_field": "extra_value"}`
- Template: contains `{INSERT: Full task specification...}`
- Call `_build_user_prompt("task-1", "L0-Coder", context, template)`
- Assert `"**extra_field:** extra_value"` appears in output

#### 14. `test_build_system_prompt_extracts_role`
- Template: `"# ROLE: Expert Coder\n\nYou write code.\n\n## Tools\n\nfile_read, file_write\n"`
- Call `_build_system_prompt("L0-Coder", template)`
- Assert `"# ROLE: Expert Coder"` in output
- Assert `"## Tools"` NOT in output (stops at `##` headers)
- Assert `"file_read"` NOT in output

### Verification
```bash
cd ~/workspace/MR-Krabs && python -m pytest tests/unit/test_orchestrator_leaf.py -v
```
All 14 tests must pass. No regressions on existing suite.
