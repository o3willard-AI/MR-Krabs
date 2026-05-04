"""
Tests for RetryConfig (P4-3: Cost-Aware Error Handling)
"""

import pytest
from src.config.retry import RetryConfig, RetryConfigFactory


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_retry_config_basic(self):
        """Test basic RetryConfig creation."""
        config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
            exponential_backoff=True,
            jitter=True
        )
        
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_backoff is True
        assert config.jitter is True

    def test_retry_config_default_values(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_backoff is True
        assert config.jitter is True

    def test_retry_config_no_retries(self):
        """Test RetryConfig with zero retries."""
        config = RetryConfig(
            max_retries=0,
            base_delay=0.0,
            jitter=False
        )
        
        assert config.max_retries == 0
        assert config.base_delay == 0.0
        assert config.jitter is False


class TestRetryConfigFactory:
    """Test RetryConfigFactory for creating retry configs."""

    def test_create_config_for_low_cost_error(self):
        """Test creating retry config for low cost retryable errors."""
        factory = RetryConfigFactory()
        
        config = factory.create_config_for_error_category(
            category="retryable_low_cost",
            budget_remaining=0.8
        )
        
        assert config.max_retries >= 3
        assert config.base_delay > 0

    def test_create_config_for_high_cost_error(self):
        """Test creating retry config for high cost retryable errors."""
        factory = RetryConfigFactory()
        
        config = factory.create_config_for_error_category(
            category="retryable_high_cost",
            budget_remaining=0.8
        )
        
        assert config.max_retries <= 3
        assert config.base_delay >= 2.0

    def test_create_config_for_escalate_error(self):
        """Test creating retry config for escalate immediately errors."""
        factory = RetryConfigFactory()
        
        config = factory.create_config_for_error_category(
            category="escalate_immediately",
            budget_remaining=0.8
        )
        
        assert config.max_retries == 0

    def test_create_config_for_static_failure(self):
        """Test creating retry config for static failures."""
        factory = RetryConfigFactory()
        
        config = factory.create_config_for_error_category(
            category="static_failure",
            budget_remaining=0.8
        )
        
        assert config.max_retries == 0

    def test_create_config_budget_constrained(self):
        """Test retry config when budget is constrained."""
        factory = RetryConfigFactory()
        
        # With 15% budget remaining
        config = factory.create_config_for_error_category(
            category="retryable_low_cost",
            budget_remaining=0.15
        )
        
        # Should have minimal retries
        assert config.max_retries <= 1

    def test_create_config_budget_healthy(self):
        """Test retry config when budget is healthy."""
        factory = RetryConfigFactory()
        
        # With 95% budget remaining
        config = factory.create_config_for_error_category(
            category="retryable_low_cost",
            budget_remaining=0.95
        )
        
        # Should have full retries
        assert config.max_retries >= 5

    def test_get_default_configs(self):
        """Test getting all default retry configs."""
        factory = RetryConfigFactory()
        
        configs = factory.get_default_configs()
        
        assert len(configs) == 4  # All 4 categories
        assert "retryable_low_cost" in configs
        assert "retryable_high_cost" in configs
        assert "escalate_immediately" in configs
        assert "static_failure" in configs
