"""
Error classification module for cost-aware error handling.
Part of P4-3: Cost-Aware Error Handling.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import re


class ErrorCategory(Enum):
    """Categories of errors with their cost implications."""
    
    RETRYABLE_LOW_COST = "retryable_low_cost"
    """Transient errors with minimal cost impact (network, rate limits)."""
    
    RETRYABLE_HIGH_COST = "retryable_high_cost"
    """Errors that may succeed on retry but have moderate cost (context limits)."""
    
    ESCALATE_IMMEDIATELY = "escalate_immediately"
    """Errors that should escalate immediately (budget, auth)."""
    
    STATIC_FAILURE = "static_failure"
    """Errors that will never succeed on retry (invalid input)."""


@dataclass
class ErrorClassification:
    """Classification result for an error."""
    
    category: ErrorCategory
    """The category of this error."""
    
    confidence: float = 0.5
    """Confidence score from 0.0 to 1.0."""
    
    estimated_cost_impact: float = 0.0
    """Estimated cost impact of retrying this error (in USD)."""
    
    suggested_action: str = "unknown"
    """Suggested action based on classification."""
    
    error_message: Optional[str] = None
    """The original error message, if available."""
    
    custom_data: dict = field(default_factory=dict)
    """Additional custom data from classification rules."""
    
    def __post_init__(self):
        """Validate confidence is in range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")


