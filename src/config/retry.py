"""
Retry configuration for error handling.
Part of P4-3: Cost-Aware Error Handling.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    max_retries: int = 3
    """Maximum number of retry attempts."""
    
    base_delay: float = 1.0
    """Base delay in seconds before first retry."""
    
    max_delay: float = 30.0
    """Maximum delay cap for exponential backoff."""
    
    exponential_backoff: bool = True
    """Whether to use exponential backoff (delay doubles each retry)."""
    
    jitter: bool = True
    """Whether to add random jitter to delays."""
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.
        
        Args:
            attempt: 0-indexed attempt number (0 = first retry)
        
        Returns:
            Delay in seconds
        """
        if not self.exponential_backoff:
            return self.base_delay
        
        # Exponential backoff: base_delay * 2^attempt
        delay = self.base_delay * (2 ** attempt)
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter if enabled
        if self.jitter:
            import random
            jitter_range = delay * 0.1  # +/- 10%
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.0, delay)  # Ensure non-negative


class RetryConfigFactory:
    """Factory for creating retry configurations based on error context."""
    
    # Default configs by error category
    DEFAULT_CONFIGS = {
        "retryable_low_cost": RetryConfig(
            max_retries=5,
            base_delay=1.0,
            max_delay=30.0,
            exponential_backoff=True,
            jitter=True
        ),
        "retryable_high_cost": RetryConfig(
            max_retries=3,
            base_delay=2.0,
            max_delay=60.0,
            exponential_backoff=True,
            jitter=True
        ),
        "escalate_immediately": RetryConfig(
            max_retries=0,
            base_delay=0.0,
            max_delay=0.0,
            exponential_backoff=False,
            jitter=False
        ),
        "static_failure": RetryConfig(
            max_retries=0,
            base_delay=0.0,
            max_delay=0.0,
            exponential_backoff=False,
            jitter=False
        )
    }
    
    # Budget multipliers for retry counts
    BUDGET_MULTIPLIERS = {
        0.8: 1.0,  # >80% budget: full retries
        0.5: 0.5,  # 50-80% budget: half retries
        0.2: 0.25, # 20-50% budget: quarter retries
        0.0: 0.0,  # <20% budget: no retries
    }
    
    def __init__(self):
        """Initialize factory with defaults."""
        self.configs: dict = dict(self.DEFAULT_CONFIGS)
    
    def create_config_for_error_category(
        self,
        category: str,
        budget_remaining: float = 1.0
    ) -> RetryConfig:
        """
        Create retry config based on error category and budget.
        
        Args:
            category: Error category string
            budget_remaining: Fraction of budget remaining (0.0 to 1.0)
        
        Returns:
            RetryConfig configured for this context
        """
        # Get base config for category
        base_config = self.configs.get(
            category,
            self.DEFAULT_CONFIGS["retryable_low_cost"]
        )
        
        # Adjust for budget
        config = self._adjust_for_budget(base_config, budget_remaining)
        
        return config
    
    def _adjust_for_budget(
        self,
        base_config: RetryConfig,
        budget_remaining: float
    ) -> RetryConfig:
        """Adjust retry config based on budget context."""
        
        # If budget is critically low, disable retries
        if budget_remaining < 0.2:
            return RetryConfig(
                max_retries=0,
                base_delay=0.0,
                max_delay=0.0,
                exponential_backoff=False,
                jitter=False
            )
        
        # Get budget multiplier
        multiplier = self._get_budget_multiplier(budget_remaining)
        
        # Calculate adjusted retry count
        adjusted_max_retries = max(
            0,
            int(base_config.max_retries * multiplier)
        )
        
        return RetryConfig(
            max_retries=adjusted_max_retries,
            base_delay=base_config.base_delay,
            max_delay=base_config.max_delay,
            exponential_backoff=base_config.exponential_backoff,
            jitter=base_config.jitter
        )
    
    def _get_budget_multiplier(self, budget_remaining: float) -> float:
        """Get retry count multiplier based on budget remaining."""
        for threshold, multiplier in sorted(self.BUDGET_MULTIPLIERS.items(), reverse=True):
            if budget_remaining >= threshold:
                return multiplier
        return 0.0
    
    def get_default_configs(self) -> dict:
        """Get all default retry configs."""
        return dict(self.configs)
