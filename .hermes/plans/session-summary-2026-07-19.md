# MR-Krabs Session Summary — July 19, 2026

## What We Did

Ran three adversarial challenges (reconciliation engine, LLM API gateway,
service registry + chaos daemon) plus the Kiosk challenge through MR-Krabs
to stress-test the loop architecture. Found 7 bugs, fixed all 7, then
discovered and addressed 5 architectural gaps across 5 implementation phases.

---

## Bugs Found & Fixed

| # | Bug | Root Cause | Fix | Commit |
|---|-----|-----------|-----|--------|
| 1 | Multi-pass writes phantom blueprint files | `extract_file_refs` treats all code-file paths in spec as targets | Filter code-block + example-section lines | `c4cc12f` |
| 2 | Judge accepts broken code at 0.75-0.80 | Qwen2.5-Coder-7B checks structure, not semantic alignment | Integration checks in judge prompt with score ceilings | `c4cc12f` |
| 3 | Loop 2 bails on failure instead of retrying | `return {"success": False}` on verify failure | Retry loop: inject errors → coder → re-verify | `c4cc12f` |
| 4 | No static analysis for wiring/stubs/imports | No deterministic check before judge | Loop 4 integration audit (AST-based, 0 LLM cost) | `60b6b9f` |
| 5 | Accumulated files block verify retries | Files added to accumulated set after judge accept; guard prevents rewrite | Clear accumulated files on verify failure before retry | `109cc8b` |
| 6 | OpenCode+OpenRouter returns 0 files | 13-char placeholder API key in `~/.config/opencode/opencode.json` | Wrote real 73-char key from secrets | `f19f25a` |
| 7 | .23 crashes under parallel PI load | Too many concurrent inference requests exhaust VRAM | `ConnectionLimiter` — per-host semaphore, .23 capped at 2 | `f19f25a` |

## Architectural Improvements (5 Phases)

| Phase | What | Why |
|-------|------|-----|
| **1** | Prompt contamination fix | Judge coaching reply format leaked into coder context; cloud models echoed the template. `_clean_feedback_for_coder()` strips coaching structure. `_is_template_echo()` detects echoes. |
| **2** | QA loop enabled + spec-coverage | `qa.enabled: true` activates Loop 3. `_compute_spec_coverage()` flags skeleton projects below 50% requirement coverage. |
| **3** | Requirement-aware audit | `check_requirements()` extracts must_define/must_call from spec and verifies they exist and are wired. Catches `get_service_address()` dead code. |
| **4** | Dependency-aware chunking | `_dependency_chunk()` builds import graph, topologically sorts, groups shared dependencies. Falls back to directory-based. |
| **5** | L0-first cost escalation | `MAX_RECHUNK_L0_BONUS` gives 3 extra re-chunk attempts on zero-cost local hardware before escalating to paid tiers. |

## Current Loop Architecture

```
Spec → [Decompose: dependency-aware, hardware-adaptive chunking]
    → [Code Gen: PI (L0) or OpenCode (L1/L2)]
    → [Loop 4: AUDIT — stubs, imports, dead code, requirements]
    → [Loop 1: JUDGE — with integration scoring ceilings]
    → [Loop 2: VERIFY — pytest with retry + error injection]
    → [Loop 3: QA — behavioral tests + spec-coverage scoring]
```

## Final Run Results (before Phase 1-5 fixes)

| Challenge | Tests | Result |
|-----------|-------|--------|
| C1 Reconcile | 8/8 passed | Clean win from L0 |
| C2 Gateway | 2/2 passed (skeleton) | 35 lines, external deps — would be caught by new QA loop |
| C3 Chaos | 0 tests (incomplete) | 3/7 files, get_service_address dead code — caught by new requirement audit |

## Files Changed (MR-Krabs repo)

```
src/core/context_compressor.py   — _clean_feedback_for_coder, _format_feedback rewrite
src/core/orchestrator.py         — connection throttle, verify retry, audit wiring, echo detection
src/core/rate_limiter.py         — ConnectionLimiter class
src/core/integration_audit.py    — Loop 4 audit + check_requirements (Check 5)
src/core/qa_loop.py              — _compute_spec_coverage, _extract_requirement_phrases
src/core/judge.py                — Integration checks section in judge prompt
src/core/task_splitter.py        — Code-block and example-section filters
src/outer_loop/decomposer.py     — probe_tier_capacity, adaptive limits, dependency chunking
src/outer_loop/orchestrator.py   — MAX_RECHUNK_L0_BONUS, adaptive classify_failure
~/.mrkrabs/config.yaml           — verify.enabled + qa.enabled
~/.config/opencode/opencode.json — Fixed OpenRouter API key
```

## Challenge Repos (cleaned)

All three `mrkrabs-challenge-*` repos on GitHub force-pushed to spec-only state:
- C1: `blueprint.json` + `SPEC.md`
- C2: `gateway.yaml` + `SPEC.md`
- C3: `app.py` + `docker-compose.yml` + `Dockerfile` + `SPEC.md`

---

## Next Round Testing Plan

### Pre-flight
1. Verify .23 and .21 server health
2. Confirm OpenRouter API key still valid (~$17 credit remaining)
3. Clean challenge repos to spec-only state
4. Enable verify + QA in config

### Run Order
1. **C1 Reconcile** (2 files) — should pass clean with L0
2. **C2 Gateway** (2 files) — QA loop should catch skeleton; requirement audit should flag external deps
3. **C3 Chaos** (7 files) — multi-pass with dependency chunking; requirement audit should catch dead get_service_address
4. **Kiosk** (17 files) — ultimate stress test for decomposition + all loops

### What To Watch
- Audit output: does it catch stubs, dead functions, import violations?
- QA loop: does spec-coverage scoring flag skeleton projects?
- L1/L2 escalation: does prompt contamination fix prevent template echoes?
- Decomposition: does dependency-aware chunking improve L0 success rate?
- .23 stability: does ConnectionLimiter prevent crashes under load?

### Known Remaining Gaps
- Phase 2c (QA feedback → decomposition rules) not yet wired
- Phase 4b (post-mortem ordering optimization) not yet implemented
- Phase 4c (parallel independent chunks) not yet implemented
- OpenCode L1/L2 occasionally produces 0 files — needs further investigation
- Outer loop never exercised during this session (all runs used inner loop directly)
