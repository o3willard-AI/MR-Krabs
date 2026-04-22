# Remediation Task List — Peer Review Findings

**Generated**: 2026-04-03
**Sources**: REVIEW_ARCHITECTURE_2026-04-03.md, REVIEW_DX_2026-04-03.md, REVIEW_PERFORMANCE_2026-04-03.md
**Status**: Pending prioritization

---

## Priority Legend
- **P0** — Critical: correctness, budget safety, data loss
- **P1** — High: core functionality, developer adoption blockers
- **P2** — Medium: quality-of-life, maintainability, scalability prep
- **P3** — Low: nice-to-have, future-proofing

---

## TASK 1 — Resolve Library vs. Service Identity Crisis

**Source**: Architecture §2.1 (Critical)
**Priority**: P0
**Owner**: TBD

### Description
The project describes itself as a "pip-installable Python library" but the architecture includes Docker, Kubernetes, PostgreSQL, Redis, RabbitMQ, FastAPI, React dashboard, and multi-tenant architecture. These are two different products. Phase 1-2 must be exclusively the library; server/platform concerns must be moved to a "Future Architecture" appendix.

### Acceptance Criteria
- [ ] SYSTEM_ARCHITECTURE.md production deployment diagrams (Sections 4.2, 4.3) moved to a "Future Architecture" appendix
- [ ] IMPLEMENTATION_ROADMAP.md Phase 3-4 items (web dashboard, multi-tenant, federated learning) marked as out-of-scope/separate project
- [ ] pyproject.toml dependencies contain zero infrastructure requirements (no database drivers, no web framework)
- [ ] README.md explicitly states the project is a library, not a service
- [ ] A separate document `docs/FUTURE_SERVER_MODE.md` created for server/dashboard ambitions, explicitly decoupled from v1

### Functional Validation
- `pip install .` succeeds with only library-level dependencies
- No Docker/Kubernetes/PostgreSQL/Redis references in any Phase 1-2 source code
- Architecture doc clearly labels server-mode content as "Future / Out of Scope"

---

## TASK 2 — Fix Concurrent Budget Race Condition

**Source**: Architecture §2.3 (Critical), Performance §3.1 (High)
**Priority**: P0
**Owner**: TBD

### Description
The `check_budget() → execute → record_spending()` sequence has a classic check-then-act race condition. Two concurrent tasks can both pass the budget check and both execute, exceeding the budget. Budget enforcement is the #1 value proposition.

### Acceptance Criteria
- [ ] Implement atomic `reserve_budget(scope, estimated_cost)` that atomically decrements remaining budget
- [ ] Implement `finalize_spending(scope, reservation_id, actual_cost)` to adjust reservation to actual cost
- [ ] Implement `release_reservation(scope, reservation_id)` to return reservation on failure
- [ ] SQLite path uses `BEGIN EXCLUSIVE` transactions for atomic reserve
- [ ] PostgreSQL path uses `SELECT ... FOR UPDATE` or atomic `UPDATE ... WHERE spent + $1 <= limit RETURNING *`
- [ ] In-memory budget ledger with periodic SQLite checkpoints for Phase 1 concurrency
- [ ] All budget check methods are `async def`

### Functional Validation
- Concurrent stress test: 100 tasks with $10 budget, verify total spent ≤ $10 + MAX_SINGLE_TASK_COST
- Race condition unit test: simulate interleaved check/execute/record and verify no overrun
- Benchmark: `test_concurrent_budget_accuracy` from Performance Review §5.2 passes

---

## TASK 3 — Fix Context Simplification for Unstructured Context

**Source**: Architecture §2.2 (Critical), Performance §5.5, §8.5
**Priority**: P0
**Owner**: TBD

### Description
Context simplification assumes structured context with identifiable sections. This fails for unstructured prompts, code-heavy context, and conversation history. `ContextPruner.truncate_file` has a `pass` body — completely unspecified.

### Acceptance Criteria
- [ ] Implement robust fallback for unstructured context: token-budget truncation from end, preserving original instruction
- [ ] Fully specify and implement `truncate_file` — use tree-sitter or AST parsing for Python/JS/TS to keep signatures and docstrings
- [ ] Add "context simplification helpfulness" metric: track whether simplified retries succeed more often than unsimplified
- [ ] Make context simplification optional and off by default until proven helpful
- [ ] Single-pass token estimation instead of per-section calls

### Functional Validation
- Unit test: unstructured string input produces valid truncated output preserving instruction
- Unit test: Python file truncation preserves function signatures and docstrings
- Benchmark: `test_context_simplification_large_input` from Performance Review §5.5 passes (<10ms for 500KB)
- Integration test: context simplification helpfulness metric is recorded and queryable

---

## TASK 4 — Fix Circuit Breaker Granularity and Race Conditions

**Source**: Architecture §3.2, Performance §3.2, §2.3
**Priority**: P1
**Owner**: TBD

### Description
Circuit breaker is keyed on `provider` only, not `(provider, model)`. If one model on a provider is degraded, all models on that provider are blocked. Additionally, there's a race condition in HALF_OPEN state where stale successes accumulate.

