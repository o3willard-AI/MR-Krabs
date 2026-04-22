#!/usr/bin/env python3
"""Unit tests for circuit breaker."""

import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(provider="test", model="test-model")
        assert cb.state == CircuitState.CLOSED

    def test_can_execute_when_closed(self):
        cb = CircuitBreaker(provider="test", model="test-model")
        assert cb.can_execute() is True

    def test_opens_after_failures(self):
        cb = CircuitBreaker(provider="test", model="test-model", failure_threshold=0.5, sample_size=4)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_rejects_when_open(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=9999)
        for _ in range(20):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_half_open_allows_test_requests(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=10, half_open_max=2)
        for _ in range(20):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.cooldown_seconds = 0
        time.sleep(0.01)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=10, half_open_max=2)
        for _ in range(20):
            cb.record_failure()
        cb.cooldown_seconds = 0
        time.sleep(0.01)
        assert cb.state == CircuitState.HALF_OPEN
        cb.can_execute()
        cb.record_success()
        cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=10, half_open_max=3)
        for _ in range(20):
            cb.record_failure()
        cb.cooldown_seconds = 0.01
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.can_execute()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_record_success_ignored_when_open(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=9999)
        for _ in range(20):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker(provider="test", model="test-model", cooldown_seconds=9999)
        for _ in range(20):
            cb.record_failure()
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_key(self):
        cb = CircuitBreaker(provider="openrouter", model="gpt-4")
        assert cb.key == ("openrouter", "gpt-4")


class TestCircuitBreakerRegistry:
    def test_creates_per_model(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get("openrouter", "model-a")
        cb2 = reg.get("openrouter", "model-b")
        assert cb1 is not cb2

    def test_same_model_same_instance(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get("openrouter", "model-a")
        cb2 = reg.get("openrouter", "model-a")
        assert cb1 is cb2

    def test_get_all_state(self):
        reg = CircuitBreakerRegistry()
        reg.get("openrouter", "model-a")
        reg.get("openrouter", "model-b")
        state = reg.get_all_state()
        assert "openrouter/model-a" in state
        assert "openrouter/model-b" in state

    def test_reset_all(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("openrouter", "model-a")
        for _ in range(20):
            cb.record_failure()
        reg.reset_all()
        assert cb.state == CircuitState.CLOSED
