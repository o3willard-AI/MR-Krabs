# MR-Krabs v0.2.0 — Judge-Based Escalation: Phases & Stories

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Status:** Not started
**Total effort:** 5 days across 6 phases, 14 user stories

---

## Phase 1: Judge + Verdict Engine (1 day)

### P4-1a — Judge Class & Verdict Evaluation
**Goal:** Implement the `Judge` class that evaluates LLM output quality using an LLM judge (default: L2-Coder).
**Files:** `src/core/judge.py`, `tests/unit/test_judge.py`
**Acceptance:**
- `Verdict` dataclass: `accepted`, `score` (0.0–1.0), `critique`, `checks_passed`, `checks_failed`
- `Judge(model="L2-Coder")` constructor with configurable criteria
- `judge.evaluate(task: str, output: str) -> Verdict` sends prompt to L2 model, parses JSON response
- Handles judge LLM failure gracefully — returns `accepted=False` with error as critique
- 15+ unit tests: valid JSON parse, invalid JSON, judge model unavailable, edge cases (empty output, non-code tasks), criterion customization
- 95%+ test coverage on judge.py

### P4-1b — Judge Prompt Template & Criteria
**Goal:** Configurable judge prompt with default + custom criteria.
**Files:** `src/core/judge.py` (extend), `src/core/judge_criteria.py`
**Acceptance:**
- Default criteria: correctness, completeness, style, safety
- Users can pass custom criteria list to `Judge(criteria=["does it compile", "no SQL injection"])`
- Prompt template is a property on Judge, overridable via `judge.prompt_template`
- Prompt auto-adapts for non-code tasks (detects if task mentions "write code" vs general Q&A)
- `score` threshold default 0.7 — configurable via `judge.acceptance_threshold`
- 10+ tests: custom criteria, non-code task detection, threshold variations

---

## Phase 2: Refactor Escalation Loop (1 day)

### P4-2a — Rewrite `_ask_with_escalation()` to Use Judge + Retry Loop
**Goal:** Replace the current hardcoded budget-driven escalation in `execute_task()` with the judge/retry/feedback pattern.
**Files:** `src/core/orchestrator.py` (refactor `execute_task` → new `execute_with_judge`), `tests/unit/test_judge_escalation.py`
**Acceptance:**
- **Delete** the budget reservation logic from `execute_task()` — CostTracker becomes observer-only
- New method `execute_with_judge()`:
  ```
  for tier in [L0-Coder, L1-Coder, L2-Coder, L3-Coder]:
      for retry in 1..max_retries:          # configurable per tier, default 3
          output = tier.call(prompt + feedback)  # feedback from prior judge verdict
          verdict = judge.evaluate(task, output)
          if verdict.accepted:
              return output, tier, cost_summary
          feedback = verdict.critique       # fed back to next retry attempt
      # retries exhausted → failure action
      handle_failure_action(tier, spend, verdict)
  ```
- Retry counter resets per tier (not cumulative across tiers)
- `feedback` parameter injected into LLM prompt on retries 2+
- CostTracker records spend per call, never blocks
- Circuit breaker still gates per-model calls
- 12+ tests: happy path (accept on first try), retry-2 acceptance, retry exhaustion escalating, feedback injection format, circuit breaker integration, cost tracking observer-only mode

### P4-2b — Retry + Feedback Prompt Injection
**Goal:** The feedback from the judge's `critique` field is properly injected into the next retry's prompt so the LLM can self-correct.
**Files:** `src/core/orchestrator.py` (extend), `tests/unit/test_feedback_loop.py`
**Acceptance:**
- On retry N+1, append to user prompt: `\n\n## Previous Attempt Feedback\n\nThe prior output was rejected by the quality judge with score {score}.\nCritique: {critique}\n\nPlease fix these issues and try again.`
- Feedback is NOT injected on first attempt (retry 1)
- Feedback is cumulative: retry 3 sees feedback from retries 1 and 2 (concatenated with `\n---\n` separator)
- 8+ tests: single retry feedback format, cumulative multi-retry feedback, edge case: empty critique, edge case: very long critique truncated to 2000 chars

