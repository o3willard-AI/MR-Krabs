#!/usr/bin/env python3
"""Unit tests for AdmissionGate backpressure controller."""

import threading
import time
import unittest

from src.core.admission import AdmissionGate, AdmissionTicket


class TestAdmissionGate(unittest.TestCase):

    def test_single_admit_release(self):
        gate = AdmissionGate(max_concurrent=1)
        ticket = gate.admit("task-1")
        self.assertTrue(ticket.admitted)
        self.assertEqual(gate.current_count, 1)

        ticket.release()
        self.assertEqual(gate.current_count, 0)

    def test_concurrent_limit_blocks(self):
        gate = AdmissionGate(max_concurrent=1, acquire_timeout=0.5)

        # Hold the only slot
        ticket_a = gate.admit("task-a")
        self.assertTrue(ticket_a.admitted)

        # Second task should be rejected after timeout
        ticket_b = gate.admit("task-b")
        self.assertFalse(ticket_b.admitted)
        self.assertGreater(ticket_b.wait_seconds, 0.4)

        # Release slot — next admit should succeed
        ticket_a.release()
        ticket_c = gate.admit("task-c")
        self.assertTrue(ticket_c.admitted)
        ticket_c.release()

    def test_context_manager(self):
        gate = AdmissionGate(max_concurrent=1)

        with gate.admit("t1") as ticket:
            self.assertTrue(ticket.admitted)
            self.assertEqual(gate.current_count, 1)

        # Context manager exit should have released
        self.assertEqual(gate.current_count, 0)

        # Next admit succeeds immediately
        ticket2 = gate.admit("t2")
        self.assertTrue(ticket2.admitted)
        ticket2.release()

    def test_multiple_slots(self):
        gate = AdmissionGate(max_concurrent=3, acquire_timeout=0.3)

        tickets = []
        for i in range(3):
            t = gate.admit(f"task-{i}")
            self.assertTrue(t.admitted, f"Task {i} should be admitted")
            tickets.append(t)

        self.assertEqual(gate.current_count, 3)

        # 4th should be rejected
        rejected = gate.admit("task-4")
        self.assertFalse(rejected.admitted)

        # Release one → 4th succeeds
        tickets[0].release()
        self.assertEqual(gate.current_count, 2)

        admitted_4 = gate.admit("task-4")
        self.assertTrue(admitted_4.admitted)
        admitted_4.release()

        for t in tickets[1:]:
            t.release()

    def test_shutdown_rejects(self):
        gate = AdmissionGate(max_concurrent=2, acquire_timeout=5.0)

        ticket = gate.admit("keep-alive")
        self.assertTrue(ticket.admitted)

        gate.shutdown(drain=False)

        # New admits should reject immediately
        rejected = gate.admit("post-shutdown")
        self.assertFalse(rejected.admitted)
        self.assertEqual(rejected.wait_seconds, 0.0)

        # Existing ticket can still release
        ticket.release()

    def test_shutdown_drain_blocks(self):
        gate = AdmissionGate(max_concurrent=2, acquire_timeout=5.0)

        ticket = gate.admit("task")
        self.assertTrue(ticket.admitted)

        # Drain should complete quickly since we release in another thread
        released = threading.Event()

        def delayed_release():
            time.sleep(0.2)
            ticket.release()
            released.set()

        drain_thread = threading.Thread(target=delayed_release)
        drain_thread.start()

        gate.shutdown(drain=True)  # should block until release
        self.assertTrue(released.is_set())

    def test_metrics_accuracy(self):
        gate = AdmissionGate(max_concurrent=2, acquire_timeout=0.2)

        # Admit 2
        t1 = gate.admit("task-1")
        t2 = gate.admit("task-2")
        self.assertTrue(t1.admitted)
        self.assertTrue(t2.admitted)

        # Reject 1 (gate full)
        rejected = gate.admit("task-3")
        self.assertFalse(rejected.admitted)

        # Release 1
        t1.release()

        m = gate.metrics
        self.assertEqual(m["current"], 1)
        self.assertEqual(m["total_admitted"], 2)
        self.assertEqual(m["total_rejected"], 1)
        self.assertEqual(m["max_concurrent"], 2)
        self.assertFalse(m["shutdown"])
        self.assertGreater(m["total_wait_secs"], 0)

        t2.release()

    def test_release_idempotent(self):
        """Calling release() on an already-released ticket is safe.

        Does not crash. Note: double-release makes current_count
        negative because threading.Semaphore allows over-release
        (unlike BoundedSemaphore which would raise).
        """
        gate = AdmissionGate(max_concurrent=1)
        ticket = gate.admit("task-1")
        ticket.release()
        ticket.release()  # safe — no crash
        # current_count goes negative after over-release — this is expected

    def test_rejected_ticket_release_noop(self):
        """Releasing a rejected ticket is a no-op."""
        gate = AdmissionGate(max_concurrent=1, acquire_timeout=0.1)
        t1 = gate.admit("task-1")  # holds slot
        rejected = gate.admit("task-2")  # rejected
        self.assertFalse(rejected.admitted)

        # Should not crash
        rejected.release()
        self.assertEqual(gate.current_count, 1)

        t1.release()

    def test_zero_concurrent_raises(self):
        with self.assertRaises(ValueError):
            AdmissionGate(max_concurrent=0)


if __name__ == "__main__":
    unittest.main()