### Acceptance Criteria
- [ ] Circuit breaker keyed on `(provider, model)` pairs
- [ ] In `record_success()`, if state is OPEN (because another thread re-opened it), ignore the success
- [ ] Reset counters when transitioning from HALF_OPEN to OPEN
- [ ] Add `_half_open_epoch` counter that increments on each HALF_OPEN entry; discard results from previous epochs
- [ ] Use `collections.deque` or `queue.Queue` for `_pending_spends` with atomic drain in `reconcile_pending_spends()`

### Functional Validation
- Unit test: one model failing does not affect circuit breaker state for another model on same provider
- Unit test: HALF_OPEN race condition — concurrent test requests don't corrupt state
- Unit test: `reconcile_pending_spends()` doesn't lose entries added during iteration

---

## TASK 5 — Fix Default Budget Failure Mode

**Source**: Architecture §3.3
**Priority**: P1
**Owner**: TBD

### Description
Default budget failure mode is "fail_closed". For individual developers, having work stop due to SQLite lock contention is a terrible experience. Default should be `fail_open_with_alert` with an emergency cap.

### Acceptance Criteria
- [ ] Default failure mode changed to `fail_open_with_alert`
- [ ] Emergency cap implemented (default: 10 untracked calls or $5.00)
- [ ] `fail_closed` documented as recommended for team/production use
- [ ] Alert mechanism logs warnings when emergency cap is engaged

### Functional Validation
- Unit test: budget system in fail_open_with_alert mode allows tasks after budget exceeded, up to emergency cap
- Unit test: tasks blocked after emergency cap exceeded
- Unit test: fail_closed mode still available and works as before

---

## TASK 6 — Migrate from YAML to TOML Configuration

**Source**: Architecture §3.4
**Priority**: P1
**Owner**: TBD

### Description
YAML has indentation sensitivity, type coercion surprises, and security risks with `yaml.load()`. TOML is simpler, has no security risks, has native Python support (`tomllib` in 3.11+), and is the Python standard.

### Acceptance Criteria
- [ ] Configuration file format changed from `.cost_orchestrator.yaml` to `.cost_orchestrator.toml`
- [ ] `pyyaml` removed from core dependencies (or restricted to `yaml.safe_load()` only if kept for backward compat)
- [ ] `tomllib` (stdlib 3.11+) used for config parsing
- [ ] TOML schema provided for IDE validation
- [ ] Migration guide written for existing YAML configs

### Functional Validation
- Unit test: valid TOML config loads correctly
- Unit test: invalid TOML config produces clear error message
- Unit test: type coercion works correctly (no `NO` → `false` surprises)
- Existing YAML config migration script produces equivalent TOML

---

## TASK 7 — Standardize Cost Savings Claims and Build Benchmark Suite

**Source**: Architecture §3.5, §C1, Architecture §Q2
**Priority**: P1
**Owner**: TBD

### Description
Cost savings claims are inconsistent across documents (60-80%, 5-10x, 40-70% progressive). No benchmark suite exists to prove claims. L0 success rate and output quality are not reported.

### Acceptance Criteria
- [ ] Single standardized claim defined precisely: "X% reduction in LLM API costs compared to [model], measured on [benchmark]"
- [ ] All documents updated to use consistent claim
- [ ] Benchmark suite created with 20-50 tasks of known difficulty and known correct outputs
- [ ] Benchmark reports both cost savings AND quality metrics (correctness, not just "did the LLM return something")
- [ ] L0 success rate measured and reported separately from overall success rate

### Functional Validation
- Benchmark suite runs end-to-end and produces a report
- Report includes: cost savings %, quality score per task, L0 success rate, per-tier distribution
- All marketing/docs numbers match benchmark results

---

## TASK 8 — Resolve Adapter Pattern for Framework Integrations

**Source**: Architecture §3.6
**Priority**: P1
**Owner**: TBD

### Description
The `BaseFrameworkAdapter` interface assumes stable interfaces for CrewAI, LangChain, AutoGen, SuperGen — all pre-1.0 and changing rapidly. Build each integration independently with its own idiomatic API. Prioritize CrewAI deeply.

### Acceptance Criteria
- [ ] `BaseFrameworkAdapter` abstraction removed or simplified
- [ ] CrewAI integration built as standalone, idiomatic module
- [ ] LangChain integration deferred or built as separate standalone module
- [ ] AutoGen integration explicitly deferred (out of scope for v1)
- [ ] CI job tests against framework `main` branches to detect breaking changes
- [ ] Integration documented with "before/after" migration guide (DX §4.3)

### Functional Validation
- CrewAI integration test: wrap existing CrewAI crew, verify cost tracking works
- CI test against CrewAI `main` branch passes or produces clear failure report
- AutoGen integration code removed or marked as "future"

---

## TASK 9 — Add Global Task Timeout

**Source**: Architecture §4.4
**Priority**: P1
**Owner**: TBD

