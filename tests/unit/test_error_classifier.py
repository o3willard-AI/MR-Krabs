#!/usr/bin/env python3
"""Unit tests for error_classifier.py - Error classification logic.

P1-11: Unit tests for Phase 1 features
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.error_classifier import (
    ErrorCategory,
    ErrorAction,
    ERROR_CLASSIFICATION,
    ClassifiedError,
    FailureAnalyzer,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_category_values(self):
        """Test error category constant values."""
        assert ErrorCategory.TRANSIENT.value == "transient"
        assert ErrorCategory.RATE_LIMIT.value == "rate_limit"
        assert ErrorCategory.CONTEXT.value == "context"
        assert ErrorCategory.MODEL_CAPABILITY.value == "model_capability"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.AUTHENTICATION.value == "authentication"
        assert ErrorCategory.INFRASTRUCTURE.value == "infrastructure"
        assert ErrorCategory.BUDGET.value == "budget"
        assert ErrorCategory.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert ErrorCategory.TIMEOUT.value == "timeout"

    def test_all_categories_defined(self):
        """Test all categories are defined."""
        expected_categories = [
            "TRANSIENT",
            "RATE_LIMIT",
            "CONTEXT",
            "MODEL_CAPABILITY",
            "VALIDATION",
            "AUTHENTICATION",
            "INFRASTRUCTURE",
            "BUDGET",
            "CIRCUIT_BREAKER",
            "TIMEOUT",
        ]
        for category_name in expected_categories:
            assert hasattr(ErrorCategory, category_name)


class TestErrorAction:
    """Tests for ErrorAction enum."""

    def test_action_values(self):
        """Test action constant values."""
        assert ErrorAction.RETRY.value == "retry"
        assert ErrorAction.RETRY_WITH_DELAY.value == "retry_delay"
        assert ErrorAction.RETRY_SIMPLIFIED.value == "retry_simplified"
        assert ErrorAction.ESCALATE.value == "escalate"
        assert ErrorAction.FAIL.value == "fail"
        assert ErrorAction.SWITCH_PROVIDER.value == "switch_provider"

    def test_all_actions_defined(self):
        """Test all actions are defined."""
        expected_actions = [
            "RETRY",
            "RETRY_WITH_DELAY",
            "RETRY_SIMPLIFIED",
            "ESCALATE",
            "FAIL",
            "SWITCH_PROVIDER",
        ]
        for action_name in expected_actions:
            assert hasattr(ErrorAction, action_name)


class TestClassifiedError:
    """Tests for ClassifiedError dataclass."""

    def test_classified_error_creation(self):
        """Test creating a classified error."""
        error = ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            action=ErrorAction.RETRY,
            original_error=None,
        )

        assert error.category == ErrorCategory.TRANSIENT
        assert error.action == ErrorAction.RETRY
        assert error.original_error is None
        assert error.user_message == ""
        assert error.technical_details == ""

    def test_classified_error_with_details(self):
        """Test creating classified error with all fields."""
        original = ValueError("test error")
        error = ClassifiedError(
            category=ErrorCategory.VALIDATION,
            action=ErrorAction.RETRY_SIMPLIFIED,
            original_error=original,
            user_message="Custom message",
            technical_details="Detailed info",
        )

        assert error.category == ErrorCategory.VALIDATION
        assert error.action == ErrorAction.RETRY_SIMPLIFIED
        assert error.original_error == original
        assert error.user_message == "Custom message"
        assert error.technical_details == "Detailed info"

    def test_format_user_message(self):
        """Test formatting user message."""
        error = ClassifiedError(
            category=ErrorCategory.RATE_LIMIT,
            action=ErrorAction.RETRY_WITH_DELAY,
        )

        formatted = error.format_user_message()

        assert isinstance(formatted, str)
        assert len(formatted) > 0
        assert "rate" in formatted.lower() or "Rate" in formatted


class TestFailureAnalyzer:
    """Tests for FailureAnalyzer class."""

    def test_analyzer_initialization(self):
        """Test failure analyzer initialization."""
        analyzer = FailureAnalyzer()

        assert analyzer is not None

    def test_analyze_connection_error(self):
        """Test analyzing a ConnectionError."""
        analyzer = FailureAnalyzer()
        error = ConnectionError("Connection refused")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.TRANSIENT
        assert classified.action == ErrorAction.RETRY

    def test_analyze_rate_limit_error(self):
        """Test analyzing a RateLimitError."""
        analyzer = FailureAnalyzer()
        error = Exception("RateLimitError: Too many requests")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        # Should match via message pattern
        assert classified.category in [ErrorCategory.RATE_LIMIT, ErrorCategory.TRANSIENT]
        assert classified.action in [ErrorAction.RETRY_WITH_DELAY, ErrorAction.RETRY]

    def test_analyze_context_error(self):
        """Test analyzing a context length error."""
        analyzer = FailureAnalyzer()
        error = Exception("ContextLengthExceeded: Max tokens exceeded")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.CONTEXT
        assert classified.action == ErrorAction.RETRY_SIMPLIFIED

    def test_analyze_auth_error(self):
        """Test analyzing an authentication error."""
        analyzer = FailureAnalyzer()
        error = Exception("AuthenticationError: Invalid API key")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.AUTHENTICATION
        assert classified.action == ErrorAction.FAIL

    def test_analyze_budget_error(self):
        """Test analyzing a budget exceeded error."""
        analyzer = FailureAnalyzer()
        error = Exception("BudgetExceededError: Daily limit reached")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.BUDGET
        assert classified.action == ErrorAction.FAIL

    def test_analyze_5xx_error(self):
        """Test analyzing a 5xx server error."""
        analyzer = FailureAnalyzer()
        error = Exception("HTTP 500 Internal Server Error")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.TRANSIENT
        assert classified.action == ErrorAction.RETRY

    def test_analyze_unknown_error(self):
        """Test analyzing an unknown error defaults to TRANSIENT."""
        analyzer = FailureAnalyzer()
        error = Exception("Some random unknown error")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.TRANSIENT
        assert classified.action == ErrorAction.ESCALATE

    def test_analyze_with_http_status_429(self):
        """Test analyzing error with HTTP status 429."""
        analyzer = FailureAnalyzer()
        error = Exception("API Error (429 Too Many Requests)")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.RATE_LIMIT
        assert classified.action == ErrorAction.RETRY_WITH_DELAY

    def test_analyze_with_http_status_401(self):
        """Test analyzing error with HTTP status 401."""
        analyzer = FailureAnalyzer()
        error = Exception("API Error (401 Unauthorized)")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.AUTHENTICATION
        assert classified.action == ErrorAction.FAIL

    def test_analyze_with_http_status_403(self):
        """Test analyzing error with HTTP status 403."""
        analyzer = FailureAnalyzer()
        error = Exception("API Error (403 Forbidden)")

        classified = analyzer.analyze(error)

        assert isinstance(classified, ClassifiedError)
        assert classified.category == ErrorCategory.AUTHENTICATION
        assert classified.action == ErrorAction.FAIL

    def test_format_user_message_with_technical_details(self):
        """Test formatted message with technical details."""
        analyzer = FailureAnalyzer()
        error = ConnectionError("Connection refused at 127.0.0.1:8080")

        classified = analyzer.analyze(error)

        formatted = classified.format_user_message()

        assert isinstance(formatted, str)
        assert "Connection" in formatted or "connection" in formatted
        assert "Technical" in formatted or "Technical" in formatted or "Details" in formatted

    def test_classified_error_str(self):
        """Test string representation of ClassifiedError."""
        error = ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            action=ErrorAction.RETRY,
        )

        error_str = str(error)

        assert isinstance(error_str, str)
        assert len(error_str) > 0


class TestErrorClassification:
    """Tests for ERROR_CLASSIFICATION dictionary."""

    def test_classification_exists(self):
        """Test that ERROR_CLASSIFICATION has entries."""
        assert isinstance(ERROR_CLASSIFICATION, dict)
        assert len(ERROR_CLASSIFICATION) > 0

    def test_classification_structure(self):
        """Test that each classification entry has correct structure."""
        from core.error_classifier import ERROR_CLASSIFICATION

        for error_type, (category, action) in ERROR_CLASSIFICATION.items():
            assert isinstance(error_type, str)
            assert isinstance(category, ErrorCategory)
            assert isinstance(action, ErrorAction)

    def test_known_errors_classified(self):
        """Test that known error types are classified."""
        from core.error_classifier import ERROR_CLASSIFICATION

        assert "ConnectionError" in ERROR_CLASSIFICATION
        assert "TimeoutError" in ERROR_CLASSIFICATION
        assert "RateLimitError" in ERROR_CLASSIFICATION
        assert "ValidationError" in ERROR_CLASSIFICATION


class TestErrorMessagePatterns:
    """Tests for ERROR_MESSAGE_PATTERNS list."""

    def test_patterns_exist(self):
        """Test that error message patterns are defined."""
        from core.error_classifier import ERROR_MESSAGE_PATTERNS

        assert isinstance(ERROR_MESSAGE_PATTERNS, list)
        assert len(ERROR_MESSAGE_PATTERNS) > 0

    def test_pattern_structure(self):
        """Test that each pattern has correct structure."""
        from core.error_classifier import ERROR_MESSAGE_PATTERNS

        for pattern_entry in ERROR_MESSAGE_PATTERNS:
            assert len(pattern_entry) == 3
            pattern, category, action = pattern_entry
            assert isinstance(pattern, str)
            assert isinstance(category, ErrorCategory)
            assert isinstance(action, ErrorAction)


class TestUserFacingMessages:
    """Tests for USER_FACING_MESSAGES dictionary."""

    def test_messages_exist(self):
        """Test that user-facing messages are defined."""
        from core.error_classifier import USER_FACING_MESSAGES

        assert isinstance(USER_FACING_MESSAGES, dict)
        assert len(USER_FACING_MESSAGES) > 0

    def test_all_categories_have_messages(self):
        """Test that all error categories have user-facing messages."""
        from core.error_classifier import USER_FACING_MESSAGES, ErrorCategory

        for category in ErrorCategory:
            assert category in USER_FACING_MESSAGES
            messages = USER_FACING_MESSAGES[category]
            assert isinstance(messages, dict)
            assert "what" in messages
            assert "why" in messages
            assert "fix" in messages
