# LangGraph Handoff Prototype — evaluation (wi-LG-HANDOFF)

Standalone prototype: `src/prototype/langgraph_handoff.py`.
Tests: `tests/unit/test_langgraph_handoff.py` (15 tests, incl. durability).

## What was built

A LangGraph `StateGraph` re-expressing the retry/escalate loop inside
`LLMOrchestrator.execute_with_judge` (orchestrator.py, ~line 1909):

```
START -> code -> judge -> route_after_judge
                          accepted            -> verifier -> END
                          rejected, retries   -> code
                          rejected, exhausted -> escalate -> code/END
```

* State: the mandated TypedDict (task_id, task_spec, task_type, tier,
  attempt, output, verdict, feedback, escalation_path, success) plus
  routing inputs (tiers, max_retries, judge_model, project_root).
* Nodes are thin wrappers over seams. Defaults call the REAL code:
  tier execution routes OpenCode -> PI -> raw LLM exactly like
  execute_with_judge; the judge node calls Judge(model).evaluate(),
  which selects criteria from judge_criteria; the verifier node calls
  RuntimeVerifier. Tests inject scripted seams (repo injectable-seam
  convention) because tier execution needs pi/opencode CLIs and live
  model infra that do not exist in the unit-test environment. A live
  run is one default-wiring call away (run_handoff with no seams).

## 1. Does the graph make verdict routing MORE explicit?

Yes. Before (execute_with_judge): verdict handling is string/state
logic interleaved with ~300 lines of audit, monitor, cost, checkpoint,
verify, and fallback bookkeeping inside one 2,948-line file; the
retry/escalate decision is `while retry_num <= max_retries` plus
nested `break`/`continue` across backend-specific branches.

After: the decision is three pure functions -- `route_after_code`,
`route_after_judge`, `route_after_verifier`, `route_after_escalate` --
each unit-testable in isolation (9 routing tests). Escalation is an
explicit node, not a loop-exit side effect. A reader can answer
"what happens on reject?" by reading one 10-line function instead of
tracing the while loop.

Honest caveat: the graph does NOT capture the full real loop. Circuit
breaker gates, fail-up/fail-now checks, pipeline monitor records,
integration audit, context compression, feedback history, multi-pass
splitting, and prompt-flow logging all live outside the prototype's
scope. Adopting the graph for this slice would mean deciding where
each of those hooks onto nodes -- reasonable (they are per-attempt or
per-verdict hooks), but real work the prototype does not do.

## 2. Does durable resume actually work?

Yes, and this is the prototype's strongest result. The durability
test crashes AFTER `code` returns and BEFORE the judge body runs
(a seam raises SimulatedCrash, modelling SIGKILL between nodes).
Resume with the same thread_id continues at `judge` from the
SqliteSaver checkpoint; `code` is NOT re-run (call count stays 1
across both runs) and the run completes to a verdict.

Versus the hand-rolled checkpoint: `_write_checkpoint` fires once per
TIER verdict and stores a coarse JSON snapshot (escalation path,
counters, best output, cost). It cannot resume mid-tier: a crash
between coder output and judge verdict restarts the tier from
attempt 1 (and, per the code comments, previously even burned retry
slots on crashes). The graph checkpoints after EVERY node, so resume
granularity is per-node, and the state is the full typed schema
rather than a best-effort subset. The SqliteSaver is also durable
across processes by construction, which the JSON snapshot achieves
only if a tier completed.

One subtlety worth knowing: LangGraph checkpoints are written when a
node completes. If the process dies INSIDE `code` (mid-LLM-call), the
checkpoint still points at START-of-code and that node re-runs --
same as any framework; the win is specifically for deaths between
nodes, which is the common crash shape (OOM killer, watchdog,
deploys) and exactly what the test simulates.

## 3. What was lost / felt worse

* **State plumbing is verbose.** The JSON checkpoint schema is
  discoverable; the TypedDict + node-return-dict dance spreads one
  logical transition across three places (node return, router,
  state defaults). For a 4-node graph this is fine; it is why the
  task scoped LangGraph to this slice only.
* **The wrappers are real indirection.** default_tier_fn re-implements
  the OpenCode/PI/raw-LLM routing selection (~15 lines) rather than
  calling one existing method, because execute_with_judge inlines that
  routing. A production adoption should extract that selection into a
  shared helper first.
* **Attempt counting differs subtly.** The prototype counts a coder
  attempt when output is produced; the real loop also counts
  recoverable hard failures per backend. Coder-failure handling here
  is simplified to "empty output escalates immediately" (matching the
  real unrecoverable-failure policy, not the recoverable-retry one).
* **Framework lock-in is real but small.** Pinning langgraph 1.2.x
  means tracking its release cadence for a control-flow library; the
  checkpoint format is versioned by the framework, not by us.
* **Live-run evidence is missing.** No API keys / pi / opencode CLIs
  exist in the test environment, so the prototype was never run
  against a real model here. The routing + resume claims are proven;
  end-to-end LLM behavior is asserted by construction (same functions)
  but not demonstrated.

## Verdict

For THIS slice, LangGraph is worth adopting. The two things Stephen
flagged as fragile -- verdict routing buried in a 2,948-line file and
crash-restarts-the-whole-task -- are exactly the two things the graph
fixes structurally: routing becomes three pure testable functions,
and resume becomes per-node durable instead of per-tier best-effort.
The cost is one small dependency (langgraph + its official
checkpoint-sqlite package) and some state plumbing that stays
contained because the scope is deliberately narrow.

Recommendation: adopt for handoff/review loop control only, after
extracting the backend-selection helper so default_tier_fn stops
duplicating routing logic, and after one live run against a real
model to close the evidence gap noted above.