### Description
Worst-case escalation path (9 LLM calls with exponential backoff) could take 10+ minutes. No global timeout exists.

### Acceptance Criteria
- [ ] Configurable `max_task_duration_seconds` added (default: 300s = 5 minutes)
- [ ] Entire escalation loop is aborted when timeout exceeded
- [ ] Partial results and costs recorded on timeout
- [ ] Timeout error clearly distinguishes from LLM errors

### Functional Validation
- Unit test: task with `max_task_duration_seconds=1` times out and records partial cost
- Benchmark: `test_worst_case_escalation_latency` from Performance Review §5.3 passes (<30s with default timeout)

---

## TASK 10 — Add Model Capability Registry

**Source**: Architecture §5.1
**Priority**: P1
**Owner**: TBD

### Description
No mechanism to check "can this model handle this task's context window?" before sending the request. Models vary in context window size (4K to 200K), tool-calling support, and language proficiency.

### Acceptance Criteria
- [ ] Model capability registry with: context window size, tool-calling support, supported languages
- [ ] Pre-flight check: "can this model handle this task?" before sending request
- [ ] Automatic fallback to capable model when capability check fails
- [ ] Registry populated for all configured tier models

### Functional Validation
- Unit test: task exceeding model context window is rejected or routed to larger model
- Unit test: model without tool-calling capability is not assigned tool-heavy tasks
- Registry covers all models in default tier configuration

---

## TASK 11 — Add Streaming Support

**Source**: Architecture §5.2
**Priority**: P2
**Owner**: TBD

### Description
Architecture assumes request-response LLM calls. Modern LLM usage heavily relies on streaming responses for UX.

### Acceptance Criteria
- [ ] Provider adapters support streaming responses
- [ ] Orchestrator `execute_task()` has `stream=True` option
- [ ] Streaming results yield chunks as they arrive
- [ ] Cost tracking works correctly with streaming (token counts from stream)
- [ ] Escalation logic works with streaming (detect failure mid-stream)

### Functional Validation
- Integration test: streaming response yields chunks before completion
- Cost tracking: streamed response cost matches non-streamed equivalent
- Escalation: streaming failure triggers escalation correctly

---

## TASK 12 — Add Graceful Shutdown

**Source**: Architecture §5.3
**Priority**: P1
**Owner**: TBD

### Description
If orchestrator is killed during escalation loop, there's no mechanism to record partial cost, resume/replay task, or clean up in-flight reservations.

### Acceptance Criteria
- [ ] SIGTERM/SIGINT handlers registered
- [ ] In-flight budget reservations released on shutdown
- [ ] Partial task cost recorded before exit
- [ ] Task state persisted for potential resume

### Functional Validation
- Integration test: send SIGTERM during task execution, verify partial cost recorded
- Integration test: budget reservations cleaned up after shutdown
- No budget leakage after forced shutdown

---

## TASK 13 — Add Config Versioning and Migration

**Source**: Architecture §5.4, Architecture §C5
**Priority**: P2
**Owner**: TBD

### Description
Config file has `version: "1.0"` but no migration mechanism. When config format changes, users need a migration path.

### Acceptance Criteria
- [ ] Config version validation on load
- [ ] Migration functions for each version bump
- [ ] Clear error message when config version is incompatible
- [ ] `orchestrator config migrate` CLI command
- [ ] Remove confusing "6-level to 3-level" reference from TECHNICAL_DESIGN_DECISIONS.md

### Functional Validation
- Unit test: v1.0 config loads with v1.1 code (via migration)
- Unit test: incompatible config version produces clear error with migration instructions
- CLI command `orchestrator config migrate` successfully upgrades config file

---

## TASK 14 — Add Orchestrator-Level Rate Limiting

**Source**: Architecture §5.5
**Priority**: P2
**Owner**: TBD

### Description
System handles provider rate limits reactively but doesn't proactively rate-limit its own calls. 1000 concurrent tasks hitting OpenRouter simultaneously becomes a DDoS.

### Acceptance Criteria
- [ ] Configurable requests-per-second limit per provider
- [ ] Token bucket or sliding window rate limiter implemented
- [ ] Rate limit errors distinguished from provider errors
- [ ] Default rate limits set for common providers

### Functional Validation
- Unit test: rate limiter enforces configured RPS
- Integration test: 1000 concurrent tasks respect rate limits
- No provider rate-limit errors under normal configured load

---

## TASK 15 — Add Prompt Format Compatibility Layer

**Source**: Architecture §5.6
**Priority**: P2
**Owner**: TBD

### Description
Some models require specific prompt formats (ChatML, Llama format, etc.). Architecture assumes all models accept the same message format.

### Acceptance Criteria
- [ ] Provider adapters handle prompt formatting per model
- [ ] Format registry maps models to their required prompt format
- [ ] Automatic format conversion before sending to provider

### Functional Validation
- Unit test: ChatML-formatted prompt sent to models requiring ChatML
- Unit test: Llama-formatted prompt sent to Llama models
- Cross-model test: same task works across models with different prompt formats

---

## TASK 16 — Separate Tiers from Roles in Configuration

