"""
MR-Krabs Integration Tests - Configuration and Fixtures

This module provides shared fixtures and configuration for integration tests
that require real LLM provider calls (OpenRouter).

Test Skip Strategy:
- If OPENROUTER_API_KEY environment variable is not set, all integration tests skip
- If OPENROUTER_API_KEY is set but server is not running, tests report server errors
- Tests are designed to be safe and predictable even with real API calls

Configuration:
- Set OPENROUTER_API_KEY="your-key-here" to enable integration tests
- Set MCP_TEST_URL="http://localhost:8000" (default) for server URL
- Set INTEGRATION_TEST_MODEL="google/gemma-7b-it" (default cheapest model)
- Set BUDGET_LIMIT="1.0" (default $1 budget cap for integration tests)

Safety Features:
- Automatic test skip when API key missing
- Budget enforcement prevents unexpected costs
- Small token requests to minimize expenses
- Explicit cleanup of sessions after each test
"""

import os
import pytest
from typing import Generator, Optional, Dict


# ============================================================================
# TEST CONFIGURATION CONSTANTS
# ============================================================================

TEST_MODEL = os.getenv("INTEGRATION_TEST_MODEL", "google/gemma-7b-it")
"""Default test model - cheapest available on OpenRouter"""

BUDGET_LIMIT = float(os.getenv("INTEGRATION_BUDGET_LIMIT", "1.0"))
"""Maximum budget per integration test session (default $1.00)"""

TEST_SERVER_URL = os.getenv("MCP_TEST_URL", "http://localhost:8000")
"""MCP Server URL for integration tests"""


def get_openrouter_api_key() -> Optional[str]:
    """
    Get OpenRouter API key from environment or test file.
    
    Checks in order:
    1. OPENROUTER_API_KEY environment variable (preferred)
    2. tests/testllm.txt file (legacy method)
    
    Returns:
        API key string if found, None otherwise
    """
    # Method 1: Environment variable (preferred for CI/CD)
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key and api_key != "":
        return api_key
    
    # Method 2: Legacy test file
    test_key_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "testllm.txt"
    )
    try:
        with open(test_key_file, "r") as f:
            key = f.read().strip()
            if key and key != "":
                return key
    except FileNotFoundError:
        pass
    
    return None


def is_openrouter_available() -> bool:
    """Check if OpenRouter API is available for integration tests."""
    api_key = get_openrouter_api_key()
    return api_key is not None and api_key != ""


def require_integration(func):
    """
    Decorator to skip test function if integration requirements not met.
    
    Use this on test functions that need OpenRouter API access:
    
        @require_integration
        def test_something(self):
            ...
    
    Returns:
        Original function if ready, wrapped skip function otherwise
    """
    def wrapper(*args, **kwargs):
        if not is_openrouter_available():
            pytest.skip(
                "OpenRouter API key not configured. "
                "Set OPENROUTER_API_KEY environment variable to run integration tests."
            )
        return func(*args, **kwargs)
    return wrapper


# ============================================================================
# PYTEST FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def openrouter_api_key() -> Optional[str]:
    """
    Session-scoped fixture for OpenRouter API key.
    
    Returns:
        API key string or None if not configured
        
    Example:
        def test_llm_call(openrouter_api_key):
            assert openrouter_api_key is not None
            # Use API key for tests
    """
    return get_openrouter_api_key()


@pytest.fixture(autouse=True)
def skip_if_no_integration(openrouter_api_key: Optional[str]) -> None:
    """
    Auto-skip fixture that applies to all integration tests.
    
    If OpenRouter API key is not configured, automatically skips
    all tests in the module where this conftest.py is loaded.
    """
    if openrouter_api_key is None:
        pytest.skip(
            "Integration tests require OPENROUTER_API_KEY environment variable. "
            "Set it to run real LLM provider tests."
        )


