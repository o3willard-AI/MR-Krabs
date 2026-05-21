"""Admission gate for the MR-Krabs orchestrator.

Provides backpressure control for concurrent task execution. Uses a
threading.Semaphore to limit how many orchestrator instances can run
simultaneously, preventing resource exhaustion and cost explosions.

Usage:
    gate = AdmissionGate(max_concurrent=3)
    with gate.admit("task-1") as ticket:
        if ticket.admitted:
            run_orchestrator()
        else:
            handle_rejection()
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdmissionTicket:
    """Result of an admission request. Release to free the slot."""

    task_id: str
    admitted: bool
    wait_seconds: float = 0.0
    _gate: Optional["AdmissionGate"] = field(default=None, repr=False)

    def release(self) -> None:
        """Return the slot to the gate. No-op if not admitted."""
        if self.admitted and self._gate is not None:
            self._gate._release()

    def __enter__(self) -> "AdmissionTicket":
        return self

    def __exit__(self, *args) -> None:
        self.release()
        return False


class AdmissionGate:
    """Limits concurrent orchestrator executions via semaphore.

    Thread-safe. Acquire blocks until a slot is available or timeout
    is exceeded. Rejected acquires return tickets with admitted=False.

    Attributes:
        max_concurrent: Maximum simultaneous admissions.
        acquire_timeout: Seconds to wait before rejecting.
    """

    def __init__(self, max_concurrent: int = 3, acquire_timeout: float = 30.0):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self.acquire_timeout = acquire_timeout

        self._semaphore = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._shutdown = threading.Event()

        # Metrics
        self._total_admitted: int = 0
        self._total_rejected: int = 0
        self._total_wait_secs: float = 0.0

    # ── Public API ──────────────────────────────────────────────────

    def admit(self, task_id: str) -> AdmissionTicket:
        """Request admission. Blocks until slot or timeout.

        Returns an AdmissionTicket. Check ticket.admitted to determine
        whether the request was granted.

        Preferred usage is the context manager:
            with gate.admit("task-1") as ticket:
                if ticket.admitted:
                    ...
        """
        if self._shutdown.is_set():
            with self._lock:
                self._total_rejected += 1
            return AdmissionTicket(
                task_id=task_id, admitted=False, wait_seconds=0.0, _gate=self
            )

        wait_start = time.monotonic()
        acquired = self._semaphore.acquire(timeout=self.acquire_timeout)
        wait_elapsed = time.monotonic() - wait_start

        if acquired:
            with self._lock:
                self._total_admitted += 1
                self._total_wait_secs += wait_elapsed
            return AdmissionTicket(
                task_id=task_id, admitted=True, wait_seconds=wait_elapsed, _gate=self
            )
        else:
            with self._lock:
                self._total_rejected += 1
                self._total_wait_secs += wait_elapsed
            return AdmissionTicket(
                task_id=task_id, admitted=False, wait_seconds=wait_elapsed, _gate=self
            )

    def shutdown(self, drain: bool = True) -> None:
        """Close the gate. New admits return rejected immediately.

        If drain=True (default), blocks until all current slots are
        released. If drain=False, returns immediately — current holders
        can still release().
        """
        self._shutdown.set()
        if drain:
            # Acquire all slots, then release — ensures queue is drained
            for _ in range(self.max_concurrent):
                self._semaphore.acquire()
            for _ in range(self.max_concurrent):
                self._semaphore.release()

    @property
    def current_count(self) -> int:
        """Approximate count of currently held slots."""
        # semaphore._value gives available count; invert for held count
        # This is approximate because the semaphore value can change
        # between reading and returning.
        return self.max_concurrent - self._semaphore._value

    @property
    def metrics(self) -> dict:
        """Snapshot of gate metrics (thread-safe)."""
        with self._lock:
            return {
                "current": self.current_count,
                "max_concurrent": self.max_concurrent,
                "total_admitted": self._total_admitted,
                "total_rejected": self._total_rejected,
                "total_wait_secs": round(self._total_wait_secs, 3),
                "shutdown": self._shutdown.is_set(),
            }

    # ── Internal ────────────────────────────────────────────────────

    def _release(self) -> None:
        """Release a slot back to the gate. Called by AdmissionTicket.release()."""
        self._semaphore.release()

    # ── Context manager support ─────────────────────────────────────

    def __enter__(self):
        raise TypeError("Use gate.admit(task_id) as a context manager, not gate directly")

    def __exit__(self, *args):
        pass  # pragma: no cover