**Source**: Architecture §3.1
**Priority**: P2
**Owner**: TBD

### Description
Tier names like "L0-Coder", "L1-Coder" conflate cost tier with task role. These are orthogonal dimensions.

### Acceptance Criteria
- [ ] Tiers defined as `L0, L1, L2, L3` (cost levels only)
- [ ] Roles are user-defined labels, separate from tiers
- [ ] Mapping `(role, tier) → model` is configuration
- [ ] Escalation chain is `L0 → L1 → L2 → L3` regardless of role
- [ ] User-facing API supports human-readable tier names: `free`, `cheap`, `standard`, `premium` (DX §5.2)

### Functional Validation
- Unit test: same tier works with different roles
- Unit test: escalation works regardless of role label
- Config: `orchestrator.execute("task", tier="cheap")` works

---

## TASK 17 — Fix Duplicate Code in orchestrator.py

**Source**: Project structure observation
**Priority**: P0
**Owner**: TBD

### Description
`src/core/orchestrator.py` contains duplicated code — `main()` function and several private methods are defined twice (lines 399-463 and 479-563, then again 566-629 and 636-703).

### Acceptance Criteria
- [ ] Duplicate methods removed; single canonical implementation retained
- [ ] `main()` function defined exactly once
- [ ] No functional regression after deduplication

### Functional Validation
- All existing tests pass after deduplication
- `python -c "import ast; ast.parse(open('src/core/orchestrator.py').read())"` succeeds
- No duplicate function names in module namespace

---

## TASK 18 — Fix pyproject.toml Entry Point

**Source**: Project structure observation
**Priority**: P1
**Owner**: TBD

### Description
`pyproject.toml` entry point `orchestrator = "src.main:cli"` points to `src.main:cli`, but actual CLI is at `src/cli/main.py` with a `main()` function.

### Acceptance Criteria
- [ ] Entry point corrected to `orchestrator = "src.cli.main:main"` (or equivalent)
- [ ] `pip install -e .` then `orchestrator --help` works

### Functional Validation
- `pip install -e . && orchestrator --help` displays help text
- No ModuleNotFoundError on CLI invocation

---

## TASK 19 — Create README.md with Quickstart

**Source**: DX §4.1, DX §2.1, DX §2.2
**Priority**: P0
**Owner**: TBD

### Description
No GitHub README exists for the library. A developer discovering this on GitHub sees 3,000+ lines of architecture docs and zero runnable code.

### Acceptance Criteria
- [ ] README.md with: one-sentence description, before/after code comparison, installation command, hello world example (5 lines), link to full docs
- [ ] Junior developer explanation as first paragraph (DX §Q3)
- [ ] Zero-config quickstart: `pip install` + env var = working

### Functional Validation
- README hello world example runs successfully with just `pip install` and one env var
- A new developer can get a result in <5 minutes following README alone

---

## TASK 20 — Implement Zero-Config Default Experience

**Source**: DX §2.1, DX §2.2
**Priority**: P0
**Owner**: TBD

### Description
Minimum config requires setting env vars, creating YAML file, writing Python code. Should work with just `OPENROUTER_API_KEY` env var.

### Acceptance Criteria
- [ ] `pip install cost-orchestrator` gives working system with zero config
- [ ] Auto-detect `OPENROUTER_API_KEY` env var
- [ ] Default config works with OpenRouter only (no LM Studio required)
- [ ] L0 defaults to cheapest available OpenRouter model
- [ ] Simple `ask()` API: `from cost_orchestrator import ask; result = ask("task")`

### Functional Validation
- `pip install -e .` + `OPENROUTER_API_KEY=xxx` + `python -c "from cost_orchestrator import ask; ask('hello')"` works
- No config file required for basic usage
- Default tier assignment works without user configuration

---

## TASK 21 — Implement `orchestrator init` Interactive CLI

**Source**: DX §2.6
**Priority**: P1
**Owner**: TBD

### Description
No guided setup exists. Users manually create config files.

### Acceptance Criteria
- [ ] `orchestrator init` interactive wizard
- [ ] Prompts for: API key, LM Studio availability, daily budget
- [ ] Tests API key validity during setup
- [ ] Writes config file and adds to .gitignore
- [ ] Prints next steps / quickstart example

### Functional Validation
- `orchestrator init` runs interactively and produces valid config
- Generated config works with `orchestrator run`
- API key validation catches invalid keys during setup

---

## TASK 22 — Implement `orchestrator doctor` Diagnostic Command

**Source**: DX §3.1
**Priority**: P1
**Owner**: TBD

### Description
No diagnostic command exists to verify system health.

### Acceptance Criteria
- [ ] `orchestrator doctor` checks: API keys valid, LM Studio reachable (if configured), config file valid, version compatibility
- [ ] Clear pass/fail output for each check
- [ ] Actionable remediation for each failure

### Functional Validation
- `orchestrator doctor` with valid setup reports all checks passing
- `orchestrator doctor` with invalid API key reports specific failure with fix instructions
- `orchestrator doctor` with missing config reports clear error

