#!/usr/bin/env python3
"""Unit tests for feedback.py - Feedback loop for LLM tuning.

P1-11: Unit tests for Phase 1 features
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.feedback import ToolFeedback, FeedbackManager, format_tool_response


class TestToolFeedback:
    """Tests for ToolFeedback dataclass."""

    def test_feedback_creation_success(self):
        """Test creating a successful tool feedback."""
        feedback = ToolFeedback(
            tool_name="file_read",
            path="/tmp/test.txt",
            success=True,
            result="test content",
        )

        assert feedback.tool_name == "file_read"
        assert feedback.path == "/tmp/test.txt"
        assert feedback.success is True
        assert feedback.result == "test content"
        assert feedback.error is None
        assert feedback.bytes_count == 0

    def test_feedback_creation_failure(self):
        """Test creating a failed tool feedback."""
        feedback = ToolFeedback(
            tool_name="file_write",
            path="/tmp/unsafe.txt",
            success=False,
            result=None,
            error="Permission denied",
        )

        assert feedback.tool_name == "file_write"
        assert feedback.success is False
        assert feedback.error == "Permission denied"
        assert feedback.result is None

    def test_to_llm_message_success_file_read(self):
        """Test formatting success message for file_read."""
        feedback = ToolFeedback(
            tool_name="file_read",
            path="/tmp/test.txt",
            success=True,
            result="Line 1\nLine 2\nLine 3",
            bytes_count=21,
        )

        message = feedback.to_llm_message()

        assert isinstance(message, str)
        assert "✓" in message
        assert "file_read" in message
        assert "SUCCESS" in message

    def test_to_llm_message_success_file_write(self):
        """Test formatting success message for file_write."""
        feedback = ToolFeedback(
            tool_name="file_write",
            path="/tmp/output.txt",
            success=True,
            result=None,
            bytes_count=1024,
        )

        message = feedback.to_llm_message()

        assert isinstance(message, str)
        assert "✓" in message
        assert "file_write" in message
        assert "SUCCESS" in message
        assert "1024" in message

    def test_to_llm_message_failure(self):
        """Test formatting failure message."""
        feedback = ToolFeedback(
            tool_name="file_delete",
            path="/tmp/missing.txt",
            success=False,
            result=None,
            error="File not found",
        )

        message = feedback.to_llm_message()

        assert isinstance(message, str)
        assert "✗" in message
        assert "file_delete" in message
        assert "FAILED" in message
        assert "File not found" in message

    def test_to_llm_message_long_content(self):
        """Test formatting with long content gets truncated."""
        long_content = "x" * 500
        feedback = ToolFeedback(
            tool_name="file_read",
            path="/tmp/large.txt",
            success=True,
            result=long_content,
        )

        message = feedback.to_llm_message()

        assert isinstance(message, str)
        assert "..." in message  # Should show truncation

    def test_feedback_default_values(self):
        """Test that default values are set correctly."""
        feedback = ToolFeedback(
            tool_name="test_tool",
            path="/tmp/test",
            success=True,
            result="data",
        )

        assert feedback.bytes_count == 0
        assert feedback.error is None


class TestFeedbackManager:
    """Tests for FeedbackManager class."""

    def test_manager_initialization(self):
        """Test feedback manager initialization."""
        manager = FeedbackManager()

        assert manager.max_feedback_length == 4000
        assert manager.feedback_history == []

    def test_manager_initialization_custom_length(self):
        """Test feedback manager with custom max length."""
        manager = FeedbackManager(max_feedback_length=2000)

        assert manager.max_feedback_length == 2000

    def test_add_feedback(self):
        """Test adding feedback to history."""
        manager = FeedbackManager()
        feedback = ToolFeedback(
            tool_name="file_read",
            path="/tmp/test.txt",
            success=True,
            result="content",
        )

        manager.add_feedback(feedback)

        assert len(manager.feedback_history) == 1
        assert manager.feedback_history[0] is feedback

    def test_add_multiple_feedback(self):
        """Test adding multiple feedback entries."""
        manager = FeedbackManager()

        for i in range(5):
            manager.add_feedback(
                ToolFeedback(
                    tool_name="file_read",
                    path=f"/tmp/test{i}.txt",
                    success=True,
                    result=f"content {i}",
                )
            )

        assert len(manager.feedback_history) == 5

    def test_get_feedback_context_empty(self):
        """Test getting feedback context with no entries."""
        manager = FeedbackManager()

        context = manager.get_feedback_context()

        assert context == "No tool executions yet."

    def test_get_feedback_context_with_entries(self):
        """Test getting feedback context with entries."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test.txt",
                success=True,
                result="content",
                bytes_count=100,
            )
        )

        context = manager.get_feedback_context()

        assert isinstance(context, str)
        assert "## Tool Execution Results:" in context
        assert "file_read" in context
        assert "SUCCESS" in context

    def test_get_feedback_context_truncated(self):
        """Test that feedback context is truncated when too long."""
        manager = FeedbackManager(max_feedback_length=100)

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/large.txt",
                success=True,
                result="x" * 200,
                bytes_count=200,
            )
        )

        context = manager.get_feedback_context()

        # The context should be truncated since header + content exceeds max
        # Truncation adds "\\n... [truncated]" which is 16 chars
        assert len(context) <= manager.max_feedback_length + 16
        assert "[truncated]" in context

    def test_get_last_feedback(self):
        """Test getting the last feedback."""
        manager = FeedbackManager()

        feedback1 = ToolFeedback(
            tool_name="file_read",
            path="/tmp/test1.txt",
            success=True,
            result="content 1",
        )
        feedback2 = ToolFeedback(
            tool_name="file_write",
            path="/tmp/test2.txt",
            success=True,
            result=None,
        )

        manager.add_feedback(feedback1)
        manager.add_feedback(feedback2)

        last = manager.get_last_feedback()

        assert last is feedback2

    def test_get_last_feedback_empty(self):
        """Test getting last feedback from empty history."""
        manager = FeedbackManager()

        last = manager.get_last_feedback()

        assert last is None

    def test_all_succeeded_all_success(self):
        """Test all_succeeded when all are successful."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test1.txt",
                success=True,
                result="content",
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_write",
                path="/tmp/test2.txt",
                success=True,
                result=None,
            )
        )

        assert manager.all_succeeded() is True

    def test_all_succeeded_with_failure(self):
        """Test all_succeeded when one fails."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test1.txt",
                success=True,
                result="content",
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_write",
                path="/tmp/test2.txt",
                success=False,
                result=None,
                error="Permission denied",
            )
        )

        assert manager.all_succeeded() is False

    def test_get_failures_empty(self):
        """Test getting failures from empty history."""
        manager = FeedbackManager()

        failures = manager.get_failures()

        assert failures == []

    def test_get_failures_mixed(self):
        """Test getting failures from mixed history."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test1.txt",
                success=True,
                result="content",
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_write",
                path="/tmp/test2.txt",
                success=False,
                result=None,
                error="Permission denied",
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_delete",
                path="/tmp/test3.txt",
                success=False,
                result=None,
                error="File not found",
            )
        )

        failures = manager.get_failures()

        assert len(failures) == 2
        assert all(not fb.success for fb in failures)

    def test_clear(self):
        """Test clearing feedback history."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test.txt",
                success=True,
                result="content",
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_write",
                path="/tmp/output.txt",
                success=True,
                result=None,
            )
        )

        manager.clear()

        assert manager.feedback_history == []

    def test_to_dict(self):
        """Test converting to dictionary."""
        manager = FeedbackManager()

        manager.add_feedback(
            ToolFeedback(
                tool_name="file_read",
                path="/tmp/test.txt",
                success=True,
                result="content",
                bytes_count=100,
            )
        )
        manager.add_feedback(
            ToolFeedback(
                tool_name="file_write",
                path="/tmp/output.txt",
                success=False,
                result=None,
                error="Permission denied",
                bytes_count=0,
            )
        )

        result_dict = manager.to_dict()

        assert isinstance(result_dict, dict)
        assert "total_executions" in result_dict
        assert "successes" in result_dict
        assert "failures" in result_dict
        assert "history" in result_dict
        assert result_dict["total_executions"] == 2
        assert result_dict["successes"] == 1
        assert result_dict["failures"] == 1

    def test_to_dict_empty(self):
        """Test converting empty manager to dictionary."""
        manager = FeedbackManager()

        result_dict = manager.to_dict()

        assert result_dict["total_executions"] == 0
        assert result_dict["successes"] == 0
        assert result_dict["failures"] == 0
        assert result_dict["history"] == []

    def test_add_from_tool_result(self):
        """Test adding feedback from tool result dict."""
        manager = FeedbackManager()

        tool_result = {
            "tool_results": [
                {
                    "tool": "file_read",
                    "path": "/tmp/test.txt",
                    "success": True,
                    "content": "content here",
                    "bytes": 100,
                },
                {
                    "tool": "file_write",
                    "path": "/tmp/output.txt",
                    "success": False,
                    "error": "Permission denied",
                    "bytes": 0,
                },
            ]
        }

        manager.add_from_tool_result(tool_result)

        assert len(manager.feedback_history) == 2
        assert manager.feedback_history[0].tool_name == "file_read"
        assert manager.feedback_history[0].success is True
        assert manager.feedback_history[1].tool_name == "file_write"
        assert manager.feedback_history[1].success is False

    def test_add_from_tool_result_empty(self):
        """Test adding from empty tool result."""
        manager = FeedbackManager()

        tool_result = {"tool_results": []}

        manager.add_from_tool_result(tool_result)

        assert manager.feedback_history == []

    def test_add_from_tool_result_missing_fields(self):
        """Test adding from tool result with missing optional fields."""
        manager = FeedbackManager()

        tool_result = {
            "tool_results": [
                {"tool": "file_read", "path": "/tmp/test.txt", "success": True}
            ]
        }

        manager.add_from_tool_result(tool_result)

        assert len(manager.feedback_history) == 1
        assert manager.feedback_history[0].bytes_count == 0
        assert manager.feedback_history[0].error is None


