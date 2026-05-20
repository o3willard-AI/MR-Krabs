# MR-Krabs v0.2.0 — Judge-Based Escalation: Phases & Stories

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Judge Design:** [JUDGE.md](./JUDGE.md)
**Status:** Implemented ✓ | **Tests:** 884 passing | **Last updated:** 2026-05-20

---

## Phase 1: Judge + Verdict Engine ✅

### P4-1a — Judge Class & Verdict Evaluation ✅
**Implemented.** `Judge` class with configurable model (default: dedicated "Judge" = claude-sonnet-4.6),
`Verdict` dataclass, graceful error handling for network/API/JSON failures.
**Files:** `src/core/judge.py`, `tests/unit/test_judge.py` (32 tests)

### P4-1b — Judge Prompt Template & Criteria ✅
**Implemented.** Default criteria: correctness, completeness, style, safety, production_ready.
Configurable via `Judge(criteria=[...])`. Prompt template overridable via `judge.prompt_template`.
**Files:** `src/core/judge.py`, `src/core/judge_criteria.py`

---

## Phase 2: Refactor Escalation Loop ✅

### P4-2a — Rewrite Escalation to Use Judge + Retry Loop ✅
**Implemented.** `execute_with_judge()` replaces budget-driven escalation.
CostTracker is observer-only. Per-tier retry loop with judge evaluation.
Circuit breaker gates each tier. All old budget reservation logic removed.
**Files:** `src/core/orchestrator.py`, `tests/unit/test_judge_escalation.py`

### P4-2b — Retry + Feedback Prompt Injection ✅
**Implemented.** Judge critique injected as feedback on retry N+1.
**Files:** `src/core/orchestrator.py` (feedback injection), `tests/unit/test_feedback.py`

---

## Phase 3: Failure Actions + Human-in-the-Loop ✅

### P4-3a — FailureAction System ✅
**Implemented.** `FailureAction` enum (LOG_ONLY, NOTIFY_AND_ESCALATE, NOTIFY_AND_WAIT).
Per-tier configurable. Human confirmation via `~/.mrkrabs/pending/<task_id>.json`.
15-minute timeout with auto-abort.
**Files:** `src/core/failure_action.py`, `src/core/tier_config.py`, `src/core/human_gate.py`

### P4-3b — Notifier Base + MeshNotifier ✅
**Implemented.** Pluggable notifiers: MeshNotifier, TelegramNotifier, NoopNotifier.
Fallback chain: Mesh → Telegram → log file.
**Files:** `src/core/notify.py`, `tests/unit/test_notify.py`

---

## Phase 4: Fail-Now Signal ✅

### P4-4a — FailNow Mechanism ✅
**Implemented.** `set_fail_now("L1-Coder")`, env var `MRKRABS_FAIL_NOW`, mesh signal file.
Auto-clears after use. Falls through if target tier unavailable.
Also: FailUp signal (`set_fail_up()`, `MRKRABS_FAIL_UP`) — abort current tier, bump up one.
**Files:** `src/core/fail_now.py`, `tests/unit/test_fail_now.py`

---

## Phase 5: Integration Testing ✅

### P4-5a — Judge Integration Tests ✅
**Implemented.** 11 E2E scenarios with mocked HTTP: L0 accepts, L0 rejects→retry succeeds,
L0 exhausts→L1, fail-now, HTTP failure fallthrough, JSON parse degradation, cost tracking,
feedback injection, all-tiers-exhausted, circuit breaker, FailUp.
**Files:** `tests/integration/test_judge_escalation_e2e.py` (11 tests)

### P5-5b — Live Tier Escalation Test (Proxmox VM) ✅
**Performed.** Real LM Studio L0 + OpenRouter L1/L2 calls on a fresh Ubuntu VM.
Tested Fibonacci, Bloom Filter, and LRU Cache challenges. Judge None bug found and fixed.
VM cleaned up after testing.

---

## Phase 6: Polish & Docs ✅

### P4-6a — Cleanup, Docs, & Deprecation ✅
**Done.** Dead budget-control code removed. Judge prompt upgraded with LMSYS/G-Eval
patterns and 5-point coaching replies. Agent system prompt added (SotA coding agent
patterns). Architecture docs refreshed.
**Files:** `docs/ARCHITECTURE.md`, `docs/JUDGE.md`, `docs/workflow/templates/agent-system-prompt.md`

---

## Phase 7: Principal Agent & Judge Decoupling ✅

### P7-1 — Dedicated Judge Model ✅
**Implemented.** Judge decoupled from agent tiers. New "Judge" entry in MODELS
(anthropic/claude-sonnet-4.6, temp 0.1). Documented best practice: Judge must
always be a reasoning model.
**Files:** `src/core/model_config.py`, `src/core/judge.py`

### P7-2 — Principal Agent Escalation ✅
**Implemented.** "Principal" tier added to MODELS and TIER_ORDER. Default escalation
path: L0 → L1 → L2 → Principal. When reached, returns structured escalation_context
instead of making an LLM call. L3-Coder remains available as optional cloud tier.
**Files:** `src/core/model_config.py`, `src/core/orchestrator.py`, `src/core/tier_manager.py`

### P7-3 — Agent System Prompt ✅
**Implemented.** Agent system prompt based on Aider/SWE-agent/CodeAct patterns:
role definition, tool docs, output format, conventions, anti-hallucination guards.
Wired into `execute_with_judge()` via `_get_agent_system_prompt()`.
**Files:** `docs/workflow/templates/agent-system-prompt.md`, `src/core/orchestrator.py`

### P7-4 — SoTA Judge Prompt with Coaching ✅
**Implemented.** Judge prompt upgraded with LMSYS impartial judge framing,
G-Eval anchored rubric, verbosity bias warning, and mandatory 5-point coaching
reply structure. Prompt engineering documented in JUDGE.md.
**Files:** `src/core/judge.py`, `docs/JUDGE.md`

---

## Test Coverage

| Category | Count | Status |
|----------|-------|--------|
| Unit tests | ~850 | All passing |
| Integration tests | 11 | All passing |
| E2E (live VM) | 3 challenges | Complete |
| **Total** | **884** | **0 failures** |

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/core/orchestrator.py` | `execute_with_judge()` — main escalation pipeline |
| `src/core/judge.py` | Judge class, coaching prompt, verdict evaluation |
| `src/core/judge_criteria.py` | Default criteria + task type detection |
| `src/core/model_config.py` | MODELS dict — all tiers + Judge + Principal |
| `src/core/failure_action.py` | FailureAction enum |
| `src/core/fail_now.py` | FailNow/FailUp signals |
| `src/core/notify.py` | Pluggable notification backends |
| `src/core/human_gate.py` | Human-in-the-loop confirmation |
| `src/core/circuit_breaker.py` | Per-model circuit breaker |
| `src/core/cost.py` | CostTracker — observer-only spend tracking |
| `docs/ARCHITECTURE.md` | Full architecture documentation |
| `docs/JUDGE.md` | Judge best practices, prompt design, coaching spec |
| `docs/workflow/templates/agent-system-prompt.md` | Agent system prompt template |
