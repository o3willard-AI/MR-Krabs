"""Production handoff graph: tier retry/escalate loop as a LangGraph graph.

Promoted from the prototype in src/prototype/langgraph_handoff.py
(wi-LG-HANDOFF, wi-LG-REFACTOR-2). The graph replaces ONLY the
retry/escalate/review loop control inside
LLMOrchestrator.execute_with_judge. Every node is a thin closure over
the orchestrator's existing methods (_execute_tier_attempt,
_system_prompt_for_backend, Judge.evaluate, RuntimeVerifier) plus the
same observability side-effects the hand-rolled loop performs
(monitor records, cost tracking, JSON checkpoint, integration audit).

Durability: the graph is compiled with a SqliteSaver, one thread per
(task_id, tier). Every node completion is checkpointed, so a crash
between the coder and judge nodes resumes at judge instead of
restarting the tier attempt. The hand-rolled JSON checkpoint
(_write_checkpoint/_load_checkpoint) is still written per verdict for
backward compatibility.

State discipline: everything in TierGraphState is JSON-serializable
(verdict is stored as a dict; the outer loop reconstructs Verdict).
Mutable per-call context (context dict, tier_config, monitor, cost
tracker) is captured by the node closures, not stored in state.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class TierGraphState(TypedDict, total=False):
    """State for one tier's retry loop (see orchestrator._run_tier_graph)."""

    # Identity / routing inputs
    task_id: str
    task_spec: str  # evolves: audit/verify inject fix prompts here
    task_type: str
    tier: str
    judge_model: str
    project_root: str
    verify_enabled: bool
    qa_enabled: bool

    # Counters (mirrors the hand-rolled loop's retry_num / retries_per_tier
    # / attempts_total exactly; see node increment comments)
    attempt: int  # retry_num equivalent (1-based slots consumed)
    retries: int  # retries_per_tier equivalent
    attempts_total: int  # global across tiers
    max_retries: int  # may bump once on a provisional verdict

    # Coder outcome of the latest attempt
    coder_outcome: str  # produced|recoverable|raw_failure|unrecoverable|fail_up
    coder_output: str
    coder_written_paths: list[str]
    coder_duration: float
    coder_exit_code: int
    coder_partial: bool
    prompt_chars: int  # for TokenCount cost parity

    # Review state
    feedback: str
    verdict: dict | None  # {accepted, provisional, score, critique, checks_passed, checks_failed}
    tool_result: dict
    files: dict
    accumulated_files: dict
    best_output: dict
    provisional_bonus_used: bool

    # Terminal flags consumed by the outer loop
    terminal: str  # ""|accepted|verify_failed|qa_failed|exhausted|fail_up|raw_failure|unrecoverable
    verifier_outcome: str  # passed|retry|exhausted|skipped
    verify_result: dict | None
    qa_result: dict | None
    fail_up_aborted: bool


NodeFn = Callable[[TierGraphState], dict]


# --- Routers (pure functions of state) -------------------------------------------

def route_after_code(state: TierGraphState) -> str:
    """Coder outcome -> next node.

    produced -> judge; recoverable backend failure -> retry while slots
    remain else end of tier; raw LLM failure / unrecoverable backend /
    fail-up -> end of tier (mirrors the hand-rolled loop's break paths).
    """
    outcome = state.get("coder_outcome", "")
    if outcome == "produced":
        return "judge"
    if outcome == "recoverable":
        return "code" if state.get("attempt", 0) <= state.get("max_retries", 0) else "__end__"
    return "__end__"


def route_after_judge(state: TierGraphState) -> str:
    """Verdict -> next node (accepted -> verifier/qa, else retry/end)."""
    verdict = state.get("verdict") or {}
    if verdict.get("accepted"):
        if state.get("verify_enabled"):
            return "verifier"
        if state.get("qa_enabled"):
            return "qa"
        return "__end__"
    return "code" if state.get("attempt", 0) <= state.get("max_retries", 0) else "__end__"


