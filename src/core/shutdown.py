#!/usr/bin/env python3
"""Graceful shutdown handler for the orchestrator.

Handles SIGTERM/SIGINT to:
- Release in-flight budget reservations
- Record partial task costs
- Persist task state for potential resume
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown of the orchestrator.

    Registers signal handlers for SIGTERM and SIGINT.
    Runs registered cleanup callbacks in reverse order.
    """

    def __init__(self):
        self._callbacks: list[Callable] = []
        self._shutdown_event = threading.Event()
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._installed = False

    def register(self, callback: Callable) -> None:
        """Register a cleanup callback. Callbacks run in reverse order."""
        self._callbacks.append(callback)

    def install(self) -> None:
        """Install signal handlers."""
        if self._installed:
            return
        signal.signal(signal.SIGTERM, self._handler)
        signal.signal(signal.SIGINT, self._handler)
        self._installed = True

    def uninstall(self) -> None:
        """Restore original signal handlers."""
        if not self._installed:
            return
        signal.signal(signal.SIGTERM, self._original_sigterm)
        signal.signal(signal.SIGINT, self._original_sigint)
        self._installed = False

    @property
    def is_shutdown_requested(self) -> bool:
        return self._shutdown_event.is_set()

    def shutdown(self) -> None:
        """Trigger shutdown immediately."""
        self._handler(signal.SIGTERM, None)

    def _handler(self, signum, frame) -> None:
        logger.info(f"Shutdown signal {signum} received, cleaning up...")
        self._shutdown_event.set()
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception:
                logger.exception(f"Error in shutdown callback: {callback}")

    def reset(self) -> None:
        """Reset shutdown state (useful for testing)."""
        self._shutdown_event.clear()
        self._callbacks.clear()


_shutdown_handler: GracefulShutdown | None = None


def get_shutdown_handler() -> GracefulShutdown:
    """Get the global shutdown handler."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdown()
    return _shutdown_handler
