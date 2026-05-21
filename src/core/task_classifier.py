"""Experimental heuristic task-type classifier.

Gated behind MRKRABS_ENABLE_HEURISTIC_CLASSIFIER=true.
When enabled, classifies tasks as "code" or "plan" based on
keyword matching. Explicit task_type in TaskSpec always wins.

This is EXPERIMENTAL. Behavior may change or be removed.
"""

import os
from typing import Optional

# ── Configuration ──────────────────────────────────────────────────

_HEURISTIC_ENABLED = os.environ.get("MRKRABS_ENABLE_HEURISTIC_CLASSIFIER", "").lower() in (
    "true", "1", "yes", "on"
)

# ── Keywords ───────────────────────────────────────────────────────

_PLAN_KEYWORDS = [
    "architecture", "design doc", "implementation plan", "tech spec",
    "system design", "component diagram", "data flow", "api design",
    "schema design", "migration plan", "roadmap", "phase 1", "phase 2",
    "planning", "proposal", "blueprint", "specification", "architect",
]

_CODE_KEYWORDS = [
    "implement", "write code", "fix bug", "add feature", "refactor",
    "patch", "debug", "optimize", "write function", "create module",
    "build endpoint", "add test", "fix test", "deploy", "release",
    "pr", "pull request", "commit", "merge",
]

_STRONG_PLAN_SIGNALS = [
    "architecture", "design doc", "implementation plan",
    "system design", "blueprint", "proposal",
]

_STRONG_CODE_SIGNALS = [
    "write code", "implement", "fix bug", "refactor",
    "pr", "pull request",
]


# ── Public API ──────────────────────────────────────────────────────

def classify_task(task_text: str, explicit_type: Optional[str] = None) -> str:
    """Classify a task as 'code' or 'plan'.

    Args:
        task_text: The task description / spec text.
        explicit_type: If set, returned immediately (no heuristic).

    Returns:
        'code' or 'plan'
    """
    # Explicit always wins
    if explicit_type in ("code", "plan"):
        return explicit_type

    # Heuristic is gated
    if not _HEURISTIC_ENABLED:
        return "code"  # safe default

    return _heuristic_classify(task_text)


def is_heuristic_enabled() -> bool:
    """Check if the experimental classifier is active."""
    return _HEURISTIC_ENABLED


def _heuristic_classify(task_text: str) -> str:
    """Keyword-based classification. Experimental — see module docstring."""
    text_lower = task_text.lower()

    # Count keyword matches
    plan_score = sum(1 for kw in _PLAN_KEYWORDS if kw in text_lower)
    code_score = sum(1 for kw in _CODE_KEYWORDS if kw in text_lower)

    # Strong signals get weighted
    plan_score += sum(2 for kw in _STRONG_PLAN_SIGNALS if kw in text_lower)
    code_score += sum(2 for kw in _STRONG_CODE_SIGNALS if kw in text_lower)

    if plan_score > code_score:
        return "plan"
    return "code"
