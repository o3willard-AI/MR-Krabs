"""Cost-Optimized AI Orchestrator — zero-config entry point.

Usage:
    from cost_orchestrator import ask
    result = ask("Write a Python function that sorts a list")
    print(result.output)
    print(f"Cost: ${result.cost:.4f}")
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional  # noqa: F401

from src.core.cost import Budget, BudgetExceededError, CostTracker, TokenCount
from src.core.orchestrator import MODELS, LLMOrchestrator


@dataclass
class AskResult:
    """Result from a simple ask() call."""

    output: str
    cost: float
    tier: str
    model: str
    success: bool
    duration_seconds: float
    attempts: int
    tokens: TokenCount | None = None


_default_tracker: CostTracker | None = None


def _get_default_tracker() -> CostTracker:
    """Get or create the default cost tracker with auto-detected budget."""
    global _default_tracker
    if _default_tracker is None:
        daily_limit = Decimal(os.environ.get("ORCHESTRATOR_DAILY_BUDGET", "10.00"))
        _default_tracker = CostTracker(budget=Budget(daily_limit_usd=daily_limit))
    return _default_tracker


def _get_available_tiers() -> list[str]:
    """Return list of tiers that have required environment variables."""
    available = []
    for tier, config in MODELS.items():
        provider = config.get("provider")
        if provider == "openrouter":
            if os.environ.get("OPENROUTER_API_KEY"):
                available.append(tier)
        elif provider == "lmstudio":
            # LM Studio doesn't require API key, just host
            # Check if host is set or default localhost works
            # We'll assume it's available; connection failure will be caught later
            available.append(tier)
        else:
            # Unknown provider, assume available
            available.append(tier)
    return available


def _get_default_tier() -> str:
    """Return the cheapest available tier."""
    available = _get_available_tiers()
    if not available:
        raise OSError(
            "No LLM provider configured. Set OPENROUTER_API_KEY environment variable.\n"
            "Get a key at https://openrouter.ai/keys"
        )
    # Prefer L0-Planner, then L0-Coder, then L0-Reviewer, then others
    preferred_order = [
        "L0-Planner",
        "L0-Coder",
        "L0-Reviewer",
        "L1-Coder",
        "L2-Coder",
        "L3-Coder",
        "L3-Architect",
    ]
    for tier in preferred_order:
        if tier in available:
            return tier
    # Fallback to first available
    return available[0]


def _estimate_tokens(prompt: str, system_prompt: str) -> TokenCount:
    """Estimate token counts for reservation."""
    # Rough approximation: 1 token ≈ 4 characters
    prompt_tokens = len(prompt) // 4 + len(system_prompt) // 4
    # Assume minimum completion of 200 tokens
    completion_tokens = 200
    return TokenCount(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def ask(
    prompt: str,
    system_prompt: str | None = None,
    tier: str | None = None,
    max_cost: float | None = None,
) -> AskResult:
    """Execute a prompt with cost optimization.

    This is the simplest entry point — no config file, no tier definitions,
    no infrastructure. Just pass a prompt and get a result.

    Args:
        prompt: The user prompt to send to the LLM.
        system_prompt: Optional system prompt. Defaults to a generic assistant role.
        tier: Optional tier override (e.g. "L0-Planner", "L1-Coder").
              Auto-detected from environment if not specified.
        max_cost: Optional per-task cost limit in USD.

    Returns:
        AskResult with output, cost, tier, model, and metadata.

    Raises:
        EnvironmentError: If no API key is configured.
        BudgetExceededError: If the daily budget is exceeded.
    """
    tracker = _get_default_tracker()
    selected_tier = tier or _get_default_tier()
    model_config = MODELS.get(selected_tier, {})
    model_name = str(model_config.get("model", "unknown"))
    provider = str(model_config.get("provider", "unknown"))

    if provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        raise OSError(
            "OPENROUTER_API_KEY not set. " "Set with: export OPENROUTER_API_KEY='your-key'"
        )

    sys_prompt = system_prompt or "You are a helpful assistant."
    temperature = float(model_config.get("temperature", 0.7))  # type: ignore

    # Estimate tokens and cost for reservation
    estimated_tokens = _estimate_tokens(prompt, sys_prompt)
    estimated_cost = tracker.calculate_cost(model_name, estimated_tokens)

    # Apply max_cost limit
    if max_cost is not None and float(estimated_cost) > max_cost:
        raise BudgetExceededError(
            f"Estimated cost ${float(estimated_cost):.4f} exceeds max_cost ${max_cost:.4f}"
        )

    # Reserve budget before execution (prevents race condition)
    reservation = tracker.reserve_budget(scope="ask", estimated_cost=estimated_cost)

    orchestrator = LLMOrchestrator()
    start_time = time.time()

    try:
        # Use call_llm_with_retry for retry logic and better metadata
        result = orchestrator.call_llm_with_retry(
            tier=selected_tier,
            system_prompt=sys_prompt,
            user_prompt=prompt,
            temperature=temperature,
        )
        duration = time.time() - start_time

        success = result.get("success", False)
        output = result.get("output", "")
        attempts = result.get("attempt", result.get("attempts", 1))

        if not success:
            # LLM call failed after retries, release reservation
            tracker.release_reservation(reservation.id)
            error_msg = result.get("error", "Unknown error")
            raise BudgetExceededError(f"LLM call failed: {error_msg}")

        # Calculate actual token usage (if available from API, otherwise estimate)
        prompt_tokens = result.get("prompt_tokens", len(prompt + sys_prompt) // 4)
        completion_tokens = result.get("completion_tokens", len(output) // 4)
        actual_tokens = TokenCount(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        actual_cost = tracker.calculate_cost(model_name, actual_tokens)

        # Finalize spending with actual cost
        entry = tracker.finalize_spending(reservation.id, actual_cost)

        return AskResult(
            output=output,
            cost=float(entry.cost_usd),
            tier=selected_tier,
            model=model_name,
            success=success,
            duration_seconds=duration,
            attempts=attempts,
            tokens=actual_tokens,
        )

    except Exception as e:
        # Release reservation on any other failure
        tracker.release_reservation(reservation.id)
        raise BudgetExceededError(f"Task failed: {e}") from e


def get_budget_remaining() -> float:
    """Get remaining daily budget in USD."""
    tracker = _get_default_tracker()
    summary = tracker.get_summary()
    return float(summary["budget_remaining"])


def get_cost_summary() -> dict:
    """Get current cost summary."""
    tracker = _get_default_tracker()
    return tracker.get_summary()


def reset_tracker() -> None:
    """Reset the default tracker (useful for testing)."""
    global _default_tracker
    _default_tracker = None


__all__ = [
    "ask",
    "AskResult",
    "get_budget_remaining",
    "get_cost_summary",
    "reset_tracker",
    "BudgetExceededError",
]
