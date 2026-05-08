"""
MR-Krabs E2E Tests - Configuration and Fixtures

This module provides shared fixtures for end-to-end tests that require
real LLM provider calls (OpenRouter).
"""

import os
import sys
import pytest
from typing import Optional


# Import from integration conftest to avoid duplication
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from integration.conftest import (
    get_openrouter_api_key,
    TEST_MODEL,
    BUDGET_LIMIT as DEFAULT_BUDGET,
    TEST_SERVER_URL,
)


@pytest.fixture(scope="session")
def openrouter_api_key() -> Optional[str]:
    """Session-scoped fixture for OpenRouter API key."""
    return get_openrouter_api_key()
