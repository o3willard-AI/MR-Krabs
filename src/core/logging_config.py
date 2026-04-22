#!/usr/bin/env python3
"""Structured JSON logging configuration."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id
        if hasattr(record, "tier"):
            log_data["tier"] = record.tier
        if hasattr(record, "attempt"):
            log_data["attempt"] = record.attempt
        if hasattr(record, "duration"):
            log_data["duration_ms"] = record.duration * 1000
        if hasattr(record, "model"):
            log_data["model"] = record.model
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Configure structured logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output
        console_output: Whether to output to console
    
    Returns:
        Configured logger
    """
    logger = logging.getLogger("orchestrator")
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers.clear()
    
    formatter = JSONFormatter()
    
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


class TaskLogger:
    """Logger wrapper for task-specific logging."""
    
    def __init__(self, logger: logging.Logger, task_id: str, tier: str):
        self.logger = logger
        self.task_id = task_id
        self.tier = tier
        self.attempt = 0
    
    def _extra(self, **kwargs) -> dict:
        return {
            "task_id": self.task_id,
            "tier": self.tier,
            "attempt": self.attempt,
            **kwargs
        }
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, extra=self._extra(**kwargs))
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, extra=self._extra(**kwargs))
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, extra=self._extra(**kwargs))
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, extra=self._extra(**kwargs))
    
    def start_attempt(self):
        self.attempt += 1
        self.info(f"Starting attempt {self.attempt}")
    
    def log_api_call(self, model: str, duration: float, success: bool):
        self.info(
            f"API call {'succeeded' if success else 'failed'}",
            model=model,
            duration=duration,
            success=success
        )
    
    def log_tool_execution(self, tool: str, path: str, success: bool, bytes_count: int = 0):
        self.info(
            f"Tool {tool} {'succeeded' if success else 'failed'}",
            tool=tool,
            path=path,
            success=success,
            bytes=bytes_count
        )
