"""Unit tests for the LangGraph handoff prototype (wi-LG-HANDOFF).

Covers:
  - Pure routing functions (route_after_code/judge/verifier/escalate)
  - End-to-end graph run with scripted tier/judge seams
    (reject-once-then-accept; full-tier escalation to failure)
  - DURABILITY: crash after `code`, resume from SqliteSaver checkpoint
    at `judge` without re-running `code`

The seams are scripted because tier execution requires pi/opencode
CLIs and live model infra. The prototype's DEFAULT seams call the real
orchestrator methods; what is proven here is loop control + durable
resume, which is the prototype's claim.
"""

import tempfile
import unittest
from pathlib import Path

from src.prototype.langgraph_handoff import (
    build_graph,
    initial_state,
    route_after_code,
    route_after_escalate,
    route_after_judge,
    route_after_verifier,
)


class SimulatedCrash(Exception):
    """Stands in for a process death (SIGKILL) between nodes."""


def make_state(**overrides):
    state = initial_state(
        task_id="t1", task_spec="Write is_even(n) in solution.py",
        tiers=["l0-coder", "l1-coder"], max_retries=3,
    )
    state.update(overrides)
    return state


class TestRouting(unittest.TestCase):
    def test_route_after_code_empty_output_escalates(self):
        self.assertEqual(route_after_code(make_state(output="")), "escalate")

    def test_route_after_code_with_output_goes_to_judge(self):
        self.assertEqual(route_after_code(make_state(output="def x: ...")), "judge")

    def test_route_after_judge_accepted_goes_to_verifier(self):
        self.assertEqual(route_after_judge(make_state(verdict="accepted")), "verifier")

    def test_route_after_judge_rejected_with_retries_goes_back_to_code(self):
        self.assertEqual(
            route_after_judge(make_state(verdict="rejected", attempt=1, max_retries=3)),
            "code",
        )

    def test_route_after_judge_rejected_exhausted_escalates(self):
        self.assertEqual(
            route_after_judge(make_state(verdict="rejected", attempt=3, max_retries=3)),
            "escalate",
        )

    def test_route_after_verifier_passed_ends(self):
        self.assertEqual(route_after_verifier(make_state(verdict="accepted")), "__end__")

    def test_route_after_verifier_failed_retries(self):
        self.assertEqual(
            route_after_verifier(make_state(verdict="rejected", attempt=1, max_retries=3)),
            "code",
        )

    def test_route_after_escalate_more_tiers_goes_to_code(self):
        self.assertEqual(route_after_escalate(make_state(success=True)), "code")

    def test_route_after_escalate_no_tiers_ends(self):
        self.assertEqual(route_after_escalate(make_state(success=False)), "__end__")


