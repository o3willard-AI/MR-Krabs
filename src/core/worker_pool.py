"""Worker pool for the MR-Krabs orchestrator.

Dispatches tasks to independent LLMOrchestrator instances via a
thread pool, gated by an AdmissionGate for backpressure control.

Each task gets its own orchestrator instance — full isolation,
no shared mutable state (except optionally the circuit breaker
registry). Failed tasks don't affect concurrent ones.

Usage:
    gate = AdmissionGate(max_concurrent=3)
    pool = WorkerPool(gate=gate)

    tasks = [TaskSpec(task_id="fib", context={"task_spec": "..."})]
    futures = pool.dispatch(tasks)     # non-blocking
    results = pool.run_all(tasks)      # blocking
"""

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from src.core.admission import AdmissionGate, AdmissionTicket
from src.core.orchestrator import LLMOrchestrator


@dataclass
class TaskSpec:
    """Specification for a task to be dispatched to the orchestrator."""

    task_id: str
    context: dict
    tiers: Optional[list[str]] = None
    max_retries_per_tier: int = 3
    judge_model: str = "Judge"
    timeout_seconds: float = 300.0

    def to_kwargs(self) -> dict:
        """Convert to kwargs for execute_with_judge()."""
        kwargs = {
            "task_id": self.task_id,
            "context": self.context,
            "max_retries_per_tier": self.max_retries_per_tier,
            "judge_model": self.judge_model,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.tiers is not None:
            kwargs["tiers"] = self.tiers
        return kwargs


class WorkerPool:
    """Dispatches tasks to isolated LLMOrchestrator instances.

    Thread-safe. Uses AdmissionGate for backpressure and
    ThreadPoolExecutor for parallel execution.

    Attributes:
        gate: AdmissionGate controlling max concurrent tasks.
        task_timeout: Per-task timeout passed to execute_with_judge().
        shared_registry: Optional shared CircuitBreakerRegistry.
    """

    def __init__(
        self,
        gate: AdmissionGate,
        task_timeout: float = 300.0,
    ):
        self.gate = gate
        self.task_timeout = task_timeout
        # Executor needs MORE workers than gate slots so overflow tasks
        # can be rejected by the gate rather than queued by the executor.
        # Capped at 32 to prevent unbounded thread creation.
        executor_workers = min(gate.max_concurrent * 4, 32)
        self._executor = ThreadPoolExecutor(max_workers=executor_workers)

        # Internal tracking
        self._lock = __import__("threading").Lock()
        self._running: dict[str, Future] = {}
        self._completed: dict[str, dict] = {}

    # ── Public API ──────────────────────────────────────────────────

    def dispatch(self, tasks: list[TaskSpec]) -> dict[str, Future]:
        """Submit tasks for execution. Returns futures immediately.

        Each task goes through the admission gate. Rejected tasks get
        a pre-resolved future with success=False, rejected=True.

        Returns:
            dict mapping task_id -> Future[dict]
        """
        futures: dict[str, Future] = {}
        for task in tasks:
            future: Future = Future()
            futures[task.task_id] = future
            self._executor.submit(self._run_task, task, future)

            with self._lock:
                self._running[task.task_id] = future

        return futures

    def run_all(self, tasks: list[TaskSpec]) -> dict[str, dict]:
        """Submit tasks and block until all complete.

        Returns:
            dict mapping task_id -> result dict (from execute_with_judge)
        """
        futures = self.dispatch(tasks)
        results: dict[str, dict] = {}

        for task_id, future in futures.items():
            try:
                results[task_id] = future.result(timeout=self.task_timeout + 30)
            except Exception as e:
                results[task_id] = {
                    "task_id": task_id,
                    "success": False,
                    "error": str(e),
                }

        return results

    @property
    def status(self) -> dict:
        """Snapshot of pool status."""
        with self._lock:
            running_ids = list(self._running.keys())
            completed_ids = list(self._completed.keys())
        return {
            "running": running_ids,
            "completed": completed_ids,
            "gate_metrics": self.gate.metrics,
        }

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the pool. No new tasks accepted.

        Args:
            wait: If True, blocks until all running tasks complete.
        """
        self.gate.shutdown(drain=wait)
        self._executor.shutdown(wait=wait)

    # ── Internal ────────────────────────────────────────────────────

    def _run_task(self, task: TaskSpec, future: Future) -> None:
        """Execute a single task in a fresh orchestrator instance."""
        ticket: Optional[AdmissionTicket] = None
        try:
            # Admit — blocks until slot or timeout
            ticket = self.gate.admit(task.task_id)
            if not ticket.admitted:
                future.set_result({
                    "task_id": task.task_id,
                    "success": False,
                    "rejected": True,
                    "reason": "admission gate full or shutdown",
                    "wait_seconds": ticket.wait_seconds,
                })
                return

            # Per-task orchestrator instance (full isolation)
            orchestrator = LLMOrchestrator()

            # Override per-task timeout from TaskSpec if specified
            effective_timeout = task.timeout_seconds or self.task_timeout

            result = orchestrator.execute_with_judge(**task.to_kwargs())
            future.set_result(result)

        except Exception as e:
            future.set_result({
                "task_id": task.task_id,
                "success": False,
                "error": str(e),
            })
        finally:
            if ticket is not None and ticket.admitted:
                ticket.release()
            with self._lock:
                self._running.pop(task.task_id, None)
                if future.done():
                    self._completed[task.task_id] = (
                        future.result() if future.exception() is None
                        else {"task_id": task.task_id, "success": False}
                    )
