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


def _clean_feedback_for_coder(critique: str) -> str:
    """Strip judge coaching format, leaving plain fix instructions.

    The judge produces output like:
        COACHING REPLY:
        1. What was done well — ...
        2. What specific thing is wrong — ...
        3. Why it's wrong — ...
        4. How to fix it — ...
        5. What to verify after fixing — ...

    LLMs seeing this template in their context may interpret it as their
    output format and produce the template instead of code. We strip the
    coaching structure and keep only the substantive fix content.
    """
    if not critique:
        return ""

    text = critique.strip()

    # Strip the coaching reply header and its 5-point structure labels
    coaching_patterns = [
        (r'COACHING\s+REPLY\s*:\s*', ''),
        (r'PROVISIONALLY\s+ACCEPTED\.?\s*', ''),
        (r'1\.\s*What\s+was\s+done\s+well\s*[-—–]\s*', '✅ Kept: '),
        (r'2\.\s*What\s+specific\s+thing\s+is\s+wrong\s*[-—–]\s*', '❌ Issue: '),
        (r'3\.\s*Why\s+it\'?s?\s+wrong\s*[-—–]\s*', 'Cause: '),
        (r'4\.\s*How\s+to\s+fix\s+it\s*[-—–]\s*', 'Fix: '),
        (r'5\.\s*What\s+to\s+verify\s+after\s+fixing\s*[-—–]\s*', 'Verify: '),
        # Also catch the numbered list without coaching header
        (r'\*\*1\.\s*\*\*What\s+was\s+done\s+well', '✅ Kept:'),
        (r'\*\*2\.\s*\*\*What\s+specific', '❌ Issue:'),
        (r'\*\*3\.\s*\*\*Why', 'Cause:'),
        (r'\*\*4\.\s*\*\*How\s+to\s+fix', 'Fix:'),
        (r'\*\*5\.\s*\*\*What\s+to\s+verify', 'Verify:'),
    ]

    for pattern, replacement in coaching_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # If the critique is just the coaching template with no substance,
    # extract the actual issue from the task_spec context
    if len(text.strip()) < 50:
        return text.strip()

    return text.strip()


def _format_feedback(feedback_history: list[str]) -> str:
    """Format judge feedback for the coder, stripping coaching format.

    The Judge produces human-readable coaching replies with markdown headers
    and a 5-point structure. Sending these verbatim to another LLM causes
    prompt contamination — cloud models (especially via OpenCode) may interpret
    the coaching template as their output format and echo it back.

    This function strips the coaching structure and produces plain fix
    instructions suitable for coder consumption.
    """
    if not feedback_history:
        return ""

    cleaned = [_clean_feedback_for_coder(fb) for fb in feedback_history]

    if len(cleaned) <= MAX_CRITIQUE_HISTORY_VERBOSE:
        lines = []
        for i, fb in enumerate(cleaned, 1):
            lines.append(f"## Fixes Needed (Attempt {i})\n\n{fb}")
        return "\n\n".join(lines)

    older = cleaned[:-1]
    most_recent = cleaned[-1]

    summary_lines = ["## Previous Fix Attempts"]
    for i, fb in enumerate(older, 1):
        short = _summarize_critique(fb)
        summary_lines.append(f"- Attempt {i}: {short}")

    return (
        "\n".join(summary_lines)
        + "\n\n"
        + f"## Fixes Needed Now (Attempt {len(feedback_history)})\n\n"
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
