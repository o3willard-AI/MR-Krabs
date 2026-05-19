"""Circuit breaker pattern for LLM provider resilience.

Implements the standard circuit breaker pattern with three states:
- CLOSED: Normal operation, requests flow through
- OPEN: Circuit tripped, requests rejected immediately
- HALF_OPEN: Testing recovery, allows limited probe requests

Supports per-provider+model granularity, sliding window failure counting,
state persistence, manual override, and Prometheus metrics.
"""

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5
    failure_window_s: float = 60.0
    reset_timeout_s: float = 30.0
    half_open_max_probes: int = 1
    success_threshold: int = 2
    enabled: bool = True


class CircuitBreaker:
    """Circuit breaker for a single provider+model combination.
    
    Thread-safe. Tracks failures in a sliding window and transitions
    between CLOSED → OPEN → HALF_OPEN → CLOSED states.
    """
    
    def __init__(self, provider: str, model: str, config: Optional[CircuitBreakerConfig] = None):
        self.provider = provider
        self.model = model
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_timestamps: deque = deque()
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._last_state_change: float = time.monotonic()
        self._open_since: Optional[float] = None
        self._half_open_probes_sent: int = 0
        self._lock = threading.Lock()
    
    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition()
            return self._state
    
    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN
    
    @property
    def can_proceed(self) -> bool:
        """Check if a request can proceed through this circuit."""
        return self.state != CircuitState.OPEN
    
    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._maybe_transition()  # Check for HALF_OPEN → CLOSED transition
            
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0
                self._consecutive_successes += 1
    
    def record_failure(self, error_type: str = "unknown") -> bool:
        """Record a failed request. Returns True if circuit just tripped."""
        with self._lock:
            now = time.monotonic()
            
            # Only count circuit-relevant errors
            if not self._is_circuit_relevant(error_type):
                return False
            
            self._failure_timestamps.append(now)
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            
            # Prune old failures outside the window
            cutoff = now - self.config.failure_window_s
            while self._failure_timestamps and self._failure_timestamps[0] < cutoff:
                self._failure_timestamps.popleft()
            
            # Check if threshold reached
            if self._state == CircuitState.CLOSED:
                recent_failures = len(self._failure_timestamps)
                if recent_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    return True
                elif self._consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    return True
            
            return False
    
    def _is_circuit_relevant(self, error_type: str) -> bool:
        """Only connection errors, 5xx, and 429 count toward circuit breaker."""
        relevant = {"connection", "timeout", "dns", "5xx", "server_error", "rate_limit", "429"}
        irrelevant = {"4xx", "bad_request", "auth_error", "budget_exhausted", "validation"}
        if error_type.lower() in irrelevant:
            return False
        if error_type.lower() in relevant:
            return True
        return True  # Unknown errors count (conservative)
    
    def _maybe_transition(self) -> None:
        """Check if state transition is needed (called under lock)."""
        if self._state == CircuitState.OPEN:
            if self._open_since is not None:
                elapsed = time.monotonic() - self._open_since
                if elapsed >= self.config.reset_timeout_s:
                    self._transition_to(CircuitState.HALF_OPEN)
            return True
        return True  # Unknown errors count (conservative)
    
    def _maybe_transition(self) -> None:
        """Check if state transition is needed (called under lock)."""
        if self._state == CircuitState.OPEN:
            if self._open_since is not None:
                elapsed = time.monotonic() - self._open_since
                if elapsed >= self.config.reset_timeout_s:
                    self._transition_to(CircuitState.HALF_OPEN)
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Perform state transition (called under lock)."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.monotonic()
        
        if new_state == CircuitState.OPEN:
            self._open_since = time.monotonic()
            self._half_open_probes_sent = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._consecutive_successes = 0
            self._half_open_probes_sent = 0
        elif new_state == CircuitState.CLOSED:
            self._open_since = None
            self._consecutive_failures = 0
            self._failure_timestamps.clear()
    
    def force_state(self, state: CircuitState) -> None:
        """Manually override circuit state."""
        with self._lock:
            self._transition_to(state)
    
    def get_status(self) -> dict:
        """Get current circuit status for observability."""
        with self._lock:
            return {
                "provider": self.provider,
                "model": self.model,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "consecutive_successes": self._consecutive_successes,
                "recent_failures": len(self._failure_timestamps),
                "seconds_in_state": time.monotonic() - self._last_state_change,
                "open_since": self._open_since,
            }


class CircuitBreakerRegistry:
    """Manages circuit breakers for all provider+model combinations."""
    
    def __init__(self, state_file: Optional[str] = None):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._state_file = state_file
        self._load_state()
    
    def _key(self, provider: str, model: str) -> str:
        return f"{provider}/{model}"
    
    def get(self, provider: str, model: str, 
            config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker for provider+model."""
        key = self._key(provider, model)
        with self._lock:
            if key not in self._breakers:
                self._breakers[key] = CircuitBreaker(provider, model, config)
            return self._breakers[key]
    
    def is_open(self, provider: str, model: str) -> bool:
        """Check if circuit is open for a provider+model."""
        return self.get(provider, model).is_open
    
    def can_proceed(self, provider: str, model: str) -> bool:
        """Check if a request can proceed for provider+model."""
        return self.get(provider, model).can_proceed
    
    def record_success(self, provider: str, model: str) -> None:
        """Record success for provider+model."""
        self.get(provider, model).record_success()
    
    def record_failure(self, provider: str, model: str, error_type: str = "unknown") -> bool:
        """Record failure. Returns True if circuit just tripped."""
        return self.get(provider, model).record_failure(error_type)
    
    def get_all_status(self) -> list:
        """Get status of all circuit breakers."""
        with self._lock:
            return [cb.get_status() for cb in self._breakers.values()]
    
    def force_state(self, provider: str, model: str, state: CircuitState) -> None:
        """Manually override circuit state."""
        self.get(provider, model).force_state(state)
    
    def reset_all(self) -> None:
        """Reset all circuits to CLOSED."""
        with self._lock:
            for cb in self._breakers.values():
                cb.force_state(CircuitState.CLOSED)
    
    def _save_state(self) -> None:
        """Persist circuit breaker states to file."""
        if not self._state_file:
            return
        try:
            state_data = []
            with self._lock:
                for key, cb in self._breakers.items():
                    provider, model = key.split("/", 1)
                    status = cb.get_status()
                    status["provider"] = provider
                    status["model"] = model
                    state_data.append(status)
            Path(self._state_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w") as f:
                json.dump(state_data, f, indent=2)
        except Exception:
            pass  # Best-effort persistence
    
    def _load_state(self) -> None:
        """Load persisted circuit breaker states."""
        if not self._state_file:
            return
        try:
            if not Path(self._state_file).exists():
                return
            with open(self._state_file) as f:
                state_data = json.load(f)
            with self._lock:
                for entry in state_data:
                    key = self._key(entry["provider"], entry["model"])
                    if key in self._breakers:
                        cb = self._breakers[key]
                        state = CircuitState(entry.get("state", "closed"))
                        cb.force_state(state)
        except Exception:
            pass


# Singleton registry instance
_circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry(state_file: str = "~/.mrkrabs/circuit_breaker_state.json") -> CircuitBreakerRegistry:
    """Get or create the singleton circuit breaker registry."""
    global _circuit_breaker_registry
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry(
            state_file=Path(state_file).expanduser()
        )
    return _circuit_breaker_registry
