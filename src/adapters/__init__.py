"""Adapter interface package.

Provides the base adapter class and registry for LiteLLM-forked components.
"""

from .base_adapter import (
    HealthStatus,
    AdapterError,
    AdapterInitError,
    AdapterHealthError,
    AdapterConfigError,
    AdapterNotFound,
    LiteLLMAdapter,
)
from .registry import AdapterRegistry

__all__ = [
    "HealthStatus",
    "AdapterError",
    "AdapterInitError",
    "AdapterHealthError",
    "AdapterConfigError",
    "AdapterNotFound",
    "LiteLLMAdapter",
    "AdapterRegistry",
]
