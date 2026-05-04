#!/usr/bin/env python3
"""Unit tests for retry.py - Retry logic with exponential backoff."""

import time
from unittest.mock import patch, MagicMock

import pytest
from src.core.retry import (
    RetryConfig,
    calculate_delay,
    retry_with_backoff,
    RetryHandler,
)


class TestRetryConfig:
    """Tests for RetryConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_config_with_zero_jitter(self):
        """Test config with jitter disabled."""
        config = RetryConfig(jitter=False)
        assert config.jitter is False


class TestCalculateDelay:
    """Tests for calculate_delay function."""

    def test_first_attempt_delay(self):
        """Test delay for first attempt."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        delay = calculate_delay(0, config)
        
        # Should be base_delay * (exponential_base ** 0) = 1.0
        assert delay == 1.0

    def test_exponential_increase(self):
        """Test delay increases exponentially."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0)
        
        delay_0 = calculate_delay(0, config)
        delay_1 = calculate_delay(1, config)
        delay_2 = calculate_delay(2, config)
        
        assert delay_1 > delay_0
        assert delay_2 > delay_1

    def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=10.0)
        
        # With high attempt number, should cap at max_delay
        delay = calculate_delay(100, config)
        assert delay <= 10.0

    def test_no_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        
        # Without jitter, delay should be deterministic
        delays = [calculate_delay(i, config) for i in range(5)]
        
        # All delays should be powers of 2
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        for actual, exp in zip(delays, expected):
            assert actual == exp

    def test_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=True)
        
        # With jitter, delays should vary
        delays = [calculate_delay(0, config) for _ in range(10)]
        
        # All should be within 50%-100% of base
        for delay in delays:
            assert 0.5 <= delay <= 1.0

    def test_delay_with_custom_base(self):
        """Test delay with custom base delay."""
        config = RetryConfig(base_delay=0.5, exponential_base=2.0, jitter=False)
        
        delay = calculate_delay(0, config)
        assert delay == 0.5


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    def test_success_on_first_try(self):
        """Test function succeeds on first attempt."""
        call_count = 0
        
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = retry_with_backoff(success_func)
        
        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self):
        """Test function succeeds after some retries."""
        call_count = 0
        
        def succeed_later():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = retry_with_backoff(succeed_later)
        
        assert result == "success"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        """Test raises exception after max retries."""
        def always_fails():
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError) as exc_info:
            retry_with_backoff(always_fails, max_retries=3)
        
        assert str(exc_info.value) == "Always fails"

    def test_custom_retry_config(self):
        """Test with custom retry configuration."""
        config = RetryConfig(max_retries=5, base_delay=0.1)
        call_count = 0
        
        def succeed_after_4():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ValueError("Try again")
            return "done"
        
        result = retry_with_backoff(succeed_after_4, config=config)
        
        assert result == "done"
        assert call_count == 4

    def test_retry_with_callback(self):
        """Test retry with on_retry callback."""
        callback_calls = []
        
        def callback(attempt, exception, delay):
            callback_calls.append((attempt, type(exception).__name__, delay))
        
        call_count = 0
        
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary")
            return "done"
        
        result = retry_with_backoff(fail_twice, on_retry=callback)
        
        assert result == "done"
        assert len(callback_calls) == 2  # Called 2 times before success
        assert callback_calls[0][0] == 1  # First retry attempt

    def test_specific_exception_only(self):
        """Test retry only for specific exceptions."""
        call_count = 0
        
        def fails_with_different_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Should retry")
            elif call_count == 2:
                raise RuntimeError("Should not retry")
            return "done"
        
        # Should raise RuntimeError immediately (not ValueError)
        with pytest.raises(RuntimeError):
            retry_with_backoff(
                fails_with_different_errors,
                retryable_exceptions=(ValueError,),
            )

    def test_no_retry_on_non_retryable(self):
        """Test no retry for non-retryable exceptions."""
        call_count = 0
        
        def fails_immediately():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Fatal error")
        
        with pytest.raises(RuntimeError):
            retry_with_backoff(
                fails_immediately,
                retryable_exceptions=(ValueError,),
            )
        
        assert call_count == 1  # Only one attempt

    def test_sleep_called(self):
        """Test that time.sleep is called during retries."""
        with patch('time.sleep') as mock_sleep:
            call_count = 0
            
            def fail_twice():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ValueError("Try again")
                return "done"
            
            config = RetryConfig(max_retries=3, base_delay=0.01)
            result = retry_with_backoff(fail_twice, config=config)
            
            assert result == "done"
            assert mock_sleep.call_count == 2  # Slept twice before success


class TestRetryHandler:
    """Tests for RetryHandler class."""

    def test_handler_initialization(self):
        """Test handler initialization."""
        handler = RetryHandler()
        
        assert handler.attempt == 0
        assert handler.last_error is None
        assert handler.total_delay == 0.0
        assert handler.config.max_retries == 3

    def test_handler_with_custom_config(self):
        """Test handler with custom config."""
        config = RetryConfig(max_retries=5, base_delay=0.5)
        handler = RetryHandler(config=config)
        
        assert handler.config.max_retries == 5
        assert handler.config.base_delay == 0.5

    def test_should_retry_true(self):
        """Test should_retry returns True before max retries."""
        handler = RetryHandler()
        handler.attempt = 2  # Within max_retries (3)
        
        assert handler.should_retry(Exception()) is True

    def test_should_retry_false(self):
        """Test should_retry returns False after max retries."""
        handler = RetryHandler()
        handler.attempt = 5  # Exceeds max_retries (3)
        
        assert handler.should_retry(Exception()) is False

    def test_wait_before_retry(self):
        """Test wait_before_retry calculates delay."""
        handler = RetryHandler()
        handler.last_error = ValueError("Test error")
        
        with patch('time.sleep'):
            delay = handler.wait_before_retry()
        
        assert delay > 0
        assert handler.attempt == 1
        assert handler.total_delay > 0

    def test_wait_before_retry_with_callback(self):
        """Test wait_before_retry calls callback."""
        handler = RetryHandler()
        handler.last_error = ValueError("Test")
        
        callback_calls = []
        
        def callback(attempt, error, delay):
            callback_calls.append((attempt, error, delay))
        
        with patch('time.sleep'):
            handler.wait_before_retry(on_retry=callback)
        
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 1  # First retry

    def test_reset(self):
        """Test reset clears handler state."""
        handler = RetryHandler()
        handler.attempt = 2
        handler.last_error = ValueError("Test")
        handler.total_delay = 10.0
        
        handler.reset()
        
        assert handler.attempt == 0
        assert handler.last_error is None
        assert handler.total_delay == 0.0

    def test_multiple_wait_cycles(self):
        """Test multiple wait cycles accumulate delays."""
        handler = RetryHandler()
        handler.last_error = ValueError("Test")
        
        with patch('time.sleep'):
            delay1 = handler.wait_before_retry()
            delay2 = handler.wait_before_retry()
        
        assert handler.attempt == 2
        assert handler.total_delay == delay1 + delay2
        assert handler.total_delay > delay1


class TestRetryEdgeCases:
    """Tests for edge cases in retry logic."""

    def test_zero_retries(self):
        """Test with zero retries (no retry)."""
        def fails():
            raise ValueError("Fail")
        
        config = RetryConfig(max_retries=0)
        
        with pytest.raises(ValueError):
            retry_with_backoff(fails, config=config)

    def test_one_retry(self):
        """Test with one retry (two attempts total)."""
        call_count = 0
        
        def fail_once_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First try")
            return "success"
        
        config = RetryConfig(max_retries=1)
        result = retry_with_backoff(fail_once_then_succeed, config=config)
        
        assert result == "success"
        assert call_count == 2

    def test_very_large_max_delay(self):
        """Test with very large max delay."""
        config = RetryConfig(base_delay=1.0, max_delay=1000000.0, jitter=False)
        
        delay = calculate_delay(100, config)
        assert delay == 1000000.0  # Should cap

    def test_very_small_base_delay(self):
        """Test with very small base delay."""
        config = RetryConfig(base_delay=0.001, max_retries=1)
        
        call_count = 0
        
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Fail")
            return "done"
        
        with patch('time.sleep'):
            result = retry_with_backoff(fail_then_succeed, config=config)
        
        assert result == "done"