class ErrorClassifier:
    """
    Classifies errors to determine appropriate error handling strategy.
    
    Considers:
    - Error type and hierarchy
    - Error message patterns
    - Budget context
    - Custom classification rules
    """
    
    # Default classification rules by error type
    DEFAULT_RULES = {
        # Network errors - retryable, low cost
        "ConnectionError": {
            "category": ErrorCategory.RETRYABLE_LOW_COST,
            "confidence": 0.9,
            "estimated_cost_impact": 0.01,
            "suggested_action": "retry_with_backoff"
        },
        "ConnectionRefusedError": {
            "category": ErrorCategory.RETRYABLE_LOW_COST,
            "confidence": 0.95,
            "estimated_cost_impact": 0.0,
            "suggested_action": "retry_with_backoff"
        },
        "TimeoutError": {
            "category": ErrorCategory.RETRYABLE_LOW_COST,
            "confidence": 0.85,
            "estimated_cost_impact": 0.02,
            "suggested_action": "retry_with_backoff"
        },
        # Rate limiting - retryable, low cost
        "RateLimitError": {
            "category": ErrorCategory.RETRYABLE_LOW_COST,
            "confidence": 0.9,
            "estimated_cost_impact": 0.0,
            "suggested_action": "retry_after_delay"
        },
        # HTTP 429 responses
        "TooManyRequestsError": {
            "category": ErrorCategory.RETRYABLE_LOW_COST,
            "confidence": 0.95,
            "estimated_cost_impact": 0.0,
            "suggested_action": "retry_after_delay"
        },
        # Budget errors - escalate immediately
        "BudgetExceededError": {
            "category": ErrorCategory.ESCALATE_IMMEDIATELY,
            "confidence": 1.0,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
        # Authentication errors - escalate
        "AuthenticationError": {
            "category": ErrorCategory.ESCALATE_IMMEDIATELY,
            "confidence": 0.95,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
        "AuthorizationError": {
            "category": ErrorCategory.ESCALATE_IMMEDIATELY,
            "confidence": 0.95,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
        # Token/context errors - retryable but high cost
        "ContextLengthError": {
            "category": ErrorCategory.RETRYABLE_HIGH_COST,
            "confidence": 0.8,
            "estimated_cost_impact": 0.1,
            "suggested_action": "retry_with_input_reduction"
        },
        "TokenLimitError": {
            "category": ErrorCategory.RETRYABLE_HIGH_COST,
            "confidence": 0.85,
            "estimated_cost_impact": 0.1,
            "suggested_action": "retry_with_input_reduction"
        },
        "ContextWindowExceededError": {
            "category": ErrorCategory.RETRYABLE_HIGH_COST,
            "confidence": 0.85,
            "estimated_cost_impact": 0.1,
            "suggested_action": "retry_with_input_reduction"
        },
        # Invalid input - static failure
        "ValueError": {
            "category": ErrorCategory.STATIC_FAILURE,
            "confidence": 0.7,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
        "TypeError": {
            "category": ErrorCategory.STATIC_FAILURE,
            "confidence": 0.7,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
        "ValidationError": {
            "category": ErrorCategory.STATIC_FAILURE,
            "confidence": 0.85,
            "estimated_cost_impact": 0.0,
            "suggested_action": "fail_immediately"
        },
    }
    
    # Message pattern rules (regex patterns to match error messages)
    DEFAULT_MESSAGE_PATTERNS = [
        # Budget patterns
        (r"(budget|limit).*(exceeded|exceed|over)", 
         ErrorCategory.ESCALATE_IMMEDIATELY, 0.9, 0.0, "fail_immediately"),
        
        # Auth patterns
        (r"(invalid.*api.*key|unauthorized|auth.*fail|forbidden)", 
         ErrorCategory.ESCALATE_IMMEDIATELY, 0.95, 0.0, "fail_immediately"),
        
        # Rate limit patterns
        (r"(rate.?limit|too.?many.?requests|429)", 
         ErrorCategory.RETRYABLE_LOW_COST, 0.9, 0.0, "retry_after_delay"),
        
        # Connection patterns
        (r"(connection.?refused|network.?error|connection.?reset|network.?unreachable)", 
         ErrorCategory.RETRYABLE_LOW_COST, 0.9, 0.0, "retry_with_backoff"),
        
        # Timeout patterns
        (r"(timeout|timed.?out|deadline.*exceeded)", 
         ErrorCategory.RETRYABLE_LOW_COST, 0.85, 0.02, "retry_with_backoff"),
        
        # Context/window patterns
        (r"(context.?window|token.?limit|maximum.*tokens|input.*too.?long)", 
         ErrorCategory.RETRYABLE_HIGH_COST, 0.85, 0.1, "retry_with_input_reduction"),
        
        # Invalid input patterns
        (r"(invalid.*format|unsupported.*parameter|schema.?error|validation.?error)", 
         ErrorCategory.STATIC_FAILURE, 0.85, 0.0, "fail_immediately"),
    ]
    
    def __init__(self):
        """Initialize classifier with default rules."""
        self.rules: dict = dict(self.DEFAULT_RULES)
        self.message_patterns: list[tuple] = [
            (re.compile(p, re.IGNORECASE), c, conf, cost, action)
            for p, c, conf, cost, action in self.DEFAULT_MESSAGE_PATTERNS
        ]
        self.custom_rules: list[tuple] = []  # (pattern, category, confidence)
    
    def add_custom_rule(
        self,
        pattern: str,
        category: ErrorCategory,
        confidence: float = 0.9,
        estimated_cost_impact: float = 0.0,
        suggested_action: str = "review"
    ) -> None:
        """
        Add a custom classification rule by message pattern.
        
        Args:
            pattern: Regex pattern to match in error message
            category: Category to assign when pattern matches
            confidence: Confidence score for this classification
            estimated_cost_impact: Estimated cost impact
            suggested_action: Suggested handling action
        """
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        self.custom_rules.append(
            (compiled_pattern, category, confidence, estimated_cost_impact, suggested_action)
        )
    
    def classify_error(
        self,
        error: Exception,
        budget: Optional[dict] = None
    ) -> ErrorClassification:
        """
        Classify an error to determine appropriate handling strategy.
        
        Args:
            error: The exception to classify
            budget: Optional budget context (with 'remaining' key)
        
        Returns:
            ErrorClassification with category, confidence, and suggested action
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Try exact error type match first
        if error_type in self.rules:
            rule = self.rules[error_type]
            return ErrorClassification(
                category=rule["category"],
                confidence=rule["confidence"],
                estimated_cost_impact=rule["estimated_cost_impact"],
                suggested_action=rule["suggested_action"],
                error_message=error_message
            )
        
        # Try exception hierarchy match
        for base_class in type(error).__bases__:
            base_name = base_class.__name__
            if base_name in self.rules:
                rule = self.rules[base_name]
                return ErrorClassification(
                    category=rule["category"],
                    confidence=rule["confidence"] * 0.9,  # Slightly lower confidence for inherited
                    estimated_cost_impact=rule["estimated_cost_impact"],
                    suggested_action=rule["suggested_action"],
                    error_message=error_message
                )
        
        # Try message pattern matching
        for pattern, category, confidence, cost, action in self.message_patterns:
            if pattern.search(error_message):
                return ErrorClassification(
                    category=category,
                    confidence=confidence,
                    estimated_cost_impact=cost,
                    suggested_action=action,
                    error_message=error_message
                )
        
        # Try custom rules
        for pattern, category, confidence, cost, action in self.custom_rules:
            if pattern.search(error_message):
                return ErrorClassification(
                    category=category,
                    confidence=confidence,
                    estimated_cost_impact=cost,
                    suggested_action=action,
                    error_message=error_message
                )
        
        # Default: conservative handling for unknown errors
        default_category = self._get_default_category(budget)
        return ErrorClassification(
            category=default_category,
            confidence=0.3,  # Low confidence for unknown errors
            estimated_cost_impact=0.05,
            suggested_action="review_and_decide",
            error_message=error_message
        )
    
    def _get_default_category(self, budget: Optional[dict]) -> ErrorCategory:
        """Get default error category based on budget context."""
        if budget:
            remaining = budget.get("remaining", 1.0)
            if remaining < 0.2:  # Less than 20% budget remaining
                # Very conservative when budget is nearly depleted
                return ErrorCategory.ESCALATE_IMMEDIATELY
            elif remaining < 0.5:  # Less than 50% budget remaining
                # Conservative but allow limited retries
                return ErrorCategory.RETRYABLE_LOW_COST
        
        # Default: allow retries for unknown errors
        return ErrorCategory.RETRYABLE_LOW_COST
    
    def get_retry_config_for_category(
        self,
        category: ErrorCategory,
        budget_remaining: float = 1.0
    ) -> dict:
        """
        Get retry configuration based on error category and budget.
        
        Args:
            category: The error category
            budget_remaining: Fraction of budget remaining (0.0 to 1.0)
        
        Returns:
            Retry configuration dict with max_retries, base_delay, etc.
        """
        # Base configs by category
        base_configs = {
            ErrorCategory.RETRYABLE_LOW_COST: {
                "max_retries": 5,
                "base_delay": 1.0,
                "max_delay": 30.0,
                "exponential_backoff": True,
                "jitter": True
            },
            ErrorCategory.RETRYABLE_HIGH_COST: {
                "max_retries": 3,
                "base_delay": 2.0,
                "max_delay": 60.0,
                "exponential_backoff": True,
                "jitter": True
            },
            ErrorCategory.ESCALATE_IMMEDIATELY: {
                "max_retries": 0,
                "base_delay": 0.0,
                "max_delay": 0.0,
                "exponential_backoff": False,
                "jitter": False
            },
            ErrorCategory.STATIC_FAILURE: {
                "max_retries": 0,
                "base_delay": 0.0,
                "max_delay": 0.0,
                "exponential_backoff": False,
                "jitter": False
            }
        }
        
        config = dict(base_configs[category])
        
        # Adjust for budget context
        if budget_remaining < 0.2:
            # Nearly depleted budget - minimal retries
            config["max_retries"] = 0
        elif budget_remaining < 0.5:
            # Moderate budget - reduce retries
            config["max_retries"] = max(1, config["max_retries"] // 2)
        elif budget_remaining < 0.8:
            # Good budget - moderate retries
            config["max_retries"] = max(2, config["max_retries"] // 2)
        
        return config
