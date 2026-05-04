#!/usr/bin/env python3
"""Unit tests for parallel.py."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.core.parallel import (
    ParallelExecutor,
    ParallelResult,
    ParallelTask,
    execute_parallel,
    execute_task,
    parallel_tool_executor,
)


class TestParallelTask:
    """Tests for ParallelTask dataclass."""

    def test_task_basic(self):
        """Test basic task creation."""
        task = ParallelTask(name="test", func=lambda: 42)
        assert task.name == "test"
        assert task.args == ()
        assert task.kwargs == {}

    def test_task_with_args(self):
        """Test task with positional args."""
        task = ParallelTask(name="add", func=lambda a, b: a + b, args=(2, 3))
        assert task.args == (2, 3)

    def test_task_with_kwargs(self):
        """Test task with keyword args."""
        task = ParallelTask(name="greet", func=lambda name: f"Hello {name}", kwargs={"name": "World"})
        assert task.kwargs == {"name": "World"}

    def test_task_kwargs_default_empty(self):
        """Test that kwargs defaults to empty dict."""
        task = ParallelTask(name="test", func=lambda: 1)
        assert task.kwargs == {}


class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = ParallelResult(name="test", success=True, result=42)
        assert result.success is True
        assert result.result == 42
        assert result.error is None

    def test_failure_result(self):
        """Test failed result."""
        result = ParallelResult(name="test", success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.result is None

    def test_result_with_duration(self):
        """Test result includes duration."""
        result = ParallelResult(name="test", success=True, result=1, duration=0.5)
        assert result.duration == 0.5


class TestExecuteTask:
    """Tests for execute_task function."""

    def test_sync_function_success(self):
        """Test executing a sync function."""
        async def run():
            task = ParallelTask(name="test", func=lambda: 42)
            result = await execute_task(task)
            return result

        result = asyncio.run(run())
        assert result.success is True
        assert result.result == 42
        assert result.error is None

    def test_sync_function_error(self):
        """Test sync function that raises exception."""
        async def run():
            def failing_func():
                raise ValueError("Test error")
            
            task = ParallelTask(name="fail", func=failing_func)
            result = await execute_task(task)
            return result

        result = asyncio.run(run())
        assert result.success is False
        assert "Test error" in result.error

    def test_async_function_success(self):
        """Test executing an async function."""
        async def async_func():
            await asyncio.sleep(0.01)
            return "done"

        async def run():
            task = ParallelTask(name="async_test", func=async_func)
            result = await execute_task(task)
            return result

        result = asyncio.run(run())
        assert result.success is True
        assert result.result == "done"

    def test_task_duration(self):
        """Test that duration is recorded."""
        async def run():
            async def slow_func():
                await asyncio.sleep(0.1)
                return "done"
            
            task = ParallelTask(name="slow", func=slow_func)
            result = await execute_task(task)
            return result

        result = asyncio.run(run())
        assert result.duration >= 0.1

    def test_task_with_args(self):
        """Test task with arguments."""
        async def run():
            task = ParallelTask(name="add", func=lambda a, b: a + b, args=(5, 10))
            result = await execute_task(task)
            return result

        result = asyncio.run(run())
        assert result.success is True
        assert result.result == 15


class TestExecuteParallel:
    """Tests for execute_parallel function."""

    def test_single_task(self):
        """Test executing a single task."""
        async def run():
            tasks = [ParallelTask(name="test", func=lambda: 42)]
            results = await execute_parallel(tasks)
            return results

        results = asyncio.run(run())
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result == 42

    def test_multiple_tasks(self):
        """Test executing multiple tasks."""
        async def run():
            tasks = [
                ParallelTask(name="task1", func=lambda: 1),
                ParallelTask(name="task2", func=lambda: 2),
                ParallelTask(name="task3", func=lambda: 3),
            ]
            results = await execute_parallel(tasks)
            return results

        results = asyncio.run(run())
        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.result for r in results] == [1, 2, 3]

    def test_mixed_success_failure(self):
        """Test mixed success and failure."""
        async def run():
            def success_func():
                return "ok"
            
            def fail_func():
                raise RuntimeError("fail")
            
            tasks = [
                ParallelTask(name="success", func=success_func),
                ParallelTask(name="fail", func=fail_func),
            ]
            results = await execute_parallel(tasks)
            return results

        results = asyncio.run(run())
        assert results[0].success is True
        assert results[1].success is False

    def test_exception_handling(self):
        """Test that unexpected exceptions are handled."""
        async def run():
            def raiser():
                raise TypeError("unexpected error")
            
            tasks = [ParallelTask(name="test", func=raiser)]
            results = await execute_parallel(tasks)
            return results

        results = asyncio.run(run())
        assert len(results) == 1
        assert results[0].success is False


class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    def test_init_max_concurrent(self):
        """Test executor initialization."""
        executor = ParallelExecutor(max_concurrent=10)
        assert executor.max_concurrent == 10

    def test_run_single_task(self):
        """Test running a single task."""
        executor = ParallelExecutor()
        tasks = [ParallelTask(name="test", func=lambda: 42)]
        results = executor.run(tasks)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result == 42

    def test_run_multiple_tasks(self):
        """Test running multiple tasks."""
        executor = ParallelExecutor()
        tasks = [
            ParallelTask(name="task1", func=lambda: 1),
            ParallelTask(name="task2", func=lambda: 2),
        ]
        results = executor.run(tasks)
        
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_concurrency_limit(self):
        """Test that max_concurrent limits parallelism."""
        active_count = [0]
        max_active = [0]
        lock = asyncio.Lock()

        async def tracked_func(task_id):
            async with lock:
                active_count[0] += 1
                max_active[0] = max(max_active[0], active_count[0])
            await asyncio.sleep(0.05)
            async with lock:
                active_count[0] -= 1
            return task_id

        async def run():
            tasks = [ParallelTask(name=str(i), func=lambda i=i: tracked_func(i)) for i in range(10)]
            executor = ParallelExecutor(max_concurrent=3)
            results = await executor.execute_batch(tasks)
            return results, max_active[0]

        results, max_concurrent_reached = asyncio.run(run())
        
        assert max_concurrent_reached <= 3
        assert all(r.success for r in results)

    def test_run_with_errors(self):
        """Test running tasks that fail."""
        executor = ParallelExecutor()
        tasks = [
            ParallelTask(name="ok", func=lambda: "success"),
            ParallelTask(name="fail", func=lambda: (_ for _ in ()).throw(ValueError("error"))),
        ]
        results = executor.run(tasks)
        
        assert results[0].success is True
        assert results[1].success is False


class TestParallelToolExecutor:
    """Tests for parallel_tool_executor function."""

    def test_empty_tool_calls(self):
        """Test with empty tool calls."""
        mock_file_tools = MagicMock()
        result = parallel_tool_executor(mock_file_tools, [])
        
        assert result["tool_results"] == []
        assert result["tools_executed"] == 0
        assert result["all_succeeded"] is True
        assert result["parallel"] is True

    def test_single_tool_call(self):
        """Test with single tool call."""
        mock_file_tools = MagicMock()
        tool_calls = [
            {
                "tool": "file_write",
                "path": "/test.txt",
                "content": "test content"
            }
        ]
        
        # Mock the parse_and_execute_tools to return a result
        mock_executor = MagicMock()
        mock_executor.parse_and_execute_tools = MagicMock(return_value={
            "tool_results": [{"success": True, "content": "written"}],
            "tools_executed": 1
        })
        
        with pytest.MonkeyPatch.context() as mp:
            from src.core import orchestrator
            mp.setattr(orchestrator, 'ToolExecutor', MagicMock(return_value=mock_executor))
            
            result = parallel_tool_executor(mock_file_tools, tool_calls)
        
        assert result["parallel"] is True

    def test_multiple_tool_calls(self):
        """Test with multiple tool calls."""
        mock_file_tools = MagicMock()
        tool_calls = [
            {"tool": "file_write", "path": "/test1.txt", "content": "content1"},
            {"tool": "file_write", "path": "/test2.txt", "content": "content2"},
        ]
        
        # Each call returns 2 results (extend adds them all)
        mock_executor = MagicMock()
        mock_executor.parse_and_execute_tools = MagicMock(return_value={
            "tool_results": [
                {"success": True, "content": "written1"},
                {"success": True, "content": "written2"},
            ],
            "tools_executed": 2
        })
        
        with pytest.MonkeyPatch.context() as mp:
            from src.core import orchestrator
            mp.setattr(orchestrator, 'ToolExecutor', MagicMock(return_value=mock_executor))
            
            result = parallel_tool_executor(mock_file_tools, tool_calls)
        
        # 2 calls * 2 results each = 4 total results
        assert result["tool_results"] == [
            {"success": True, "content": "written1"},
            {"success": True, "content": "written2"},
            {"success": True, "content": "written1"},
            {"success": True, "content": "written2"},
        ]
        assert result["parallel"] is True
