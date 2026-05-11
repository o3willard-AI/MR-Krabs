#!/usr/bin/env python3
"""Task timeout mechanism for MR-Krabs orchestrator."""

import signal
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict

from src.core.exceptions import TaskTimeoutError


class TaskTimeout:
    """Context manager that raises TaskTimeoutError after max_duration_seconds."""
    
    def __init__(self, max_duration_seconds: int = 300):
        self.max_duration_seconds = max_duration_seconds
        self._timer = None
        self._timeout_occurred = False
        self._original_alarm_handler = None
        
    def __enter__(self):
        """Start the timeout timer."""
        if self.max_duration_seconds <= 0:
            return self
            
        # Use signal-based timeout for Unix systems (most reliable)
        try:
            self._original_alarm_handler = signal.signal(signal.SIGALRM, self._handle_timeout)
            signal.alarm(self.max_duration_seconds)
        except (ValueError, OSError):
            # Fallback to threading timer for systems that don't support SIGALRM
            self._timer = threading.Timer(self.max_duration_seconds, self._handle_timeout)
            self._timer.start()
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the timeout timer and handle cleanup."""
        # Cancel the alarm or timer
        try:
            if self._timer is not None:
                self._timer.cancel()
            else:
                signal.alarm(0)  # Cancel any pending alarm
                # Restore original alarm handler
                if self._original_alarm_handler is not None:
                    signal.signal(signal.SIGALRM, self._original_alarm_handler)
        except (ValueError, OSError):
            pass
            
        # If timeout occurred, re-raise the exception
        if self._timeout_occurred:
            raise TaskTimeoutError(
                f"Task timed out after {self.max_duration_seconds} seconds",
                partial_result=None,
                accumulated_cost=0.0,
                elapsed_seconds=self.max_duration_seconds
            )
            
        return False  # Don't suppress exceptions
        
    def _handle_timeout(self, signum=None, frame=None):
        """Handle timeout signal."""
        self._timeout_occurred = True
        # Raise the exception in the main thread - this is the key part that makes it work
        raise TaskTimeoutError(
            f"Task timed out after {self.max_duration_seconds} seconds",
            partial_result=None,
            accumulated_cost=0.0,
            elapsed_seconds=self.max_duration_seconds
        )


@contextmanager
def task_timeout(max_duration_seconds: int = 300):
    """Context manager for task timeout."""
    timeout = TaskTimeout(max_duration_seconds)
    try:
        with timeout:
            yield timeout
    except TaskTimeoutError:
        raise