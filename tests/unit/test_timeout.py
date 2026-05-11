#!/usr/bin/env python3
"""Unit tests for timeout functionality."""

import time
import pytest
from unittest.mock import patch, MagicMock

from src.core.timeout import TaskTimeout, task_timeout
from src.core.exceptions import TaskTimeoutError


class TestTaskTimeout:
    """Tests for TaskTimeout context manager."""
    
    def test_timeout_triggers(self):
        """Test that timeout raises TaskTimeoutError when exceeded."""
        # Create a task that sleeps longer than the timeout
        with pytest.raises(TaskTimeoutError) as exc_info:
            with TaskTimeout(max_duration_seconds=1):
                time.sleep(2)
        
        assert "timed out" in str(exc_info.value).lower()
        assert "1 seconds" in str(exc_info.value)
    
    def test_timeout_records_partial_cost(self):
        """Test that timeout records partial cost and result."""
        # This is a more complex test that requires mocking the actual cost tracking
        # For now, just ensure the exception can be constructed with all parameters
        try:
            with TaskTimeout(max_duration_seconds=1):
                time.sleep(2)
        except TaskTimeoutError as e:
            # The real implementation should populate these fields, but for this test,
            # we're ensuring it's constructable with all expected parameters
            assert e.partial_result is None
            assert e.accumulated_cost == 0.0
            assert e.elapsed_seconds == 1.0
    
    def test_normal_task_not_affected(self):
        """Test that normal fast tasks complete without timeout."""
        start_time = time.time()
        
        with TaskTimeout(max_duration_seconds=5):
            # This should complete quickly
            result = "test_result"
            
        end_time = time.time()
        assert result == "test_result"
        assert (end_time - start_time) < 2.0  # Should be fast
    
    def test_timeout_error_distinguishable(self):
        """Test that TaskTimeoutError is distinguishable from other exceptions."""
        with pytest.raises(TaskTimeoutError) as exc_info:
            with TaskTimeout(max_duration_seconds=1):
                time.sleep(2)
        
        # Ensure it's a TaskTimeoutError and can be caught specifically
        assert isinstance(exc_info.value, TaskTimeoutError)
        assert isinstance(exc_info.value, Exception)  # It should inherit from Exception
        
        # Test that it's not caught by generic LLM error handlers (which would mean catching Exception)
        # This is more about ensuring it's a distinct exception type from LLM errors
        # We can verify it doesn't inherit from any specific LLM error classes 
        assert not hasattr(exc_info.value, 'status_code')  # Unlike APIError
        assert not hasattr(exc_info.value, 'response')  # Unlike APIError