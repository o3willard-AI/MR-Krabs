from dataclasses import dataclass
from typing import Dict, Any
from src.core.failure_action import FailureAction

# Default tier configuration
TIER_FAILURE_DEFAULTS = {
    "L0-Coder": {"failure_action": "log_only", "max_retries": 3},
    "L1-Coder": {"failure_action": "notify_and_escalate", "max_retries": 3},
    "L2-Coder": {"failure_action": "notify_and_wait", "max_retries": 3},
    "L3-Coder": {"failure_action": "notify_and_wait", "max_retries": 2},
}

def get_tier_failure_action(tier: str) -> FailureAction:
    """Get the failure action for a specific tier."""
    config = TIER_FAILURE_DEFAULTS.get(tier, {})
    action_str = config.get("failure_action", "log_only")
    return FailureAction(action_str)

def get_tier_max_retries(tier: str) -> int:
    """Get the maximum retries for a specific tier."""
    config = TIER_FAILURE_DEFAULTS.get(tier, {})
    return config.get("max_retries", 3)