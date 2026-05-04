#!/usr/bin/env python3
"""Retry logic with exponential backoff and jitter."""

import random
import time
from collections.abc import Callable
from typing import Any


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for given attempt number."""
    delay = config.base_delay * (config.exponential_base**attempt)

    if config.jitter:
        jitter_factor = 0.5 + random.random() * 0.5
        delay *= jitter_factor

    return min(delay, config.max_delay)


def retry_with_backoff(
    func: Callable,
    config: RetryConfig | None = None,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable[[int, Exception, float], None] | None = None,
    max_retries: int | None = None,
) -> Any:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Function to execute
        config: Retry configuration
        retryable_exceptions: Tuple of exceptions that trigger retry
        on_retry: Callback(attempt, exception, delay) called before each retry

    Returns:
        Result of successful function execution

    Raises:
        Last exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()
    
    # Override max_retries if provided as parameter
    if max_retries is not None:
        config = RetryConfig(
            max_retries=max_retries,
            base_delay=config.base_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
        )
    
    last_exception = None
    
    # First attempt
    try:
        return func()
    except retryable_exceptions as e:
        last_exception = e
    
    # Retry up to max_retries times
    # If max_retries is 0, no retries will happen
    for retry_attempt in range(config.max_retries):
        # Calculate delay before retry
        delay = calculate_delay(retry_attempt, config)
        
        # Call callback before retry
        if on_retry:
            on_retry(retry_attempt + 1, last_exception, delay)
        
        # Sleep before retry
        time.sleep(delay)
        
        # Execute retry
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
    
    # If we get here, all attempts failed
    raise last_exception


class RetryHandler:
    """Stateful retry handler for orchestrator operations."""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_error = None
        self.total_delay = 0.0

    def should_retry(self, exception: Exception) -> bool:
        """Check if operation should be retried."""
        return self.attempt < self.config.max_retries

    def wait_before_retry(self, on_retry: Callable | None = None) -> float:
        """Wait before next retry, returns delay."""
        delay = calculate_delay(self.attempt, self.config)
        self.total_delay += delay

        if on_retry:
            on_retry(self.attempt + 1, self.last_error, delay)

        time.sleep(delay)
        self.attempt += 1
        return delay

    def reset(self):
        """Reset retry state."""
        self.attempt = 0
        self.last_error = None
        self.total_delay = 0.0
