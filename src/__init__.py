"""Cost-Optimized AI Orchestrator — zero-config entry point.

Usage:
    from cost_orchestrator import ask
    result = ask("Write a Python function that sorts a list")
    print(result.output)
    print(f"Cost: ${result.cost:.4f}")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.core.cost import CostTracker, Budget, TokenCount, BudgetExceededError
from src.core.orchestrator import MODELS


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
    tokens: Optional[TokenCount] = None


_default_tracker: Optional[CostTracker] = None


def _get_default_tracker() -> CostTracker:
    """Get or create the default cost tracker with auto-detected budget."""
    global _default_tracker
    if _default_tracker is None:
        daily_limit = Decimal(os.environ.get("ORCHESTRATOR_DAILY_BUDGET", "10.00"))
        _default_tracker = CostTracker(budget=Budget(daily_limit_usd=daily_limit))
    return _default_tracker


def _get_default_model() -> str:
    """Return the default L0 model, preferring OpenRouter over LM Studio."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return "L0-Planner"
    if os.environ.get("LM_STUDIO_HOST"):
        return "L0-Coder"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "L0-Planner"
    raise EnvironmentError(
        "No LLM provider configured. Set OPENROUTER_API_KEY environment variable.\n"
        "Get a key at https://openrouter.ai/keys"
    )


def ask(
    prompt: str,
    system_prompt: Optional[str] = None,
    tier: Optional[str] = None,
    max_cost: Optional[float] = None,
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
    selected_tier = tier or _get_default_model()
    model_config = MODELS.get(selected_tier, {})
    model_name = model_config.get("model", "unknown")
    provider = model_config.get("provider", "unknown")

    if provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        raise EnvironmentError(
            "OPENROUTER_API_KEY not set. "
            "Set with: export OPENROUTER_API_KEY='your-key'"
        )

    from src.core.orchestrator import LLMOrchestrator

    orchestrator = LLMOrchestrator()
    sys_prompt = system_prompt or "You are a helpful assistant."

    result = orchestrator.call_llm(selected_tier, sys_prompt, prompt)

    tokens = TokenCount(
        prompt_tokens=len(prompt) // 4,
        completion_tokens=len(result) // 4,
    )

    cost = tracker.calculate_cost(model_name, tokens)

    if max_cost is not None and float(cost) > max_cost:
        raise BudgetExceededError(
            f"Estimated cost ${float(cost):.4f} exceeds max_cost ${max_cost:.4f}"
        )

    entry = tracker.record(
        task_id="ask",
        tier=selected_tier,
        model=model_name,
        tokens=tokens,
        duration=0.0,
    )

    return AskResult(
        output=result,
        cost=float(entry.cost_usd),
        tier=selected_tier,
        model=model_name,
        success=True,
        duration_seconds=0.0,
        attempts=1,
        tokens=tokens,
    )


def get_budget_remaining() -> float:
    """Get remaining daily budget in USD."""
    tracker = _get_default_tracker()
    summary = tracker.get_summary()
    return summary["budget_remaining"]


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
