"""LangGraph prototype: intra-agent handoff + review loop (wi-LG-HANDOFF).

This module re-expresses the retry/escalate loop inside
``LLMOrchestrator.execute_with_judge`` (src/core/orchestrator.py) as a
LangGraph StateGraph. It is a PROTOTYPE for evaluation, not a production
refactor: nothing here is wired into the CLI or the production path.

Design rule (per the task spec): the graph replaces LOOP CONTROL ONLY
(retry counting, verdict routing, tier escalation, checkpoint/resume).
The model routing, tier execution, judge criteria, and budgets stay in
the existing code, which this module IMPORTS and calls:

  - tier execution: LLMOrchestrator._execute_opencode_tier /
    _execute_pi_tier / call_llm_with_retry (same routing the real loop
    uses: OpenCode first, PI fallback, raw LLM last)
  - judge: Judge(model=...).evaluate(...) from src.core.judge, which
    internally selects criteria from src.core.judge_criteria
  - verifier: RuntimeVerifier from src.core.verifier

Testability: each node calls a seam function. The defaults call the
real orchestrator methods above; tests inject small scripted seams
(repo convention: injectable seams, see AGENTS.md section 2). Tier
execution requires pi/opencode CLIs and live model infra, so committed
tests exercise routing + durable resume with scripted seams, while a
live run is one default-wiring call away (see run_handoff).

Graph shape:

    START -> code -> judge -> route_after_judge
                               accepted      -> verifier -> END
                               rejected, retries left -> code
                               rejected, retries out  -> escalate -> code/END

Checkpointing: every node completion is persisted via SqliteSaver, so
a crash after `code` returns resumes at `judge` instead of restarting
the task (the hand-rolled loop only checkpoints after a full tier
verdict, via _write_checkpoint/_load_checkpoint).
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

# Tier chain, same order execute_with_judge uses when tiers is not given.
TIER_ORDER = ["l0-coder", "l1-coder", "l2-coder", "principal"]

# Default retries per tier, matching MAX_RETRIES in orchestrator.py.
DEFAULT_MAX_RETRIES = 3


class HandoffState(TypedDict, total=False):
    """Graph state. The first ten fields are the task-mandated schema."""

    task_id: str
    task_spec: str
    task_type: str
    tier: str
    attempt: int
    output: str
    verdict: str  # "accepted" | "rejected"
    feedback: str  # Judge critique, fed back to the coder on reject
    escalation_path: list[str]
    success: bool
    # Prototype extras (routing inputs / bookkeeping, not in the mandate):
    tiers: list[str]
    max_retries: int
    judge_model: str
    project_root: str
    verify_errors: list[str]


# --- Seam types -----------------------------------------------------------------
# tier_fn(state) -> (output: str, success: bool)
# judge_fn(state) -> (accepted: bool, critique: str, score: float)
# verifier_fn(state) -> (passed: bool, errors: list[str])

TierFn = Callable[[HandoffState], "tuple[str, bool]"]
JudgeFn = Callable[[HandoffState], "tuple[bool, str, float]"]
VerifierFn = Callable[[HandoffState], "tuple[bool, list[str]]"]


# --- Default seams: call the REAL orchestrator code ------------------------------

_orchestrator_singleton: Any = None


def _default_orchestrator() -> Any:
    """Lazily construct the real orchestrator (import cost paid once)."""
    global _orchestrator_singleton
    if _orchestrator_singleton is None:
        from src.core.orchestrator import LLMOrchestrator

        _orchestrator_singleton = LLMOrchestrator()
    return _orchestrator_singleton


def default_tier_fn(state: HandoffState) -> tuple[str, bool]:
    """Execute one coder attempt via the shared tier-attempt helper.

    All backend selection lives in
    LLMOrchestrator._execute_tier_attempt (OpenCode -> PI -> raw LLM,
    the same routing execute_with_judge inlines). This wrapper only
    builds the prompt (task spec + judge feedback on retry) and the
    system prompt, then delegates -- no routing logic is duplicated
    here anymore.
    """
    orch = _default_orchestrator()
    tier = state["tier"]
    task_spec = state.get("task_spec", "")
    prompt = task_spec
    if state.get("attempt", 0) > 0 and state.get("feedback"):
        prompt = (
            task_spec
            + "\n\n## Previous attempt was rejected by the Judge.\n"
            + "Fix the issue and try again. Critique:\n"
            + state["feedback"]
        )
    system_prompt = orch._get_agent_system_prompt(state.get("task_type", "code"))
    result = orch._execute_tier_attempt(
        tier,
        prompt,
        system_prompt,
        retry_num=state.get("attempt", 0) + 1,
        project_root=state.get("project_root") or None,
        accumulated_files=set(),
    )
    return str(result.get("output", "")), bool(result.get("success"))


def default_judge_fn(state: HandoffState) -> tuple[bool, str, float]:
    """Evaluate the output with the real Judge call path.

    Judge(model).evaluate() internally picks criteria from
    judge_criteria via detect_task_type -- the same path
    execute_with_judge uses. A judge exception degrades to a
    rejection, mirroring the real loop.
    """
    from src.core.judge import Judge, Verdict

    task_text = state.get("task_spec", state.get("task_id", ""))
    if state.get("task_type") == "plan":
        task_text = f"[PLANNING TASK] Decompose into subtasks: {task_text}"
    try:
        judge = Judge(model=state.get("judge_model", "Judge"))
        verdict: Verdict = judge.evaluate(
            task=str(task_text), output=state.get("output", "")
        )
        return bool(verdict.accepted), verdict.critique, float(verdict.score)
    except Exception as exc:  # judge unavailable -> rejection (real loop behavior)
        return False, f"Judge unavailable: {exc}", 0.0


def default_verifier_fn(state: HandoffState) -> tuple[bool, list[str]]:
    """Run the real RuntimeVerifier on the produced files."""
    from src.core.verifier import RuntimeVerifier

    verifier = RuntimeVerifier(
        project_root=state.get("project_root") or ".",
    )
    result = verifier.verify()
    if result.passed:
        return True, []
    errors = list(getattr(result, "errors", []) or [])
    if result.exit_code:
        errors.append(f"verification exited with code {result.exit_code}")
    return False, errors


# --- Routing (pure, unit-testable -- the part Stephen called fragile) ----------

def route_after_code(state: HandoffState) -> str:
    """After coder execution: judge the output, or escalate if the coder
    produced nothing (mirrors the real loop, where an unrecoverable
    backend failure escalates without consuming a judge call)."""
    if state.get("output"):
        return "judge"
    return "escalate"


def route_after_judge(state: HandoffState) -> str:
    """Decide the next node after a judge verdict.

    Returns "verifier" on accept, "code" if retries remain on this
    tier, otherwise "escalate" (next tier or terminal failure).
    """
    if state.get("verdict") == "accepted":
        return "verifier"
    if state.get("attempt", 0) < state.get("max_retries", DEFAULT_MAX_RETRIES):
        return "code"
    return "escalate"


def route_after_verifier(state: HandoffState) -> str:
    """Decide the next node after runtime verification.

    Passed -> END (success already set by the verifier node).
    Failed -> same retry/escalate logic as a judge rejection, with the
    verifier's errors as feedback (mirrors the real Loop-2 behavior).
    """
    if state.get("verdict") == "accepted":
        return "__end__"
    if state.get("attempt", 0) < state.get("max_retries", DEFAULT_MAX_RETRIES):
        return "code"
    return "escalate"


def route_after_escalate(state: HandoffState) -> str:
    """After escalation: run the next tier, or END if tiers ran out.

    The escalate node has already advanced state["tier"] (or set
    success=False when no tier remains), so this is a pure check.
    """
    if not state.get("success", True):
        return "__end__"
    return "code"


# --- Nodes (thin wrappers over the seams) ---------------------------------------

def make_code_node(tier_fn: TierFn):
    def code_node(state: HandoffState) -> dict:
        output, produced = tier_fn(state)
        return {
            "output": output,
            "attempt": state.get("attempt", 0) + 1,
            "verdict": "",
            # A coder failure with no output escalates immediately,
            # matching the real loop (unrecoverable failures do not
            # consume retries -- they escalate).
            "success": produced,
        }

    return code_node


def make_judge_node(judge_fn: JudgeFn):
    def judge_node(state: HandoffState) -> dict:
        accepted, critique, _score = judge_fn(state)
        update: dict[str, Any] = {
            "verdict": "accepted" if accepted else "rejected",
        }
        if accepted:
            update["feedback"] = ""
            update["success"] = True
        else:
            update["feedback"] = critique
        return update

    return judge_node


def make_verifier_node(verifier_fn: VerifierFn):
    def verifier_node(state: HandoffState) -> dict:
        passed, errors = verifier_fn(state)
        if passed:
            return {"verdict": "accepted", "success": True}
        feedback = "Runtime verification failed:\n" + "\n".join(errors[:20])
        return {
            "verdict": "rejected",
            "feedback": feedback,
            "verify_errors": errors,
            "success": False,
        }

    return verifier_node


def escalate_node(state: HandoffState) -> dict:
    """Advance to the next tier (attempt resets) or fail terminally."""
    path = list(state.get("escalation_path", []))
    if state.get("tier"):
        path.append(state["tier"])
    tiers = state.get("tiers") or TIER_ORDER
    current = state.get("tier")
    idx = tiers.index(current) if current in tiers else len(tiers) - 1
    if idx + 1 < len(tiers):
        return {"escalation_path": path, "tier": tiers[idx + 1], "attempt": 0,
                "success": True}
    # No tier remains -- terminal failure.
    return {"escalation_path": path, "success": False}


# --- Graph assembly --------------------------------------------------------------

def build_graph(checkpointer, *, tier_fn=None, judge_fn=None, verifier_fn=None):
    """Compile the handoff StateGraph with the given checkpoint saver.

    Nodes with no seam supplied use the real orchestrator defaults.
    Returns the compiled graph.
    """
    from langgraph.graph import END, START, StateGraph

    tier_fn = tier_fn or default_tier_fn
    judge_fn = judge_fn or default_judge_fn
    verifier_fn = verifier_fn or default_verifier_fn

    graph = StateGraph(HandoffState)
    graph.add_node("code", make_code_node(tier_fn))
    graph.add_node("judge", make_judge_node(judge_fn))
    graph.add_node("verifier", make_verifier_node(verifier_fn))
    graph.add_node("escalate", escalate_node)

    graph.add_edge(START, "code")
    graph.add_conditional_edges(
        "code",
        route_after_code,
        {"judge": "judge", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "judge",
        route_after_judge,
        {"verifier": "verifier", "code": "code", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"__end__": END, "code": "code", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "escalate",
        route_after_escalate,
        {"__end__": END, "code": "code"},
    )
    return graph.compile(checkpointer=checkpointer)


def initial_state(
    task_id: str,
    task_spec: str,
    *,
    tiers: list[str] | None = None,
    task_type: str = "code",
    max_retries: int = DEFAULT_MAX_RETRIES,
    judge_model: str = "Judge",
    project_root: str = "",
) -> HandoffState:
    """Fresh handoff state for a new run (thread)."""
    tier_list = list(tiers) if tiers else list(TIER_ORDER)
    return {
        "task_id": task_id,
        "task_spec": task_spec,
        "task_type": task_type,
        "tier": tier_list[0],
        "attempt": 0,
        "output": "",
        "verdict": "",
        "feedback": "",
        "escalation_path": [],
        "success": False,
        "tiers": tier_list,
        "max_retries": max_retries,
        "judge_model": judge_model,
        "project_root": project_root,
        "verify_errors": [],
    }


def run_handoff(
    checkpoint_path: str,
    thread_id: str,
    state: HandoffState,
    *,
    tier_fn=None,
    judge_fn=None,
    verifier_fn=None,
) -> dict:
    """Run the graph to completion against a persistent SqliteSaver.

    The graph object is rebuilt per call; durable state lives in the
    SQLite file, so a later call with the same thread_id resumes from
    the last completed node instead of restarting the task.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_graph(
            checkpointer, tier_fn=tier_fn, judge_fn=judge_fn,
            verifier_fn=verifier_fn,
        )
        return graph.invoke(state, {"configurable": {"thread_id": thread_id}})
