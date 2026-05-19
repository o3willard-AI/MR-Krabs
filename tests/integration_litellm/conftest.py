"""Shared fixtures for integration testing LiteLLM adapters.

Provides isolated mock implementations of MR-Krabs core components:
- ask() — returns pre-configured responses
- vault — returns fake encrypted credentials  
- tier manager — controllable escalation outcomes
- session manager — no-op persistence
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, Optional


class MockMrKrabsCore:
    """Mock MR-Krabs core for isolated integration testing of LiteLLM adapters.
    
    Provides configurable mock implementations of:
    - ask() — returns pre-configured responses
    - vault — returns fake encrypted credentials
    - tier manager — controllable escalation outcomes
    - session manager — no-op persistence
    """
    
    def __init__(self):
        self._ask_responses = []
        self._ask_errors = []
        self._call_count = 0
        self._vault_data = {}
        self._budget_remaining = 10.00
        self._tier_results = {}  # task_type -> tier_name
    
    def queue_ask_response(self, response: Dict[str, Any]):
        """Queue a response that ask() will return on next call."""
        self._ask_responses.append(response)
    
    def queue_ask_error(self, error: Exception):
        """Queue an error that ask() will raise on next call."""
        self._ask_errors.append(error)
    
    def set_vault_entry(self, path: str, value: str):
        """Set a vault entry for testing."""
        self._vault_data[path] = value
    
    def set_budget(self, amount: float):
        """Set remaining budget."""
        self._budget_remaining = amount
    
    def set_tier_result(self, task_type: str, tier: str):
        """Configure which tier a task type escalates to."""
        self._tier_results[task_type] = tier
    
    def ask(self, task: str, **kwargs) -> Dict[str, Any]:
        """Mock ask() — returns queued response or sensible default."""
        self._call_count += 1
        if self._ask_errors:
            raise self._ask_errors.pop(0)
        if self._ask_responses:
            return self._ask_responses.pop(0)
        return {
            "output": f"Mock response for: {task[:50]}",
            "cost": 0.001,
            "success": True,
            "tier_used": "L0-Coder",
            "attempts": 1,
        }
    
    def get_budget_remaining(self) -> float:
        return self._budget_remaining
    
    def get_vault(self, path: str) -> Optional[str]:
        return self._vault_data.get(path)


@pytest.fixture
def mock_core():
    """Fixture providing a clean MockMrKrabsCore for each test."""
    return MockMrKrabsCore()


@pytest.fixture
def mock_config():
    """Fixture providing a minimal config dict for adapter testing."""
    return {
        "enable_prometheus_metrics": False,
        "enable_litellm_router": False,
        "enable_helm_deployment": False,
        "enable_bearer_auth": False,
        "enable_tracing": False,
        "enable_cache": False,
        "prometheus_port": 8001,
        "budget_daily_limit": 10.00,
    }


@pytest.fixture
def mock_config_with_metrics(mock_config):
    """Config with Prometheus metrics enabled."""
    config = mock_config.copy()
    config["enable_prometheus_metrics"] = True
    return config


@pytest.fixture
def mock_config_with_router(mock_config):
    """Config with SmartRouter enabled."""
    config = mock_config.copy()
    config["enable_litellm_router"] = True
    config["router_strategy"] = "smart"
    return config