@pytest.fixture(scope="function")
def test_config(openrouter_api_key: Optional[str]) -> Dict:
    """
    Function-scoped fixture providing standard test configuration.
    
    Returns:
        Dictionary with API key, model, budget limit, and server URL
        
    Example:
        def test_cost_estimate(test_config):
            api_key = test_config["api_key"]
            model = test_config["model"]
            budget = test_config["budget_limit"]
    """
    return {
        "api_key": openrouter_api_key,
        "model": TEST_MODEL,
        "budget_limit": BUDGET_LIMIT,
        "server_url": TEST_SERVER_URL,
        "enforcement_mode": "fail",  # Fail immediately on budget exceeded
        "warning_threshold": 90.0,   # Warn at 90%
        "default_tier": "L0",  # Use cheapest tier for tests
        "models": [TEST_MODEL],  # Restrict to test model
    }


@pytest.fixture(scope="function")
def test_prompt() -> str:
    """
    Simple, deterministic prompt for integration tests.
    
    Uses a basic arithmetic question to ensure predictable responses
    and minimal token usage.
    
    Returns:
        Simple prompt string (~10 tokens)
        
    Example:
        def test_llm_response(test_prompt):
            response = call_llm(prompt=test_prompt)
            assert "2" in response  # 1+1=2
    """
    return "What is 1 + 1? Answer with just the number."


@pytest.fixture(scope="function")
def test_budget_config() -> Dict:
    """
    Budget configuration for safe integration testing.
    
    Returns:
        Dictionary with budget limit, enforcement mode, and warning threshold
        
    Safety Features:
        - Low budget limit ($1.00) prevents runaway costs
        - "fail" mode stops execution if budget exceeded
        - High warning threshold (90%) for early alerts
    """
    return {
        "budget_limit": BUDGET_LIMIT,
        "enforcement_mode": "fail",  # Stop immediately on budget exceeded
        "warning_threshold": 90.0,  # Warn at 90%
        "default_tier": "L0",  # Use cheapest tier
        "models": [TEST_MODEL],  # Restrict to test model only
    }


@pytest.fixture(scope="function")
def safe_token_counts() -> Dict:
    """
    Conservative token count estimates for integration tests.
    
    Returns:
        Dictionary with input and output token limits
        
    Safety Features:
        - Small token counts minimize API costs
        - Realistic but conservative estimates
        - Designed to complete within budget limits
    """
    return {
        "input_tokens": 50,   # ~15-20 words prompt
        "output_tokens": 100,  # ~30-80 word response
        "max_input_tokens": 200,  # Hard limit
        "max_output_tokens": 500,  # Hard limit
    }


# ============================================================================
# MARKERS FOR INTEGRATION TESTS
# ============================================================================

def pytest_configure(config):
    """Register custom markers for integration tests."""
    config.addinivalue_line(
        "markers", 
        "integration: mark test as requiring OpenRouter API access"
    )
    config.addinivalue_line(
        "markers", 
        "slow: mark test as potentially slow (real LLM calls)"
    )
    config.addinivalue_line(
        "markers", 
        "costly: mark test as making actual API calls (may incur cost)"
    )


# ============================================================================
# HELPER FUNCTIONS FOR TEST SETUP
# ============================================================================

def setup_integration_environment() -> bool:
    """
    Prepare environment for integration tests.
    
    Ensures:
    - Required modules are available
    - Configuration is valid
    - Safety limits are in place
    
    Returns:
        True if environment ready, False otherwise
    """
    try:
        # Verify we can import required modules
        import requests
        from src.mcp.session_manager import SessionManager
        
        # Verify configuration
        if TEST_MODEL not in ["", None]:
            return True
            
        print(f"WARNING: Invalid test model configuration: {TEST_MODEL}")
        return False
        
    except ImportError as e:
        print(f"Missing required module: {e}")
        return False


def get_integration_skip_reason() -> str:
    """
    Get detailed reason why integration tests should be skipped.
    
    Returns:
        String explaining skip reason for test reports
    """
    if not is_openrouter_available():
        return (
            "OpenRouter API key not configured. "
            "Set OPENROUTER_API_KEY environment variable or "
            "place your key in tests/testllm.txt to enable integration tests."
        )
    
    if not setup_integration_environment():
        return "Integration test environment not properly configured"
    
    return None  # Tests should NOT be skipped
