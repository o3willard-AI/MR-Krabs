"""
Error response strategies for cost-aware error handling.
Part of P4-3: Cost-Aware Error Handling.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.classifiers.error_classifier import ErrorClassification, ErrorCategory


class ResponseAction(Enum):
    """Response actions for error handling."""
    
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    """Retry with exponential backoff and optional jitter."""
    
    RETRY_AFTER_DELAY = "retry_after_delay"
    """Retry after a fixed delay (e.g., rate limit retry-after)."""
    
    RETRY_WITH_ESCALATION = "retry_with_escalation"
    """Retry with tier escalation if retries exhausted."""
    
    IMMEDIATE_ESCALATION = "immediate_escalation"
    """Immediately escalate to higher tier without retries."""
    
    FAIL_IMMEDIATELY = "fail_immediately"
    """Fail immediately without retries or escalation."""
    
    REVIEW_AND_DECIDE = "review_and_decide"
    """Requires manual review and decision."""


@dataclass
class ErrorResponseStrategy:
    """Strategy for handling errors based on classification and context."""
    
    action: ResponseAction
    """The response action to take."""
    
    max_retries: int = 0
    """Maximum number of retries before giving up or escalating."""
    
    base_delay: float = 0.0
    """Base delay in seconds before first retry."""
    
    max_delay: float = 30.0
    """Maximum delay cap for exponential backoff."""
    
    jitter: bool = True
    """Whether to add random jitter to delays."""
    
    escalate_after_retries: int = 0
    """Number of retries after which to escalate tier."""
    
    custom_params: dict = None
    
    def __post_init__(self):
        """Ensure custom_params is initialized."""
        if self.custom_params is None:
            self.custom_params = {}


class ErrorResponseStrategySelector:
    """
    Selects appropriate error response strategies based on:
    - Error classification category
    - Confidence score
    - Budget context
    - Estimated cost impact
    """
    
    # Default strategies by error category
    DEFAULT_STRATEGIES = {
        ErrorCategory.RETRYABLE_LOW_COST: ErrorResponseStrategy(
            action=ResponseAction.RETRY_WITH_BACKOFF,
            max_retries=5,
            base_delay=1.0,
            max_delay=30.0,
            jitter=True,
            escalate_after_retries=3
        ),
        ErrorCategory.RETRYABLE_HIGH_COST: ErrorResponseStrategy(
            action=ResponseAction.RETRY_WITH_BACKOFF,
            max_retries=3,
            base_delay=2.0,
            max_delay=60.0,
            jitter=True,
            escalate_after_retries=2
        ),
        ErrorCategory.ESCALATE_IMMEDIATELY: ErrorResponseStrategy(
            action=ResponseAction.IMMEDIATE_ESCALATION,
            max_retries=0,
            base_delay=0.0,
            max_delay=0.0,
            jitter=False,
            escalate_after_retries=0
        ),
        ErrorCategory.STATIC_FAILURE: ErrorResponseStrategy(
            action=ResponseAction.FAIL_IMMEDIATELY,
            max_retries=0,
            base_delay=0.0,
            max_delay=0.0,
            jitter=False,
            escalate_after_retries=0
        ),
    }
    
    # Budget threshold multipliers for retry counts
    BUDGET_MULTIPLIERS = {
        0.8: 1.0,  # >80% budget: full retries
        0.5: 0.5,  # 50-80% budget: half retries
        0.2: 0.25, # 20-50% budget: quarter retries
        0.0: 0.0,  # <20% budget: no retries
    }
    
    def __init__(self):
        """Initialize strategy selector with defaults."""
        self.strategies: dict = dict(self.DEFAULT_STRATEGIES)
    
    def get_response_strategy(
        self,
        classification: ErrorClassification,
        budget_remaining: float = 1.0
    ) -> ErrorResponseStrategy:
        """
        Select appropriate error response strategy.
        
        Args:
            classification: The error classification result
            budget_remaining: Fraction of budget remaining (0.0 to 1.0)
        
        Returns:
            ErrorResponseStrategy configured for this error and context
        """
        # Get base strategy for error category
        base_strategy = self.strategies.get(
            classification.category,
            self.DEFAULT_STRATEGIES[ErrorCategory.RETRYABLE_LOW_COST]
        )
        
        # Adjust strategy based on budget
        strategy = self._adjust_for_budget(base_strategy, classification, budget_remaining)
        
        return strategy
    
    def _adjust_for_budget(
        self,
        base_strategy: ErrorResponseStrategy,
        classification: ErrorClassification,
        budget_remaining: float
    ) -> ErrorResponseStrategy:
        """Adjust strategy based on budget context."""
        
        # Determine budget multiplier
        multiplier = self._get_budget_multiplier(budget_remaining)
        
        # Calculate adjusted retry count
        adjusted_max_retries = max(
            0,
            int(base_strategy.max_retries * multiplier)
        )
        
        # If budget is critically low, force immediate escalation
        if budget_remaining < 0.2:
            return ErrorResponseStrategy(
                action=ResponseAction.IMMEDIATE_ESCALATION,
                max_retries=0,
                base_delay=0.0,
                max_delay=0.0,
                jitter=False,
                escalate_after_retries=0
            )
        
        # For static failures, always fail immediately regardless of budget
        if classification.category == ErrorCategory.STATIC_FAILURE:
            return ErrorResponseStrategy(
                action=ResponseAction.FAIL_IMMEDIATELY,
                max_retries=0,
                base_delay=0.0,
                max_delay=0.0,
                jitter=False,
                escalate_after_retries=0
            )
        
        # Adjust max_retries based on budget
        adjusted_strategy = ErrorResponseStrategy(
            action=base_strategy.action,
            max_retries=adjusted_max_retries,
            base_delay=base_strategy.base_delay,
            max_delay=base_strategy.max_delay,
            jitter=base_strategy.jitter,
            escalate_after_retries=base_strategy.escalate_after_retries,
            custom_params=dict(base_strategy.custom_params)
        )
        
        return adjusted_strategy
    
    def _get_budget_multiplier(self, budget_remaining: float) -> float:
        """Get retry count multiplier based on budget remaining."""
        for threshold, multiplier in sorted(self.BUDGET_MULTIPLIERS.items(), reverse=True):
            if budget_remaining >= threshold:
                return multiplier
        return 0.0
    
    def get_retry_config(
        self,
        classification: ErrorClassification,
        budget_remaining: float = 1.0
    ) -> dict:
        """
        Get retry configuration dict for use with retry mechanisms.
        
        Args:
            classification: The error classification
            budget_remaining: Fraction of budget remaining
        
        Returns:
            Dict with max_retries, base_delay, max_delay, exponential_backoff, jitter
        """
        strategy = self.get_response_strategy(classification, budget_remaining)
        
        return {
            "max_retries": strategy.max_retries,
            "base_delay": strategy.base_delay,
            "max_delay": strategy.max_delay,
            "exponential_backoff": True,
            "jitter": strategy.jitter,
            "escalate_after_retries": strategy.escalate_after_retries
        }