---

## TASK 23 — Implement `orchestrator explain <task_id>` Command

**Source**: DX §3.2
**Priority**: P2
**Owner**: TBD

### Description
No way to understand why a task escalated or what happened during execution.

### Acceptance Criteria
- [ ] `orchestrator explain <task_id>` shows step-by-step execution history
- [ ] Each attempt shows: tier, model, success/failure, reason, action taken
- [ ] Summary shows: total cost, budget remaining, duration

### Functional Validation
- After running a task that escalates, `orchestrator explain` shows full escalation chain
- Output matches format specified in DX §3.2

---

## TASK 24 — Implement `--dry-run` Mode

**Source**: DX §3.3, Architecture §4.1
**Priority**: P1
**Owner**: TBD

### Description
No way to preview what would happen without calling any LLM.

### Acceptance Criteria
- [ ] `orchestrator run --dry-run "task"` shows: estimated complexity, initial tier, estimated tokens, estimated cost range, budget remaining
- [ ] No LLM API calls made in dry-run mode
- [ ] `orchestrator.estimate_task()` API available programmatically

### Functional Validation
- `orchestrator run --dry-run "Create auth endpoints"` produces cost estimate
- No API calls logged during dry run
- Programmatic `estimate_task()` returns same estimate

---

## TASK 25 — Implement `orchestrator stats` Terminal Dashboard

**Source**: DX §3.5
**Priority**: P2
**Owner**: TBD

### Description
No terminal-based cost summary exists.

### Acceptance Criteria
- [ ] `orchestrator stats` shows: today's spending, tier breakdown, top cost tasks, savings vs reference model
- [ ] `--quiet` flag: only final result and cost
- [ ] `--verbose` flag: full context simplification, circuit breaker state, token counts
- [ ] `--debug` flag: raw prompts/responses (with data exposure warning)

### Functional Validation
- `orchestrator stats` after running tasks shows accurate summary
- Output matches format specified in DX §3.5
- Verbose/debug modes show additional detail

---

## TASK 26 — Add Per-Task Cost Limits

**Source**: Architecture §4.2
**Priority**: P2
**Owner**: TBD

### Description
Budget system only has global limits. No way to say "this single task should not cost more than $1.00".

### Acceptance Criteria
- [ ] `max_cost_per_task` config option
- [ ] `execute_task(max_cost=1.00)` API parameter
- [ ] Task aborted when per-task limit exceeded
- [ ] Per-task limit independent of global budget

### Functional Validation
- Unit test: task with `max_cost=0.01` is aborted before consuming significant budget
- Integration test: per-task limit doesn't affect global budget tracking

---

## TASK 27 — Add Per-Task One-Line Cost Summary

**Source**: DX §2.5
**Priority**: P1
**Owner**: TBD

### Description
No feedback loop after task execution. Developer can't tell if orchestrator is saving money.

### Acceptance Criteria
- [ ] After every task execution, print one-line summary: `[orchestrator] Task completed: L0-Coder, $0.00, saved ~$0.12 vs. GPT-4o`
- [ ] "Saved vs." comparison uses configurable reference model (default: GPT-4o)
- [ ] Savings calculation based on reference model pricing for same tokens

### Functional Validation
- Every task execution produces a one-line summary
- Savings amount is reasonable and correctly calculated
- Reference model is configurable

---

## TASK 28 — Define User-Facing Error Messages

**Source**: DX §2.4
**Priority**: P1
**Owner**: TBD

### Description
Error classification defines categories and actions but user-facing error messages are not specified.

### Acceptance Criteria
- [ ] Every error category has a user-facing message template
- [ ] Every error includes: what happened (plain English), why, what to do
- [ ] Error messages include actionable "What to do" section
- [ ] `StorageError: Connection refused` replaced with detailed message per DX §2.4 example

### Functional Validation
- Unit test: each error category produces a user-facing message with what/why/fix
- Manual test: trigger each error type and verify message is actionable
- No raw exception messages exposed to end user

---

## TASK 29 — Create Migration Guides for Framework Integrations

**Source**: DX §4.3
**Priority**: P2
**Owner**: TBD

### Description
Each framework integration needs a dedicated "Before/After" migration guide with 1-2 line diff.

### Acceptance Criteria
- [ ] CrewAI migration guide: before/after code, 1-2 line diff
- [ ] LangChain migration guide (when implemented)
- [ ] Standalone Python migration guide
- [ ] All examples are copy-pasteable and tested

### Functional Validation
- Each migration guide example runs successfully
- Diff between before/after is ≤2 lines of user code change

---

## TASK 30 — Create Troubleshooting/FAQ Document

**Source**: DX §4.4
**Priority**: P2
**Owner**: TBD

### Description
No troubleshooting or FAQ document exists.

### Acceptance Criteria
- [ ] FAQ covers: constant escalation to L3, cost showing $0.00, using without OpenRouter, streaming support, over-budget behavior
- [ ] Each FAQ entry has: symptom, cause, fix
- [ ] "How do I know it's working?" guide (Architecture §Q7)

