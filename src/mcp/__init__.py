"""
MR-Krabs MCP Server Module

Model Context Protocol server for exposing MR-Krabs capabilities as reusable tools.
Supports HTTP transport with stateful session management and optional stateless mode.

Version: 0.2.0-dev
"""

from .session_manager import SessionManager, SessionConfig
from .budget_enforcer import BudgetEnforcer, EnforcementMode

# Phase 1: Cost Management Tools
from .cost_tools import (
    estimate_cost,
    CostEstimateRequest,
    CostEstimateResponse,
    BudgetCheckRequest,
    BudgetCheckResponse,
    CostTrackRequest,
    CostTrackResponse,
)

__version__ = "0.2.0-dev"
__all__ = [
    # Core components
    "SessionManager",
    "SessionConfig",
    "BudgetEnforcer",
    "EnforcementMode",
    # Phase 1: Cost management
    "estimate_cost",
    "CostEstimateRequest",
    "CostEstimateResponse",
    "BudgetCheckRequest",
    "BudgetCheckResponse",
    "CostTrackRequest",
    "CostTrackResponse",
]


# FastAPI app imported lazily to avoid hard dependency for core components
def _get_app():
    """Lazy import of FastAPI app."""
    try:
        from .server import app
        return app
    except ImportError as e:
        raise ImportError(
            f"FastAPI is required for server functionality: {e}. "
            f"Install with: pip install fastapi uvicorn"
        )


# Don't export 'app' directly to avoid import errors when FastAPI not available
