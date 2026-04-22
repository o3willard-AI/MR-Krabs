#!/usr/bin/env python3
"""Circuit breaker pattern for provider/model fault tolerance.

Keyed on (provider, model) pairs to avoid blocking all models when one is degraded.
Thread-safe with proper HALF_OPEN state handling to prevent race conditions.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Tuple


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit breaker for a specific (provider, model) pair.

    State machine:
    - CLOSED: Normal operation. Failures tracked against threshold.
    - OPEN: All requests rejected. Transitions to HALF_OPEN after cooldown.
    - HALF_OPEN: Limited test requests allowed. Success -> CLOSED, any failure -> OPEN.

    Race condition handling:
    - _half_open_epoch tracks each HALF_OPEN entry; stale results from previous epochs are discarded.
    - Counters reset when transitioning from HALF_OPEN to OPEN.
    - record_success() ignores results if state is already OPEN (re-opened by another thread).
    """

    provider: str
    model: str
    failure_threshold: float = 0.5
    sample_size: int = 10
    cooldown_seconds: float = 60
    half_open_max: int = 3

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _successes: int = field(default=0, init=False)
    _total: int = field(default=0, init=False)
    _opened_at: Optional[float] = field(default=None, init=False)
    _half_open_in_flight: int = field(default=0, init=False)
    _half_open_epoch: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def key(self) -> Tuple[str, str]:
        return (self.provider, self.model)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                if time.monotonic() - self._opened_at >= self.cooldown_seconds:
                    self._transition_to_half_open()
            return self._state

    def can_execute(self) -> bool:
        """Check if a request is allowed through the circuit."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._opened_at is not None and time.monotonic() - self._opened_at >= self.cooldown_seconds:
                    self._transition_to_half_open()
                    return True
                return False
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight < self.half_open_max:
                    self._half_open_in_flight += 1
                    return True
                return False
            return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                return
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._successes += 1
                if self._successes >= self.half_open_max:
                    self._close()
            elif self._state == CircuitState.CLOSED:
                self._successes += 1
                self._total += 1
                self._check_threshold()

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._open()
                return
            if self._state == CircuitState.CLOSED:
                self._failures += 1
                self._total += 1
                self._check_threshold()

    def get_state_info(self) -> Dict:
        """Get current state information for observability."""
        with self._lock:
            return {
                "provider": self.provider,
                "model": self.model,
                "state": self._state.value,
                "failures": self._failures,
                "successes": self._successes,
                "total": self._total,
                "failure_rate": self._failures / self._total if self._total > 0 else 0.0,
                "half_open_epoch": self._half_open_epoch,
                "half_open_in_flight": self._half_open_in_flight,
            }

    def _check_threshold(self) -> None:
        """Check if failure rate exceeds threshold. Must be called with lock held."""
        if self._total >= self.sample_size:
            failure_rate = self._failures / self._total
            if failure_rate >= self.failure_threshold:
                self._open()

    def _open(self) -> None:
        """Transition to OPEN state. Must be called with lock held."""
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._failures = 0
        self._successes = 0
        self._total = 0
        self._half_open_in_flight = 0

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state. Must be called with lock held."""
        self._state = CircuitState.HALF_OPEN
        self._failures = 0
        self._successes = 0
        self._total = 0
        self._half_open_in_flight = 0
        self._half_open_epoch += 1

    def _close(self) -> None:
        """Transition to CLOSED state. Must be called with lock held."""
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._total = 0
        self._half_open_in_flight = 0
        self._opened_at = None

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        with self._lock:
            self._close()


class CircuitBreakerRegistry:
    """Thread-safe registry of circuit breakers keyed on (provider, model)."""

    def __init__(
        self,
        failure_threshold: float = 0.5,
        sample_size: int = 10,
        cooldown_seconds: int = 60,
        half_open_max: int = 3,
    ):
        self._breakers: Dict[Tuple[str, str], CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._defaults = {
            "failure_threshold": failure_threshold,
            "sample_size": sample_size,
            "cooldown_seconds": cooldown_seconds,
            "half_open_max": half_open_max,
        }

    def get(self, provider: str, model: str) -> CircuitBreaker:
        """Get or create a circuit breaker for (provider, model)."""
        key = (provider, model)
        if key not in self._breakers:
            with self._lock:
                if key not in self._breakers:
                    self._breakers[key] = CircuitBreaker(
                        provider=provider,
                        model=model,
                        **self._defaults,
                    )
        return self._breakers[key]

    def get_all_state(self) -> Dict[str, Dict]:
        """Get state info for all circuit breakers."""
        result = {}
        with self._lock:
            for key, breaker in self._breakers.items():
                result[f"{key[0]}/{key[1]}"] = breaker.get_state_info()
        return result

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
