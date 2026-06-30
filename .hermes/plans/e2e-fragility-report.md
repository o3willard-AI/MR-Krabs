# E2E Fragility Report — Enhanced Kiosk Challenge (June 30, 2026)

## Bugs Found

### B1: Multi-Pass Splitter Infinite Recursion 🔴 P0
**File:** `src/core/orchestrator.py:1440-1457`
**Symptom:** 24-file spec triggers multi-pass → `generate_subtask_spec` includes original spec text → subtask `execute_with_judge` calls `extract_file_refs` → finds 24 files again → splits again → `RecursionError`
**Root cause:** `plan_first=False` prevents the `or plan_first` branch but NOT the `len(file_refs) > MAX_FILES_PER_PASS` branch. The subtask spec contains all original file references.
**Workaround:** Kept spec under 20 files and avoided false-positive file references in text.
**Fix:** In `_execute_multi_pass`, set a context flag that `execute_with_judge` checks to skip the splitter. Or: `generate_subtask_spec` should NOT include the full original spec text — only pass-specific files.

### B2: PI Model Config Mismatch 🔴 P0
**File:** `~/.mrkrabs/config.yaml` vs `~/.pi/agent/models.json`
**Symptom:** `Model "local-23/qwen/qwen3-coder-30b" not found` (PI error)
**Root cause:** MR-Krabs uses `local-23/qwen/qwen3-coder-30b` but PI's provider registry uses `bakeoff23/ornith-35b-q4`. No mapping layer exists.
**Workaround:** Manually edited ~/.mrkrabs/config.yaml to match PI registry.
**Fix:** Add a PI provider mapping layer in the orchestrator so `pi_models` keys can use MR-Krabs provider names and auto-map to PI's registry. Or: sync the two configs via a generation script.

### B3: PI Missing OpenRouter API Key 🟡 P1
**File:** `~/.pi/agent/models.json`
**Symptom:** `No API key found for openrouter` on L1/L2 tiers
**Root cause:** PI's models.json has no `openrouter` provider entry for cloud escalation tiers.
**Workaround:** Reduced pipeline to L0-only (Principal as final).
**Fix:** Add OpenRouter provider to PI config. Read API key from `~/.hermes/secrets/openrouter-api-key` or env var `OPENROUTER_API_KEY`.

### B4: Orchestrator Hang on PI Subprocess 🟡 P1
**File:** `src/core/orchestrator.py:_execute_pi_tier`
**Symptom:** Orchestrator initialized, loaded spec, created debug dirs, then hung with 1.1% CPU, 161MB RSS. No output for >60s.
**Root cause:** Unclear — possibly PI subprocess stdout buffering, or the subprocess started but produced no output before the orchestrator's read timeout.
**Workaround:** Invoked PI directly via terminal.
**Fix:** Add subprocess stdout timeout in `_execute_pi_tier()`. If PI produces no output within 30s, log a diagnostic and retry. Add `stderr` capture and logging.

### B5: 16K Context Too Small for Large Files 🔴 P0
**File:** llama.cpp server on .23 (`--ctx-size 16384`)
**Symptom:** `400 request (16709 tokens) exceeds available context size (16384)` on any file >~4KB of generated code.
**Root cause:** PI's internal conversation format overhead is ~15K tokens, leaving <1KB for generated content. System prompt (~550 tokens) + task spec + generated code + tool call traces = overflow.
**Workaround:** Split into 7 tiny passes of 1-5 files each. Still lost 3/17 files.
**Fix:** Increase llama.cpp server context on .23 from 16K to 32K. From memory: "35B Q4_K_M KV cache at 32K overflows 24 GB VRAM into swap." Accept swap cost OR reduce to Q4_K_S quantization to fit 32K in 24GB.

### B6: Append-System-Prompt Context Bloat 🟢 P2
**File:** `docs/workflow/templates/code-pi-system-prompt.md` (2,208 chars)
**Symptom:** With `--append-system-prompt`, overflow at 16,709 tokens. Without it, overflow at 16,640. Difference: ~69 tokens.
**Root cause:** The appended system prompt adds to already-tight context budget.
**Workaround:** Ran without `--append-system-prompt` for critical passes.
**Fix:** Make the system prompt shorter (~500 chars) for PI mode. Or: PI should load the system prompt from a file path and inject it internally without adding conversation overhead.

