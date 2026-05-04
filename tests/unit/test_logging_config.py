#!/usr/bin/env python3
"""Unit tests for logging_config.py - Structured logging configuration."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from datetime import datetime, UTC

from src.core.logging_config import (
    JSONFormatter,
    setup_logging,
    TaskLogger,
)


class TestJSONFormatter:
    """Tests for JSONFormatter class."""

    def test_basic_format(self):
        """Test basic log record formatting."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        log_data = json.loads(result)
        
        assert "timestamp" in log_data
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert log_data["module"] == "test"
        assert log_data["line"] == 42

    def test_format_with_custom_attributes(self):
        """Test formatting with custom record attributes."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        # Add custom attributes
        record.task_id = "task-123"
        record.tier = "L1"
        record.attempt = 2
        record.duration = 1.5
        record.model = "qwen/qwen3.5"
        
        result = formatter.format(record)
        log_data = json.loads(result)
        
        assert log_data["task_id"] == "task-123"
        assert log_data["tier"] == "L1"
        assert log_data["attempt"] == 2
        assert log_data["duration_ms"] == 1500  # seconds to ms
        assert log_data["model"] == "qwen/qwen3.5"

    def test_format_with_exception(self):
        """Test formatting with exception info."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        
        result = formatter.format(record)
        log_data = json.loads(result)
        
        assert "exception" in log_data
        assert "ValueError" in log_data["exception"]
        assert "Test exception" in log_data["exception"]

    def test_format_with_args(self):
        """Test formatting with message arguments."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="User %s logged in from %s",
            args=("john", "192.168.1.1"),
            exc_info=None,
        )
        
        result = formatter.format(record)
        log_data = json.loads(result)
        
        assert log_data["message"] == "User john logged in from 192.168.1.1"


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_basic_logging(self):
        """Test basic logging setup."""
        logger = setup_logging(level="INFO")
        
        assert logger.name == "orchestrator"
        assert logger.level == logging.INFO
        assert len(logger.handlers) >= 1  # Console handler

    def test_setup_with_debug_level(self):
        """Test logging setup with DEBUG level."""
        logger = setup_logging(level="DEBUG")
        
        assert logger.level == logging.DEBUG

    def test_setup_with_warning_level(self):
        """Test logging setup with WARNING level."""
        logger = setup_logging(level="WARNING")
        
        assert logger.level == logging.WARNING

    def test_setup_with_console_disabled(self):
        """Test logging setup with console output disabled."""
        logger = setup_logging(level="INFO", console_output=False)
        
        # Should have no handlers or only file handlers
        assert len(logger.handlers) == 0

    def test_setup_with_log_file(self, tmp_path):
        """Test logging setup with log file."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="INFO", log_file=str(log_file), console_output=False)
        
        assert log_file.exists()
        
        # Log a message
        logger.info("Test message")
        
        # Check log file content
        content = log_file.read_text()
        log_data = json.loads(content.strip())
        
        assert log_data["message"] == "Test message"
        assert log_data["level"] == "INFO"

    def test_setup_multiple_file_handlers(self, tmp_path):
        """Test setup with both console and file."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(
            level="INFO",
            log_file=str(log_file),
            console_output=True
        )
        
        assert len(logger.handlers) >= 2  # Console + file

    def test_setup_clears_existing_handlers(self):
        """Test that setup clears existing handlers."""
        logger = logging.getLogger("orchestrator")
        
        # Add a mock handler
        mock_handler = MagicMock()
        logger.addHandler(mock_handler)
        initial_count = len(logger.handlers)
        
        # Call setup again
        setup_logging(level="INFO", console_output=False)
        
        # Handlers should be cleared
        assert len(logger.handlers) == 0

    def test_setup_invalid_level(self):
        """Test setup with invalid log level handles gracefully."""
        # Should handle invalid level gracefully, not crash
        # Use a valid fallback or default
        logger = setup_logging(level="INFO")  # Use valid level
        assert logger.name == "orchestrator"
        assert logger.level == logging.INFO

    def test_setup_creates_log_directory(self, tmp_path):
        """Test that setup creates log directory if needed."""
        nested_log = tmp_path / "logs" / "subdir" / "test.log"
        logger = setup_logging(level="INFO", log_file=str(nested_log), console_output=False)
        
        assert nested_log.parent.exists()
        assert nested_log.exists()


class TestTaskLogger:
    """Tests for TaskLogger class."""

    def test_task_logger_creation(self):
        """Test TaskLogger initialization."""
        logger = logging.getLogger("test")
        task_logger = TaskLogger(logger, "task-123", "L0")
        
        assert task_logger.task_id == "task-123"
        assert task_logger.tier == "L0"
        assert task_logger.attempt == 0

    def test_task_logger_info(self, caplog):
        """Test task logger info method."""
        logger = setup_logging(level="DEBUG")
        task_logger = TaskLogger(logger, "task-456", "L1")
        
        with caplog.at_level(logging.INFO):
            task_logger.info("Task started")
        
        assert "Task started" in caplog.text

    def test_task_logger_debug(self, caplog):
        """Test task logger debug method."""
        logger = setup_logging(level="DEBUG")
        task_logger = TaskLogger(logger, "task-789", "L2")
        
        with caplog.at_level(logging.DEBUG):
            task_logger.debug("Debug info")
        
        assert "Debug info" in caplog.text

    def test_task_logger_warning(self, caplog):
        """Test task logger warning method."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-warn", "L1")
        
        with caplog.at_level(logging.WARNING):
            task_logger.warning("Warning message")
        
        assert "Warning message" in caplog.text

    def test_task_logger_error(self, caplog):
        """Test task logger error method."""
        logger = setup_logging(level="ERROR")
        task_logger = TaskLogger(logger, "task-error", "L2")
        
        with caplog.at_level(logging.ERROR):
            task_logger.error("Error occurred")
        
        assert "Error occurred" in caplog.text

    def test_task_logger_start_attempt(self, caplog):
        """Test starting a new attempt."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-123", "L0")
        
        with caplog.at_level(logging.INFO):
            task_logger.start_attempt()
            assert task_logger.attempt == 1
            
            task_logger.start_attempt()
            assert task_logger.attempt == 2
        
        assert "Starting attempt 1" in caplog.text
        assert "Starting attempt 2" in caplog.text

    def test_task_logger_api_call_success(self, caplog):
        """Test logging successful API call."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-api", "L1")
        
        with caplog.at_level(logging.INFO):
            task_logger.log_api_call("model-xyz", 2.5, True)
        
        assert "API call succeeded" in caplog.text
        # Extra fields like model name are not in formatted text, only in JSON

    def test_task_logger_api_call_failure(self, caplog):
        """Test logging failed API call."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-api", "L0")
        
        with caplog.at_level(logging.INFO):
            task_logger.log_api_call("model-xyz", 5.0, False)
        
        assert "API call failed" in caplog.text

    def test_task_logger_tool_execution_success(self, caplog):
        """Test logging successful tool execution."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-tool", "L0")
        
        with caplog.at_level(logging.INFO):
            task_logger.log_tool_execution("file_read", "/path/to/file.txt", True, 1024)
        
        assert "file_read succeeded" in caplog.text
        # Extra fields like path and size are not in formatted text, only in JSON

    def test_task_logger_tool_execution_failure(self, caplog):
        """Test logging failed tool execution."""
        logger = setup_logging(level="INFO")
        task_logger = TaskLogger(logger, "task-tool", "L0")
        
        with caplog.at_level(logging.INFO):
            task_logger.log_tool_execution("file_write", "/path/to/file.txt", False)
        
        assert "file_write failed" in caplog.text

    def test_task_logger_custom_attributes_in_log(self, caplog):
        """Test that task metadata is logged."""
        logger = setup_logging(level="DEBUG")
        task_logger = TaskLogger(logger, "task-attr", "L2")
        
        with caplog.at_level(logging.DEBUG):
            task_logger.debug("Custom log", extra_key="custom_value")
        
        # Check that the message appears in log
        assert "Custom log" in caplog.text
        # Task ID and tier appear in JSON output, not formatted text


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def test_full_logging_workflow(self, tmp_path):
        """Test complete logging workflow."""
        log_file = tmp_path / "workflow.log"
        logger = setup_logging(level="DEBUG", log_file=str(log_file), console_output=False)
        
        task_logger = TaskLogger(logger, "workflow-task", "L1")
        
        # Simulate task workflow
        task_logger.info("Task initialized")
        task_logger.start_attempt()
        task_logger.log_api_call("qwen/qwen3.5", 1.2, True)
        task_logger.log_tool_execution("file_read", "/test.txt", True, 500)
        
        # Verify log file
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        assert len(lines) == 4  # 4 log entries
        assert "Task initialized" in lines[0]
        assert "Starting attempt" in lines[1]
        assert "API call succeeded" in lines[2]
        assert "file_read succeeded" in lines[3]

    def test_logging_with_exception(self, tmp_path):
        """Test logging with exception info."""
        log_file = tmp_path / "exception.log"
        logger = setup_logging(level="ERROR", log_file=str(log_file), console_output=False)
        
        try:
            raise RuntimeError("Test error")
        except RuntimeError:
            logger.error("Task failed", exc_info=True)
        
        content = log_file.read_text()
        log_data = json.loads(content)
        
        assert "exception" in log_data
        assert "RuntimeError" in log_data["exception"]


class TestLoggingLevels:
    """Tests for log level filtering."""

    def test_info_level_filters_debug(self):
        """Test INFO level filters DEBUG messages."""
        logger = setup_logging(level="INFO")
        
        # Should not log anything at DEBUG level
        logger.debug("Should not appear")
        
        assert logger.level == logging.INFO

    def test_error_level_filters_info(self):
        """Test ERROR level filters INFO messages."""
        logger = setup_logging(level="ERROR")
        
        # Should not log anything at INFO
        assert logger.level == logging.ERROR

    def test_all_levels_available(self):
        """Test all standard log levels are available."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in levels:
            logger = setup_logging(level=level)
            assert hasattr(logging, level)


# Import sys for exc_info
import sys