### Functional Validation
- FAQ document exists at `docs/TROUBLESHOOTING.md`
- Each FAQ answer has been verified against current codebase behavior

---

## TASK 31 — Create Cookbook/Recipes Document

**Source**: DX §4.5
**Priority**: P2
**Owner**: TBD

### Description
Developers learn by example. No recipes exist.

### Acceptance Criteria
- [ ] Recipe: "Save money on a CrewAI project"
- [ ] Recipe: "Track LangChain agent cost per conversation"
- [ ] Recipe: "Set up team budget with alerts"
- [ ] Recipe: "Use only local models (no cloud)"
- [ ] Recipe: "Optimize for speed, not cost"
- [ ] All recipes are tested and copy-pasteable

### Functional Validation
- Each recipe runs end-to-end without modification
- Recipes are in `examples/` directory with executable code

---

## TASK 32 — Add "How It Works" Simplified Documentation

**Source**: DX §4.2
**Priority**: P1
**Owner**: TBD

### Description
SYSTEM_ARCHITECTURE.md is 800 lines. Need a 20-line "How It Works" for developers, not architects.

### Acceptance Criteria
- [ ] `docs/HOW_IT_WORKS.md` with 5-7 step explanation
- [ ] Written for developers, not architects
- [ ] Links to detailed architecture for those who want it

### Functional Validation
- A developer can understand the system flow in <2 minutes reading HOW_IT_WORKS.md

---

## TASK 33 — Fix tiktoken Initialization Performance

**Source**: Performance §2.2
**Priority**: P1
**Owner**: TBD

### Description
tiktoken encoder initialization is lazy, causing 50-100ms delay on first call per model.

### Acceptance Criteria
- [ ] Pre-initialize encoders at startup for all configured models (eager loading)
- [ ] Ship BPE merge files with package to avoid network download
- [ ] Fast approximation (`len(text) // 4`) used for budget pre-checks
- [ ] `_encoders` capped with LRU cache (max 10 models)

### Functional Validation
- First `estimate_tokens()` call takes <10ms (no network download)
- Unit test: LRU cache evicts oldest encoder when >10 models loaded
- Benchmark: no 50-100ms spike on first call

---

## TASK 34 — Optimize OpenTelemetry Span Creation

**Source**: Performance §2.4
**Priority**: P2
**Owner**: TBD

### Description
OTel span creation and export can add overhead.

### Acceptance Criteria
- [ ] `BatchSpanProcessor` used (not `SimpleSpanProcessor`)
- [ ] 10% sampling rate for production, 100% for development
- [ ] `max_export_batch_size` and `max_queue_size` configured on BatchSpanProcessor
- [ ] Budget remaining gauge updated on timer (1-5s), not every check

### Functional Validation
- Benchmark: OTel overhead <20ms per task with BatchSpanProcessor
- Unit test: span processor configuration is correct
- Memory test: OTel batch queue doesn't grow unboundedly

---

## TASK 35 — Add Performance Benchmark Suite

**Source**: Performance §5.1-5.5
**Priority**: P1
**Owner**: TBD

### Description
No performance benchmarks exist to validate <100ms overhead claim.

### Acceptance Criteria
- [ ] Overhead microbenchmark (mock provider, measure orchestrator code only)
- [ ] Concurrent budget stress test (100 tasks, verify no overrun)
- [ ] Escalation latency benchmark (all tiers fail, measure total time)
- [ ] Memory profile under load (10,000 tasks, peak <200MB)
- [ ] Context simplification performance (500KB input, <10ms)
- [ ] Benchmarks run on every PR, fail if regression >10%

### Functional Validation
- All 5 benchmarks from Performance Review §5.1-5.5 implemented and passing
- CI pipeline runs benchmarks on PR
- Benchmark results published in accessible format

---

## TASK 36 — Add Production Monitoring KPIs

**Source**: Performance §6.1-6.3
**Priority**: P3
**Owner**: TBD

### Description
No monitoring strategy defined for production.

### Acceptance Criteria
- [ ] Key metrics instrumented: overhead p99, db write latency, budget check latency, circuit breaker lock wait, memory RSS, pending spend count, escalation duration, OTel export queue size
- [ ] Alert thresholds configured per Performance §6.1 table
- [ ] Grafana dashboard panels defined (8 panels per §6.2)
- [ ] Profiling strategy documented: py-spy/pyinstrument, benchmark CI, load test on release

### Functional Validation
- All 8 KPIs from Performance §6.1 are emitted as metrics
- Metrics are queryable and match expected format
- Grafana dashboard JSON exported and versioned

---

## TASK 37 — Offload CPU-Bound Work to Thread Pool

**Source**: Performance §4.2
**Priority**: P2
**Owner**: TBD

### Description
Python asyncio is single-threaded. CPU-bound operations (token counting, context simplification, JSON serialization) create head-of-line blocking with 500+ concurrent tasks.

### Acceptance Criteria
- [ ] Token counting offloaded via `asyncio.to_thread()`
- [ ] Context simplification offloaded via `asyncio.to_thread()`
- [ ] JSON serialization offloaded if significant

