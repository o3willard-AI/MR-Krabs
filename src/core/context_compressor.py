#!/usr/bin/env python3
"""Context compression for the orchestrator's retry/escalation loop.

Implements Article Pillar 2: when context reaches a threshold of the
effective window, summarize older history, keep recent messages verbatim,
and preserve tool results that are still relevant.

Strategy:
  1. Task spec + system prompt — always preserved verbatim.
  2. Accumulated files list — compressed to counts when >5 files.
  3. Judge feedback history — summarized when >2 critiques,
     keeping only the most recent critique verbatim.
  4. Model profile prepend — preserved verbatim (small, high-value).
"""

from __future__ import annotations

import re
from typing import Optional


# ── Constants ──────────────────────────────────────────────────────────

MAX_ACCUMULATED_FILES_VERBATIM = 5   # switch to summary above this
MAX_CRITIQUE_HISTORY_VERBOSE = 2     # only keep the 2 most recent verbatim
MAX_CHARS_PER_CRITIQUE_SUMMARY = 120 # per-summarized-critique cap


# ── Public API ─────────────────────────────────────────────────────────


def compress_history(
    task_spec: str,
    accumulated_files: Optional[dict[str, int]] = None,
    feedback_history: Optional[list[str]] = None,
    prepend: str = "",
    max_total_chars: int = 8_000,
) -> str:
    """Compress the full retry context into a budget-controlled prompt.

    Args:
        task_spec: The original task specification (preserved verbatim).
        accumulated_files: path → byte_count from completed tiers.
        feedback_history: ordered list of judge critiques (oldest first).
        prepend: Model-profile prepend prompt (preserved verbatim).
        max_total_chars: Hard cap on the assembled prompt.

    Returns:
        An assembled, compressed prompt string.
    """
    parts: list[str] = []

    # 1. Prepend (model profile) — small, always include
    if prepend:
        parts.append(prepend)

    # 2. Task spec — always preserved
    parts.append(task_spec)

    # 3. Accumulated files — compress if many
    if accumulated_files:
        parts.append(_format_accumulated_files(accumulated_files))

    # 4. Feedback history — compress if long
    if feedback_history:
        parts.append(_format_feedback(feedback_history))

    # 5. Assemble and enforce hard cap
    combined = "\n\n".join(parts)
    if len(combined) <= max_total_chars:
        return combined

    # Emergency truncation from tail (shouldn't fire in normal operation)
    return combined[:max_total_chars - 50] + "\n\n[Context truncated to fit budget]"


# ── Internal helpers ───────────────────────────────────────────────────


def _format_accumulated_files(files: dict[str, int]) -> str:
    """Format the accumulated-files section, compressing when >5 files."""
    if not files:
        return ""

    header = "## Files Already Completed by Previous Tiers\n\n"

    if len(files) <= MAX_ACCUMULATED_FILES_VERBATIM:
        lines = [
            f"- {p} ({b} bytes) — COMPLETED, DO NOT REWRITE"
            for p, b in sorted(files.items())
        ]
        return header + "\n".join(lines) + "\n"

    # Compressed form: summary line + top-N
    total_bytes = sum(files.values())
    top_n = sorted(files.items(), key=lambda x: x[1], reverse=True)[
        :MAX_ACCUMULATED_FILES_VERBATIM
    ]
    top_lines = [
        f"- {p} ({b} bytes) — COMPLETED"
        for p, b in top_n
    ]
    remaining = len(files) - len(top_lines)
    return (
        f"{header}"
        f"{len(files)} files ({total_bytes:,} bytes total) already written "
        f"by previous tiers. DO NOT modify or rewrite any of them. "
        f"Largest files:\n"
        + "\n".join(top_lines)
        + f"\n... and {remaining} more.\n"
    )


def _format_feedback(feedback_history: list[str]) -> str:
    """Format judge feedback, summarizing older critiques."""
    if not feedback_history:
        return ""

    if len(feedback_history) <= MAX_CRITIQUE_HISTORY_VERBOSE:
        # All verbatim
        lines = []
        for i, fb in enumerate(feedback_history, 1):
            lines.append(f"## Previous Attempt {i} Feedback\n\n{fb}")
        return "\n\n".join(lines)

    # Summarize older critiques, keep most recent verbatim
    older = feedback_history[:-1]
    most_recent = feedback_history[-1]

    summary_lines = ["## Previous Attempt Summary"]
    for i, fb in enumerate(older, 1):
        short = _summarize_critique(fb)
        summary_lines.append(f"- Attempt {i}: {short}")

    return (
        "\n".join(summary_lines)
        + "\n\n"
        + f"## Most Recent Feedback (Attempt {len(feedback_history)})\n\n"
        + most_recent
    )


def _summarize_critique(critique: str) -> str:
    """Extract a one-line summary from a judge critique."""
    if not critique:
        return "No feedback provided."

    # Try to find the key issue: first sentence or first bullet
    # after "COACHING REPLY" or "PROVISIONALLY ACCEPTED" prefixes
    stripped = critique.strip()

    # Strip known prefixes
    for prefix in (
        "COACHING REPLY: ",
        "PROVISIONALLY ACCEPTED. ",
        "PROVISIONALLY ACCEPTED: ",
    ):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]

    # Take first sentence or first 120 chars
    first_sentence = re.split(r'[.!?]\s+', stripped)[0]
    if len(first_sentence) > MAX_CHARS_PER_CRITIQUE_SUMMARY:
        first_sentence = first_sentence[:MAX_CHARS_PER_CRITIQUE_SUMMARY - 3] + "..."

    return first_sentence


def estimate_context_fill(
    task_spec: str,
    accumulated_files: dict[str, int] | None = None,
    feedback_history: list[str] | None = None,
) -> float:
    """Estimate context fill ratio for observability (0.0–1.0).

    Uses a heuristic 32K token window. This is a rough estimate —
    not a tokenizer-accurate measurement — intended for the PipelineMonitor
    to surface context pressure before it causes problems.
    """
    total_chars = len(task_spec)
    if accumulated_files:
        total_chars += len(_format_accumulated_files(accumulated_files))
    if feedback_history:
        total_chars += len(_format_feedback(feedback_history))

    # Rough: 1 token ≈ 4 characters for English text
    estimated_tokens = total_chars / 4
    return min(estimated_tokens / 32_768, 1.0)