def route_after_verifier(state: TierGraphState) -> str:
    """Verifier outcome -> code (retry), qa (passed+qa on), or END."""
    outcome = state.get("verifier_outcome", "")
    if outcome == "retry":
        return "code"
    if outcome == "exhausted":
        return "__end__"
    if state.get("qa_enabled"):
        return "qa"
    return "__end__"


def route_after_qa(state: TierGraphState) -> str:
    """QA is terminal either way (fail -> qa_failed flag, pass -> accept)."""
    return "__end__"


# --- Assembler --------------------------------------------------------------------

def build_tier_graph(
    checkpointer,
    code_node: NodeFn,
    judge_node: NodeFn,
    verifier_node: NodeFn | None = None,
    qa_node: NodeFn | None = None,
):
    """Assemble the per-tier graph skeleton.

    START -> code -> judge -> verifier -> qa -> END, with retry loops
    code/judge/verifier -> code. Nodes are callables taking/returning
    state dicts; conditional routers above decide the edges.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(TierGraphState)
    graph.add_node("code", code_node)
    graph.add_node("judge", judge_node)
    if verifier_node is not None:
        graph.add_node("verifier", verifier_node)
    if qa_node is not None:
        graph.add_node("qa", qa_node)

    graph.add_edge(START, "code")
    graph.add_conditional_edges(
        "code", route_after_code, {"judge": "judge", "__end__": END}
    )
    judge_routes = {"code": "code", "__end__": END}
    if verifier_node is not None:
        judge_routes["verifier"] = "verifier"
    if qa_node is not None:
        judge_routes["qa"] = "qa"
    graph.add_conditional_edges("judge", route_after_judge, judge_routes)
    if verifier_node is not None:
        graph.add_conditional_edges(
            "verifier", route_after_verifier,
            {"code": "code", "__end__": END, "qa": "qa"} if qa_node is not None
            else {"code": "code", "__end__": END},
        )
    if qa_node is not None:
        graph.add_conditional_edges("qa", route_after_qa, {"__end__": END})
    return graph.compile(checkpointer=checkpointer)


def initial_tier_state(
    task_id: str,
    task_spec: str,
    tier: str,
    *,
    task_type: str = "code",
    judge_model: str = "Judge",
    project_root: str = "",
    max_retries: int = 3,
    verify_enabled: bool = False,
    qa_enabled: bool = False,
    attempts_total: int = 0,
    accumulated_files: dict | None = None,
    best_output: dict | None = None,
) -> TierGraphState:
    """Fresh per-tier graph state (attempt mirrors retry_num, 1-based)."""
    return {
        "task_id": task_id,
        "task_spec": task_spec,
        "task_type": task_type,
        "tier": tier,
        "judge_model": judge_model,
        "project_root": project_root,
        "verify_enabled": verify_enabled,
        "qa_enabled": qa_enabled,
        "attempt": 1,
        "retries": 0,
        "attempts_total": attempts_total,
        "max_retries": max_retries,
        "coder_outcome": "",
        "coder_output": "",
        "coder_written_paths": [],
        "coder_duration": 0.0,
        "coder_exit_code": 0,
        "coder_partial": False,
        "prompt_chars": 0,
        "feedback": "",
        "verdict": None,
        "tool_result": {},
        "files": {},
        "accumulated_files": dict(accumulated_files or {}),
        "best_output": dict(best_output or {}),
        "provisional_bonus_used": False,
        "terminal": "",
        "verifier_outcome": "",
        "verify_result": None,
        "qa_result": None,
        "fail_up_aborted": False,
    }


def verdict_dict(v: Any) -> dict:
    """Serialize a Judge Verdict into JSON-safe state form."""
    return {
        "accepted": bool(v.accepted),
        "provisional": bool(v.provisional),
        "score": float(v.score),
        "critique": str(v.critique),
        "checks_passed": list(v.checks_passed),
        "checks_failed": list(v.checks_failed),
    }
