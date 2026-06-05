"""Tier failure actions — loaded from config, with sensible defaults."""

import re

from src.core.failure_action import FailureAction


def get_tier_failure_action(tier: str) -> FailureAction:
    """Get the failure action for a specific tier.

    Reads from MrKrabsConfig.tier_failure_actions. Falls back to
    sensible defaults based on tier number:
      L0 → log_only
      L1 → notify_and_escalate
      L2+ → notify_and_wait

    Args:
        tier: Tier name (e.g. "L0-Coder", "l0-coder").

    Returns:
        FailureAction enum value.
    """
    from src.core.config_loader import get_config

    # Normalize key for config lookup
    norm_key = tier.lower().replace(" ", "-")
    config = get_config()
    action_str = config.get_failure_action(norm_key)

    if action_str != "log_only":
        return FailureAction(action_str)

    # Fall back to tier-number-based defaults
    match = re.match(r"l(\d+)", norm_key)
    if match:
        tier_num = int(match.group(1))
        if tier_num == 0:
            return FailureAction("log_only")
        elif tier_num == 1:
            return FailureAction("notify_and_escalate")
        else:
            return FailureAction("notify_and_wait")

    return FailureAction("log_only")


def get_tier_max_retries(tier: str) -> int:
    """Get the maximum retries for a specific tier.

    Reads from config workflows. Falls back to default (3).

    Args:
        tier: Tier name (e.g. "L0-Coder", "l0-coder").

    Returns:
        Max retries (default: 3).
    """
    from src.core.config_loader import get_config

    norm_key = tier.lower().replace(" ", "-")
    config = get_config()

    for wf in config.workflows.values():
        if norm_key in wf.tiers:
            return wf.max_retries_per_tier

    return 3
