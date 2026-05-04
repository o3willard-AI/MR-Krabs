"""
Configuration module for MR-Krabs.
"""

from .retry import RetryConfig, RetryConfigFactory

__all__ = [
    "RetryConfig",
    "RetryConfigFactory",
]