### Functional Validation
- Benchmark: 500 concurrent tasks don't show head-of-line blocking from CPU work
- Overhead per task remains <100ms at 500 concurrency

---

## TASK 38 — Cap Unbounded In-Memory Structures

**Source**: Performance §4.4
**Priority**: P1
**Owner**: TBD

### Description
Several in-memory structures can grow unboundedly: encoders, circuit breakers, OTel spans, pending spends.

### Acceptance Criteria
- [ ] `_encoders` LRU cache capped at 10 models
- [ ] OTel `BatchSpanProcessor` has `max_export_batch_size` and `max_queue_size`
- [ ] `_pending_spends` capped at 1000 entries, new tasks rejected when full
- [ ] Circuit breaker instances cleaned up for decommissioned providers/models

### Functional Validation
- Memory benchmark: 10,000 tasks with many different models, peak memory <200MB
- Unit test: pending spends rejected when cap reached
- Unit test: OTel queue bounded

---

## TASK 39 — Add Currency Precision with Decimal

**Source**: Architecture §Q9
**Priority**: P0
**Owner**: TBD

### Description
Floating-point arithmetic on costs (e.g., `0.1 + 0.2 != 0.3`). All monetary calculations must use `Decimal`.

### Acceptance Criteria
- [ ] All cost values use `decimal.Decimal` internally
- [ ] All arithmetic on costs uses Decimal
- [ ] Config parsing converts float costs to Decimal
- [ ] API responses format Decimal to fixed precision

### Functional Validation
- Unit test: `0.1 + 0.2 == 0.3` with Decimal cost arithmetic
- Unit test: cost accumulation over 10,000 calls has zero floating-point drift
- All cost-related tests pass with Decimal

---

## TASK 40 — Handle Edge Cases: Pricing Changes, Model Deprecation, Budget Reset

**Source**: Architecture §Q9
**Priority**: P2
**Owner**: TBD

### Description
Multiple edge cases not handled: provider pricing changes mid-session, model deprecation, budget reset during execution, zero-cost model producing harmful output.

### Acceptance Criteria
- [ ] Provider pricing update mechanism documented and implemented
- [ ] Model deprecation detected and warned about at startup
- [ ] Budget reset during execution handled (task uses budget from start time)
- [ ] Zero-cost model output quality check (basic validation)

### Functional Validation
- Unit test: budget reset mid-task doesn't give task double budget
- Unit test: deprecated model produces warning at startup
- Integration test: pricing update during session uses correct prices

---

## TASK 41 — Add CONTRIBUTING.md and Dev Environment Setup

**Source**: DX §Q7
**Priority**: P2
**Owner**: TBD

### Description
No CONTRIBUTING.md, no one-command dev environment setup.

### Acceptance Criteria
- [ ] `CONTRIBUTING.md` with "good first issues" guidance
- [ ] `make dev` or equivalent one-command setup
- [ ] Tests run fast and cover important paths
- [ ] Pre-commit hooks configured

### Functional Validation
- New contributor can set up dev environment in one command
- `make test` runs all tests in <60 seconds
- Pre-commit hooks catch formatting/linting issues

---

## TASK 42 — Create Prompt Templates

**Source**: Project structure observation
**Priority**: P1
**Owner**: TBD

### Description
The `templates/` directory is empty but code references template files (`01-planner.md`, `02-l0-coder.md`, etc.).

### Acceptance Criteria
- [ ] All referenced prompt templates created in `templates/`
- [ ] Templates contain required sections (e.g., `# ROLE:`)
- [ ] Templates validated by TemplateValidator

### Functional Validation
- `orchestrator doctor` passes template validation
- All template references in code resolve to existing files
- TemplateValidator tests pass

---

## TASK 43 — Populate Examples Directory

**Source**: DX §4.5, Project structure observation
**Priority**: P2
**Owner**: TBD

### Description
The `examples/` directory is empty. Developers learn by example.

### Acceptance Criteria
- [ ] Hello world example
- [ ] CrewAI integration example
- [ ] Budget tracking example
- [ ] Custom tier configuration example
- [ ] All examples are executable and tested

### Functional Validation
- `python examples/hello_world.py` runs successfully
- Each example has a corresponding test

---

## TASK 44 — Consider LiteLLM for Provider Abstraction

**Source**: Architecture §4.3, Architecture §Q6
**Priority**: P3
**Owner**: TBD

### Description
LiteLLM already provides unified interface to 100+ LLM providers with cost tracking. Building custom provider adapters is high maintenance.

### Acceptance Criteria
- [ ] Evaluate LiteLLM as optional provider backend
- [ ] If adopted, LiteLLM is an optional dependency (`pip install cost-orchestrator[litellm]`)
- [ ] Custom provider adapters still work for users who don't want LiteLLM
- [ ] Decision documented with pros/cons

### Functional Validation
- If adopted: LiteLLM-backed provider works with all configured models
- Cost tracking through LiteLLM matches custom provider tracking
- Users without LiteLLM can still use custom providers