---

## Phase 3: Failure Actions + Human-in-the-Loop (1 day)

### P4-3a — FailureAction System
**Goal:** Implement per-tier configurable failure actions: LOG_ONLY, NOTIFY_AND_ESCALATE, NOTIFY_AND_WAIT.
**Files:** `src/core/failure_action.py`, `src/core/tier_config.py` (extend MODELS dict), `tests/unit/test_failure_action.py`
**Acceptance:**
- `FailureAction` enum: `LOG_ONLY`, `NOTIFY_AND_ESCALATE`, `NOTIFY_AND_WAIT`
- `TierConfig` dataclass extends the existing MODELS dict entries with:
  - `failure_action: FailureAction` (default per-tier)
  - `max_retries: int` (default 3)
  - `judge_model: str` (default "L2-Coder", per-tier overridable)
- Defaults match ARCHITECTURE.md spec:
  - L0-Coder: LOG_ONLY, 3 retries
  - L1-Coder: NOTIFY_AND_ESCALATE, 3 retries
  - L2-Coder: NOTIFY_AND_WAIT, 3 retries
  - L3-Coder: NOTIFY_AND_WAIT, 2 retries
- Human confirmation mechanism for NOTIFY_AND_WAIT:
  - Writes a JSON file to `~/.mrkrabs/pending/<task_id>.json`
  - Blocks (polls file every 2s) for `{confirmed: true}` or `{confirmed: false, reason: "..."}`
  - Timeout: 15 minutes → auto-abort
- 10+ tests: each action type, wait timeout, human confirmed, human rejected, per-tier defaults, custom config

### P4-3b — Notifier Base + MeshNotifier
**Goal:** Pluggable notification backends for when escalation needs human attention.
**Files:** `src/core/notify.py`, `tests/unit/test_notify.py`
**Acceptance:**
- `Notifier` ABC with `send(message: str, urgency: str, context: dict) -> bool`
- `MeshNotifier`: sends via agent mesh → primary agent (uses `mesh_send.py` at `~/.hermes/scripts/mesh_send.py`, or logs to file if mesh unavailable)
- `TelegramNotifier`: sends via Telegram if `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars set
- `NoopNotifier`: silent, for testing
- Fallback chain: MeshNotifier → TelegramNotifier → log to file (never lose a notification)
- Notification message includes: task_id, current tier, spend so far, failure reason, what action is being taken, what's needed from human (if WAIT mode)
- 12+ tests: each notifier, fallback chain, mesh unavailable, telegram unavailable, message format

---

## Phase 4: Fail-Now Signal (0.5 day)

### P4-4a — FailNow Mechanism
**Goal:** Human or agent can preempt the escalation loop: skip to specified tier, one shot, no budget check.
**Files:** `src/core/fail_now.py`, `src/core/orchestrator.py` (integrate), `tests/unit/test_fail_now.py`
**Acceptance:**
- `set_fail_now(tier="L3-Coder")` — sets module-level state for the next `ask()` call
- `clear_fail_now()` — resets after `ask()` completes (auto-cleared)
- Env var: `MRKRABS_FAIL_NOW=L2-Coder` as alternative trigger
- Mesh message listener: `mrkrabs://fail-now` topic — an agent or human can trigger remotely
- When fail_now is active:
  - Skips directly to specified tier
  - Calls exactly once, no retry loop, no judge
  - Returns whatever the model produces
  - Cost is tracked but budget is completely ignored
  - After returning, fail_now is cleared automatically
- If target tier is unavailable (circuit breaker open) → falls through to next tier with log warning
- 10+ tests: env var path, function path, mesh message path, auto-clear, tier unavailable fallthrough, cost tracking intact

---

## Phase 5: Integration Testing (1 day)