### B7: Feedback Format Test Assertion Staleness 🟢 P2
**File:** `tests/unit/test_judge_escalation.py:222`
**Symptom:** `assert "Previous Attempt Feedback" in str(user_prompt)` failed
**Root cause:** Context compressor changed format to `"Previous Attempt 1 Feedback"` (numbered headings).
**Workaround:** Updated assertion.

### B8: Skill.md 100KB Char Limit 🟢 P2
**File:** `~/.hermes/skills/.../mr-krabs/SKILL.md`
**Symptom:** Could not add loop-engineering features section — "SKILL.md content is 101,424 characters (limit: 100,000)"
**Workaround:** Removed duplicate pitfall section, used `references/loop-engineering-features.md` file.

### B9: Challenge Script Python Import Path 🟢 P2
**File:** `.hermes/plans/run-enhanced-kiosk-challenge.py`
**Symptom:** `ModuleNotFoundError: No module named 'src'`
**Root cause:** Script not running from MR-Krabs repo root, sys.path not set.
**Workaround:** Added `sys.path.insert`, `os.chdir`, and `PYTHONPATH` env var.

### B10: Return Payload Missing escalated_to_principal After Consecutive Error Break 🟡 P1
**File:** `src/core/orchestrator.py`
**Symptom:** `test_all_tiers_exhausted_escalates_to_principal` failed — `escalated_to_principal` was None
**Root cause:** The `break` from consecutive error detection exited the tier loop, falling to the "all tiers exhausted" return which didn't set `escalated_to_principal`.
**Fix:** Added `escalated_by_consecutive_errors` flag set on break, wired into the return dict.

---

## Fragility-Addressing Changes (Priority Order)

### P0 — Must Fix (blocks production use)

1. **Fix multi-pass splitter recursion**
   - Add `context["_multi_pass_child"] = True` in `_execute_multi_pass` before calling `execute_with_judge`
   - In `execute_with_judge`, skip splitter when this flag is set
   - Or: modify `generate_subtask_spec` to NOT include full original spec text

2. **Add PI provider mapping layer**
   - Create `src/core/pi_provider_map.py` that translates MR-Krabs provider names → PI provider names
   - Auto-detect from `~/.pi/agent/models.json` on orchestrator init
   - Log a clear diagnostic when a model can't be resolved

3. **Increase llama.cpp context to 32K on .23**
   - Change `--ctx-size 16384` → `--ctx-size 32768` in systemd unit
   - Accept VRAM swap cost (~3 GB into swap from 24 GB)
   - Alternative: switch to Q4_K_S quantization to reduce KV cache footprint
   - Verification: run the full kiosk challenge in ONE pass after bumping

### P1 — Should Fix (removes friction)

4. **Add PI subprocess stdout timeout + diagnostics**
   - In `_execute_pi_tier`, after spawning PI, set a 30s timeout for first output
   - If no output within timeout, log PID, stderr, and model status
   - Add `[DIAG]` lines for: model resolution, API key check, server health check before PI spawn

5. **Add OpenRouter provider to PI models.json**
   - Read API key from `OPENROUTER_API_KEY` env var
   - Add `openrouter` provider block with DeepSeek V4 Flash and Mimo v2.5 models
   - Enables L1/L2 cloud escalation in MR-Krabs pipeline

6. **Pre-flight context size check**
   - Before spawning PI, estimate token count of (system_prompt + task_spec + PI overhead)
   - If estimated > 14K (safe margin for 16K context), warn and suggest splitting
   - If estimated > 16K, refuse to send and return clear error

### P2 — Nice to Have (quality of life)

7. **Reduce PI system prompt to ~500 chars**
   - The current `code-pi-system-prompt.md` is 2,208 chars (~552 tokens)
   - A 500-char version still conveys the essential rules
   - Particularly: "write code only", "complete implementations", "DONE when finished"

8. **Consolidate SKILL.md into smaller chunks**
   - Move detailed pitfall sections to references/ files
   - Keep SKILL.md under 80K chars to leave room for growth
   - Already partially done with `references/loop-engineering-features.md`

9. **Add orchestrator dry-run/debug mode**
   - `MRKRABS_DRY_RUN=1` → prints what it WOULD do without spawning subprocesses
   - Useful for debugging config mismatches without wasting model tokens
   - Shows: which model would be called, estimated token count, system prompt path

10. **Make challenge script self-contained**
    - Bundle the KIOSK_SPEC and KIOSK_SPEC_DICT in a standalone JSON file
    - Add `--check` flag that verifies PI/config/server health before running
    - Add `--passes N` flag to control split granularity