class TestGraphEndToEnd(unittest.TestCase):
    def test_reject_once_then_accept(self):
        calls = {"code": 0, "judge": 0}

        def tier_fn(state):
            calls["code"] += 1
            return (f"output attempt {calls['code']}", True)

        def judge_fn(state):
            calls["judge"] += 1
            if calls["judge"] == 1:
                return (False, "missing docstring", 0.4)
            return (True, "good", 0.9)

        def verifier_fn(state):
            return (True, [])

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "handoff.sqlite")
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=judge_fn, verifier_fn=verifier_fn,
                )
                result = graph.invoke(
                    make_state(), {"configurable": {"thread_id": "t1"}}
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["verdict"], "accepted")
        self.assertEqual(calls["code"], 2)  # one reject -> one retry
        self.assertEqual(calls["judge"], 2)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["output"], "output attempt 2")

    def test_escalates_through_tiers_to_failure(self):
        def tier_fn(state):
            return ("bad output", True)

        def judge_fn(state):
            return (False, "always wrong", 0.1)

        def verifier_fn(state):  # never reached on reject path
            raise AssertionError("verifier must not run after rejection")

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "handoff.sqlite")
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=judge_fn, verifier_fn=verifier_fn,
                )
                result = graph.invoke(
                    make_state(), {"configurable": {"thread_id": "t1"}}
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["escalation_path"], ["l0-coder", "l1-coder"])
        self.assertEqual(result["final_tier"] if "final_tier" in result else result["tier"], "l1-coder")

    def test_empty_coder_output_escalates_without_judge(self):
        calls = {"judge": 0}

        def tier_fn(state):
            return ("", False)  # coder produced nothing

        def judge_fn(state):
            calls["judge"] += 1
            return (True, "ok", 1.0)

        def verifier_fn(state):
            return (True, [])

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "handoff.sqlite")
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=judge_fn, verifier_fn=verifier_fn,
                )
                result = graph.invoke(
                    make_state(), {"configurable": {"thread_id": "t1"}}
                )

        self.assertEqual(calls["judge"], 0)  # judge never consulted
        self.assertFalse(result["success"])  # all tiers produced nothing

    def test_verifier_failure_loops_back_to_code(self):
        calls = {"code": 0, "verify": 0}

        def tier_fn(state):
            calls["code"] += 1
            return ("output", True)

        def judge_fn(state):
            return (True, "ok", 0.9)

        def verifier_fn(state):
            calls["verify"] += 1
            if calls["verify"] == 1:
                return (False, ["pytest: test_even failed"])
            return (True, [])

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "handoff.sqlite")
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=judge_fn, verifier_fn=verifier_fn,
                )
                result = graph.invoke(
                    make_state(), {"configurable": {"thread_id": "t1"}}
                )

        self.assertTrue(result["success"])
        self.assertEqual(calls["code"], 2)  # verifier fail -> coder retry
        self.assertEqual(calls["verify"], 2)


class TestDurabilityResume(unittest.TestCase):
    def test_crash_after_code_resumes_at_judge_without_rerunning_code(self):
        """The A/B deliverable.

        First run: `code` completes (checkpointed), then the judge seam
        raises SimulatedCrash -- modelling a process death between the
        code and judge nodes. Second run (same thread_id): the graph
        resumes at `judge` from the SqliteSaver checkpoint. `code` must
        NOT re-run (call count stays 1) and the run completes.
        """
        calls = {"code": 0, "judge": 0}

        def tier_fn(state):
            calls["code"] += 1
            return ("def is_even(n): return n % 2 == 0", True)

        def crashing_judge_fn(state):
            calls["judge"] += 1
            if calls["judge"] == 1:
                raise SimulatedCrash("process died before judge body ran")
            return (True, "correct", 0.95)

        def verifier_fn(state):
            return (True, [])

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "handoff.sqlite")
            from langgraph.checkpoint.sqlite import SqliteSaver

            # ---- Run 1: crash after code, before judge ----
            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=crashing_judge_fn,
                    verifier_fn=verifier_fn,
                )
                with self.assertRaises(SimulatedCrash):
                    graph.invoke(
                        make_state(), {"configurable": {"thread_id": "durable-1"}}
                    )
            self.assertEqual(calls["code"], 1)

            # ---- Run 2: resume from checkpoint ----
            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(
                    checkpointer,
                    tier_fn=tier_fn, judge_fn=crashing_judge_fn,
                    verifier_fn=verifier_fn,
                )
                result = graph.invoke(
                    None, {"configurable": {"thread_id": "durable-1"}}
                )

        # Code ran exactly ONCE across both processes; judge ran twice
        # (crashed attempt + resumed attempt); run completed.
        self.assertEqual(calls["code"], 1)
        self.assertEqual(calls["judge"], 2)
        self.assertTrue(result["success"])
        self.assertEqual(result["verdict"], "accepted")
        self.assertEqual(result["output"], "def is_even(n): return n % 2 == 0")


class TestStateSchema(unittest.TestCase):
    def test_initial_state_has_mandated_fields(self):
        state = initial_state(task_id="x", task_spec="spec")
        for field in (
            "task_id", "task_spec", "task_type", "tier", "attempt",
            "output", "verdict", "feedback", "escalation_path", "success",
        ):
            self.assertIn(field, state)
        self.assertEqual(state["task_type"], "code")
        self.assertEqual(state["tier"], "l0-coder")
        self.assertEqual(state["attempt"], 0)


if __name__ == "__main__":
    unittest.main()
