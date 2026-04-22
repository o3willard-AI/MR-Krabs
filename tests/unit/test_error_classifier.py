#!/usr/bin/env python3
"""Unit tests for error classifier."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.error_classifier import (
    FailureAnalyzer, ErrorCategory, ErrorAction, ClassifiedError,
    USER_FACING_MESSAGES,
)


class TestFailureAnalyzer:
    def test_connection_error(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(ConnectionError("Connection refused"))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.action == ErrorAction.RETRY

    def test_rate_limit_by_type(self):
        analyzer = FailureAnalyzer()
        from src.core.exceptions import RateLimitError
        result = analyzer.analyze(RateLimitError("Too many requests"))
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_rate_limit_by_message(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(RuntimeError("429 Too Many Requests"))
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_context_length(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(ValueError("Context length exceeded"))
        assert result.category == ErrorCategory.CONTEXT
        assert result.action == ErrorAction.RETRY_SIMPLIFIED

    def test_auth_error(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(PermissionError("Invalid API key"))
        assert result.category == ErrorCategory.AUTHENTICATION
        assert result.action == ErrorAction.FAIL

    def test_budget_error(self):
        analyzer = FailureAnalyzer()
        from src.core.cost import BudgetExceededError
        result = analyzer.analyze(BudgetExceededError("Budget exceeded"))
        assert result.category == ErrorCategory.BUDGET
        assert result.action == ErrorAction.FAIL

    def test_timeout_error(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(TimeoutError("Request timed out"))
        assert result.category == ErrorCategory.TIMEOUT

    def test_unknown_error_defaults_transient(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(RuntimeError("Something weird happened"))
        assert result.category == ErrorCategory.TRANSIENT

    def test_http_status_429(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(Exception("API returned 429"))
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_http_status_500(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(Exception("Server returned 502"))
        assert result.category == ErrorCategory.TRANSIENT

    def test_user_message_format(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze(ConnectionError("Connection refused"))
        msg = result.format_user_message()
        assert "Error:" in msg
        assert "Reason:" in msg
        assert "What to do:" in msg

    def test_all_categories_have_messages(self):
        for category in ErrorCategory:
            assert category in USER_FACING_MESSAGES
            assert "what" in USER_FACING_MESSAGES[category]
            assert "why" in USER_FACING_MESSAGES[category]
            assert "fix" in USER_FACING_MESSAGES[category]