---

## TASK 45 — Consider Proxy Mode for Zero-Code Integration

**Source**: DX §5.4
**Priority**: P3
**Owner**: TBD

### Description
Instead of wrapping frameworks, offer a local proxy that intercepts OpenAI-compatible API calls. Works with any tool supporting OpenAI API format.

### Acceptance Criteria
- [ ] `orchestrator proxy --port 8080` starts local proxy
- [ ] Proxy intercepts OpenAI-compatible API calls
- [ ] Proxy applies cost optimization and tier routing
- [ ] `OPENAI_API_BASE=http://localhost:8080/v1` works with existing tools
- [ ] Decision: build now or defer to future phase

### Functional Validation
- If adopted: existing OpenAI-compatible tool works with proxy without code changes
- Cost tracking visible for proxied calls
- Proxy adds <50ms latency per call

---

## TASK 46 — Fix Cost Savings Claim Contradictions Across Documents

**Source**: Architecture §C1, §C2, §C3, §C4
**Priority**: P1
**Owner**: TBD

### Description
Multiple contradictions between documents: cost savings (60-80% vs 5-10x), setup time (<2h vs <30m vs <15m), web dashboard phase (Phase 2 vs Future vs Phase 3), SaaS offering (future vs not a SaaS).

### Acceptance Criteria
- [ ] All documents use same cost savings claim (from Task 7 benchmark)
- [ ] All documents use same setup time target
- [ ] All documents agree on web dashboard phase
- [ ] SaaS offering position is consistent (not a SaaS per project principles)

### Functional Validation
- Grep across all docs for savings numbers: only one consistent claim
- Grep for setup time: only one consistent target
- No contradictions between any design documents

---

## TASK 47 — Add pyproject.toml Optional Dependencies for Metrics

**Source**: Project structure observation
**Priority**: P2
**Owner**: TBD

### Description
`pyproject.toml` has optional `metrics` deps (prometheus-client) but no documentation of when to use it.

### Acceptance Criteria
- [ ] `pip install cost-orchestrator[metrics]` documented
- [ ] Metrics module only loaded when optional dep is present
- [ ] Graceful degradation when metrics deps not installed

### Functional Validation
- `pip install cost-orchestrator` works without metrics deps
- `pip install cost-orchestrator[metrics]` enables metrics export
- No ImportError when metrics deps not installed

---

## TASK 48 — Expand Test Coverage for Core Modules

**Source**: Project structure observation
**Priority**: P1
**Owner**: TBD

### Description
Core orchestrator, cost tracker, metrics, retry, and feedback modules lack dedicated unit tests. Only 3 unit test files exist covering validators, tool executor, and file tools.

### Acceptance Criteria
- [ ] Unit tests for `core/orchestrator.py`
- [ ] Unit tests for `core/cost.py`
- [ ] Unit tests for `core/retry.py`
- [ ] Unit tests for `core/metrics.py`
- [ ] Unit tests for `core/feedback.py`
- [ ] Unit tests for `core/parallel.py`
- [ ] Coverage target: ≥80%

### Functional Validation
- `pytest --cov=src --cov-report=term-missing` shows ≥80% coverage
- All new tests pass
- No regressions in existing tests

---

## Summary by Priority

| Priority | Count | Key Themes |
|----------|-------|------------|
| P0 | 7 | Budget safety, code correctness, first-run experience |
| P1 | 18 | Core functionality, DX blockers, testing, docs |
| P2 | 15 | Quality of life, scalability prep, edge cases |
| P3 | 5 | Future-proofing, optional features |
| **Total** | **45** | |

## Suggested Execution Order

### Wave 1 — Foundation (Weeks 1-2)
Tasks: 17, 18, 39, 1, 19, 20, 42
*Fix bugs, resolve identity crisis, establish quickstart*

### Wave 2 — Budget & Safety (Weeks 3-4)
Tasks: 2, 5, 33, 38, 3, 4, 9
*Budget race condition, failure mode, performance, circuit breaker, timeout*

### Wave 3 — Developer Experience (Weeks 5-6)
Tasks: 21, 22, 24, 27, 28, 32, 30, 16
*Interactive setup, diagnostics, dry-run, cost feedback, errors, simplified docs, tier/role separation*

### Wave 4 — Testing & Benchmarks (Weeks 7-8)
Tasks: 48, 35, 7, 46, 6
*Test coverage, benchmarks, standardized claims, config migration*

### Wave 5 — Advanced Features (Weeks 9-10)
Tasks: 10, 11, 12, 13, 14, 15, 23, 25, 26, 29, 31, 34, 37, 40
*Model capabilities, streaming, shutdown, versioning, rate limiting, prompt formats, explain, stats, per-task limits, migration guides, cookbook, OTel, threading, edge cases*

### Wave 6 — Future / Optional (As resources allow)
Tasks: 8, 36, 41, 43, 44, 45, 47
*Framework integrations, monitoring, contributing, examples, LiteLLM, proxy mode, optional deps*
