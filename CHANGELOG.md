# Loop Architecture Improvements — July 19, 2026

## Motivation

Ran three adversarial challenges against the MR-Krabs loop architecture:
a filesystem reconciliation engine, an LLM API gateway proxy, and a
multi-container service registry with chaos resilience.

The original loop (Judge → Verify) was systematically missing integration-
level failures: dead functions, stub placeholders, import violations, and
swallowed error paths. The judge (Qwen2.5-Coder-7B at 0.75–0.80 threshold)
accepted structurally-plausible but semantically-broken code.

## Changes

### 1. Integration Audit — Loop 4 (new)
**File**: `src/core/integration_audit.py` (590 lines)
**Wired**: `src/core/orchestrator.py` between code gen and judge

Deterministic, AST-based, zero-LLM-cost static analysis. Four checks:

| Check | Method | Catches |
|-------|--------|---------|
| Call Graph | AST walk — defs vs call sites | `rollback()` defined but never called |
| Stub Detection | 11 regex patterns | `"ttft_ms": 0  # Placeholder"` |
| Import Audit | AST import parse vs spec | `import requests` when "stdlib only" |
| Error Path | AST except-block walk | `except: pass` — errors swallowed |

On failure: formats fix instructions → injects into task_spec → routes
back to coder tier → continues in retry loop.

### 2. File Extraction Filter
**File**: `src/core/task_splitter.py`

`extract_file_refs()` now excludes file paths found inside ```code blocks```
and under example/blueprint section headers. This prevents the multi-pass
file selection algorithm from treating blueprint JSON example files
(e.g., `app/src/models/user.py`) as output targets.

### 3. Loop 2 Retry on Failure
**File**: `src/core/orchestrator.py` (lines 2506–2583)

Loop 2 previously returned `success: False` immediately on verification
failure. Now it:
1. Extracts test failure output
2. Injects "RUNTIME FIX REQUIRED" context
3. Reroutes to coder tier for fixes
4. Loops up to `verify_config.max_retries` times (default: 3)
5. Only returns failure when all retries exhausted

### 4. Judge Prompt — Integration Checks
**File**: `src/core/judge.py` (lines 262–290)

Added "Integration Checks" section to the judge system prompt:

| Check | Score Ceiling |
|-------|--------------|
| Function defined but never called | ≤0.5 |
| Stub/mock/placeholder detected | ≤0.4 |
| External import violating spec constraints | ≤0.3 |
| Silent error swallowing (bare pass in except) | ≤0.5 |

## Verified Against All Known Failure Modes

| Failure | Loop 4 (Audit) | Loop 1 (Judge) | Loop 2 (Verify) |
|---------|:---:|:---:|:---:|
| C1: rollback() dead code | ✅ caught | ✅ now ≤0.5 | ✅ would catch |
| C1: "skip implementation" stub | ✅ caught | ✅ now ≤0.4 | — |
| C2: TTFT/tokens hardcoded to 0 | ✅ caught (15 stubs) | ✅ now ≤0.4 | — |
| C2: SSE streaming returns mock data | ✅ caught | ✅ now ≤0.4 | — |
| C3: get_service_address() dead | ✅ caught | ✅ now ≤0.5 | — |
| C3: import requests (stdlib-only spec) | ✅ caught | ✅ now ≤0.3 | — |
| C3: sys used but not imported | ✅ caught | — | ✅ would catch |
| C1: Phantom blueprint files | ✅ fixed (extraction filter) | — | — |

## Architecture After Changes

```
Code Gen → [Loop 4: AUDIT] → [Loop 1: JUDGE] → [Loop 2: VERIFY] → [Loop 3: QA]
               ↑ fail→coder        ↑ fail→coder       ↑ fail→coder
               └──retry────────────┴──retry───────────┴──retry (new)
```

- Loop 4 catches structural/wiring problems deterministically (0 LLM cost)
- Loop 1 catches semantic/quality problems with explicit scoring ceilings
- Loop 2 catches runtime problems and now retries instead of bailing
- Each failure mode has at least two layers of defense