### P4-5a — Judge Integration Tests
**Goal:** End-to-end tests for the judge-based escalation with real LLM calls (mocked at HTTP level).
**Files:** `tests/integration/test_judge_escalation_e2e.py`
**Acceptance:**
- Mock HTTP: simulate L0 produces low-quality output, L1 produces acceptable output → verify L1 output returned with 2 tiers logged
- Mock HTTP: simulate L0+L1 fail quality, L2 accepted → verify escalation to L2 with NOTIFY_AND_ESCALATE action triggered
- Mock HTTP: simulate NOTIFY_AND_WAIT at L2 → verify pending file written, human confirm → resume
- Mock HTTP: simulate NOTIFY_AND_WAIT timeout at L2 → verify abort with cost summary
- Mock HTTP: fail_now at L3 → verify skip-all, one-shot, return
- CostTracker observer: verify cost tracked as observer (recorded, never blocked)
- 12+ integration tests

### P4-5b — Tier Escalation Integration Test (clean Ubuntu VM)
**Goal:** Real subagent tests with actual LM Studio L0 and OpenRouter L1/L2 calls, verifying the full escalation pipeline works on a fresh system.
**Files:** `tests/integration/test_live_escalation.py`
**Acceptance:**
- Provision clean Ubuntu VM via Linus deployment specialist (Proxmox)
- Install MR-Krabs + deps on VM
- Configure L0 → LM Studio `qwen3-coder-30b` at `192.168.101.21:1234`
- Configure L1 → OpenRouter `x-ai/grok-4.3`
- Configure L2 → OpenRouter `minimax/minimax-m2.7` (judge default)
- Test 1: trivial task → L0 accepts → returns with 1 tier, $0 cost
- Test 2: complex task L0 fails quality → L1 retries with feedback → L1 accepted
- Test 3: complex task exhausts L0+L1 → L2 judge evaluates → L2 accepted with NOTIFY_AND_WAIT triggered → pending file written
- Test 4: fail_now at L3 → direct call, skip all
- Verify all costs logged, no budget blocking
- 6+ integration tests

---

## Phase 6: Polish & Docs (0.5 day)

### P4-6a — Cleanup, Docs, & Deprecation
**Goals:** Remove dead budget-control code paths, update docs, add deprecation warnings.
**Files:** Various
**Acceptance:**
- Remove `max_cost` parameter from any remaining ask() signatures
- Remove `BudgetExceededError` raise-on-record behavior from CostTracker (keep the exception class, just stop raising on `record()`) — it becomes a pure observer
- Add deprecation warning if old `_ask_with_escalation()` is called (redirects to new method)
- Update README with judge-based escalation architecture
- Run full test suite: 947 existing + new tests, 0 regressions
- Lint + security scan pass (bandit)
- Manual integration test on fresh VM — pass all 4 scenarios from P4-5b

### P4-6b — Skill Capture
**Goal:** Capture the judge-based escalation pattern as a reusable skill for future orchestration projects.
**Files:** Skill in `~/.hermes/skills/`
**Acceptance:**
- Create `judge-based-escalation` skill with the architecture pattern
- Include: when to use, judge prompt template, failure action config, pitfalls

---

## Phase Dependencies

```
Phase 1 (Judge + Verdict)
  ↓
Phase 2 (Escalation Loop Refactor)
  ↓
Phase 3 (Failure Actions + Notifier) ←── Phase 1 optional dependency (judge model for notifier)
  ↓
Phase 4 (Fail Now)
  ↓
Phase 5 (Integration Tests)
  ↓
Phase 6 (Polish)
```

Phases 3 and 4 can partially overlap if needed.

## What Stays (untouched)
- `CostTracker` — refactored to observer-only (never blocks), but the class stays
- `MODELS` dict — extended with failure_action, max_retries fields
- `CircuitBreaker` + `CircuitBreakerRegistry` — used as-is, gating each model call
- `RateLimiter` — stays, optional throttling
- `ToolExecutor` + `FileTools` — unchanged
- All 947 existing tests — must continue passing

## What Gets Deleted/Changed
- Budget reservation logic in `execute_task()` — removed entirely
- `BudgetExceededError` raise in `CostTracker.record()` — removed (exception class kept for reference)
- `max_cost` on any ask() interface — removed
- `_ask_with_escalation()` — deprecated, redirects to new method
