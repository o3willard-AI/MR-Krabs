"""
Tests for ErrorClassifier (P4-3: Cost-Aware Error Handling)
"""

from decimal import Decimal

import pytest
from src.classifiers.error_classifier import ErrorClassifier, ErrorClassification, ErrorCategory
from src.core.cost import Budget


# Custom error types for testing
class RateLimitError(Exception):
    pass


class TestErrorClassification:
    """Test ErrorClassification dataclass."""
    
    def test_error_classification_basic(self):
        """Test basic ErrorClassification creation."""
        classification = ErrorClassification(
            category=ErrorCategory.RETRYABLE_LOW_COST,
            confidence=0.95,
            estimated_cost_impact=0.01,
            suggested_action="retry"
        )
        
        assert classification.category == ErrorCategory.RETRYABLE_LOW_COST
        assert classification.confidence == 0.95
        assert classification.estimated_cost_impact == 0.01
        assert classification.suggested_action == "retry"

    def test_error_classification_default_values(self):
        """Test ErrorClassification with minimal required fields."""
        classification = ErrorClassification(
            category=ErrorCategory.ESCALATE_IMMEDIATELY,
            confidence=0.8
        )
        
        assert classification.category == ErrorCategory.ESCALATE_IMMEDIATELY
        assert classification.confidence == 0.8
        assert classification.estimated_cost_impact == 0.0
        assert classification.suggested_action == "unknown"  # Default value


class TestErrorClassifier:
    """Test ErrorClassifier class."""

    def test_classify_connection_error(self):
        """Test classification of connection errors as RETRYABLE_LOW_COST."""
        classifier = ErrorClassifier()
        
        class ConnectionError(Exception):
            pass
        
        error = ConnectionError("Connection refused")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.RETRYABLE_LOW_COST
        assert result.confidence >= 0.7
        assert result.estimated_cost_impact < 0.05

    def test_classify_rate_limit_error(self):
        """Test classification of rate limit errors as RETRYABLE_LOW_COST."""
        classifier = ErrorClassifier()
        
        class RateLimitError(Exception):
            pass
        
        error = RateLimitError("Rate limit exceeded. Retry after 60s")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.RETRYABLE_LOW_COST
        assert "retry" in result.suggested_action.lower()

    def test_classify_budget_exceeded_error(self):
        """Test classification of budget exceeded errors as ESCALATE_IMMEDIATELY."""
        classifier = ErrorClassifier()
        
        class BudgetExceededError(Exception):
            pass
        
        error = BudgetExceededError("Budget limit exceeded")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.ESCALATE_IMMEDIATELY
        assert "escalate" in result.suggested_action.lower() or "fail" in result.suggested_action.lower()

    def test_classify_auth_error(self):
        """Test classification of authentication errors as ESCALATE_IMMEDIATELY."""
        classifier = ErrorClassifier()
        
        class AuthError(Exception):
            pass
        
        error = AuthError("Invalid API key")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.ESCALATE_IMMEDIATELY

    def test_classify_model_context_error(self):
        """Test classification of context window errors as RETRYABLE_HIGH_COST."""
        classifier = ErrorClassifier()
        
        class ContextLengthError(Exception):
            pass
        
        error = ContextLengthError("Context window exceeded maximum tokens")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.RETRYABLE_HIGH_COST
        # These errors may succeed on retry with input reduction
        assert result.estimated_cost_impact >= 0.05

    def test_classify_invalid_input_error(self):
        """Test classification of invalid input as STATIC_FAILURE."""
        classifier = ErrorClassifier()
        
        class ValueError(Exception):
            pass
        
        error = ValueError("Invalid input format")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.STATIC_FAILURE
        assert "retry" not in result.suggested_action.lower()

    def test_classify_unknown_error(self):
        """Test classification of unknown error types."""
        classifier = ErrorClassifier()
        
        class UnknownError(Exception):
            pass
        
        error = UnknownError("Something went wrong")
        result = classifier.classify_error(error)
        
        # Unknown errors should default to conservative handling
        assert result.category in [ErrorCategory.RETRYABLE_LOW_COST, ErrorCategory.ESCALATE_IMMEDIATELY]
        assert result.confidence < 0.5  # Low confidence for unknown errors

    def test_classify_with_custom_rules(self):
        """Test custom error classification rules."""
        classifier = ErrorClassifier()
        
        # Add custom rule for specific error message pattern
        classifier.add_custom_rule(
            pattern="CUSTOM_ERROR",
            category=ErrorCategory.STATIC_FAILURE,
            confidence=0.95
        )
        
        class CustomError(Exception):
            pass
        
        error = CustomError("This is a CUSTOM_ERROR message")
        result = classifier.classify_error(error)
        
        assert result.category == ErrorCategory.STATIC_FAILURE
        assert result.confidence >= 0.9

    def test_classify_error_with_cost_context(self):
        """Test error classification with budget context."""
        classifier = ErrorClassifier()
        
        budget = Budget(
            daily_limit_usd=Decimal("10.00"),
            task_limit_usd=Decimal("1.00"),
            warn_thresholds=[Decimal("0.5"), Decimal("0.75"), Decimal("0.9")]
        )
        
        class ConnectionError(Exception):
            pass
        
        error = ConnectionError("Connection refused")
        result = classifier.classify_error(error, budget={"remaining": Decimal("0.1")})
        
        # Classification should still be RETRYABLE_LOW_COST but with lower estimated impact
        # when budget is constrained
        assert result.category == ErrorCategory.RETRYABLE_LOW_COST
        assert result.confidence >= 0.7


class TestErrorClassifierIntegration:
    """Test ErrorClassifier integration scenarios."""

    def test_classify_sequential_errors(self):
        """Test classifying multiple errors in sequence."""
        classifier = ErrorClassifier()
        
        errors = [
            ConnectionError("Connection refused"),
            ValueError("Invalid input"),
            RateLimitError("Too many requests"),
        ]
        
        classifications = [classifier.classify_error(e) for e in errors]
        
        assert classifications[0].category == ErrorCategory.RETRYABLE_LOW_COST
        assert classifications[1].category == ErrorCategory.STATIC_FAILURE
        assert classifications[2].category == ErrorCategory.RETRYABLE_LOW_COST

    def test_classify_error_hierarchy(self):
        """Test that error classification respects exception hierarchy."""
        classifier = ErrorClassifier()
        
        class NetworkError(Exception):
            pass
        
        class TimeoutError(NetworkError):
            pass
        
        # Test that subclass is classified consistently with parent
        parent_error = NetworkError("Network error")
        child_error = TimeoutError("Timeout")
        
        parent_result = classifier.classify_error(parent_error)
        child_result = classifier.classify_error(child_error)
        
        # Both should be classified similarly as network-related errors
        assert parent_result.category == child_result.category