class TestFormatToolResponse:
    """Tests for format_tool_response function."""

    def test_format_response_success(self):
        """Test formatting successful tool response."""
        tool_result = {
            "tool_results": [
                {
                    "tool": "file_read",
                    "path": "/tmp/test.txt",
                    "success": True,
                    "content": "test content",
                    "bytes": 12,
                }
            ]
        }

        result = format_tool_response(tool_result)

        assert isinstance(result, str)
        assert "## Tool Execution Results:" in result
        assert "SUCCESS" in result

    def test_format_response_failure(self):
        """Test formatting failed tool response."""
        tool_result = {
            "tool_results": [
                {
                    "tool": "file_write",
                    "path": "/tmp/output.txt",
                    "success": False,
                    "error": "Permission denied",
                    "bytes": 0,
                }
            ]
        }

        result = format_tool_response(tool_result)

        assert isinstance(result, str)
        assert "## Tool Execution Results:" in result
        assert "FAILED" in result
        assert "Permission denied" in result

    def test_format_response_empty(self):
        """Test formatting empty tool response."""
        tool_result = {"tool_results": []}

        result = format_tool_response(tool_result)

        assert result == "No tool executions yet."


class TestFeedbackManagerIntegration:
    """Integration tests for FeedbackManager."""

    def test_full_workflow(self):
        """Test a complete feedback workflow."""
        manager = FeedbackManager()

        # Add some successful operations
        manager.add_from_tool_result({
            "tool_results": [
                {
                    "tool": "file_read",
                    "path": "/tmp/data.txt",
                    "success": True,
                    "content": "data content",
                    "bytes": 12,
                }
            ]
        })

        # Verify state
        assert len(manager.feedback_history) == 1
        assert manager.all_succeeded() is True

        # Add a failure
        manager.add_from_tool_result({
            "tool_results": [
                {
                    "tool": "file_write",
                    "path": "/tmp/output.txt",
                    "success": False,
                    "error": "Permission denied",
                    "bytes": 0,
                }
            ]
        })

        # Verify state changed
        assert len(manager.feedback_history) == 2
        assert manager.all_succeeded() is False
        assert len(manager.get_failures()) == 1

        # Get context
        context = manager.get_feedback_context()
        assert isinstance(context, str)
        assert "## Tool Execution Results:" in context

        # Convert to dict
        data = manager.to_dict()
        assert data["total_executions"] == 2
        assert data["successes"] == 1
        assert data["failures"] == 1
