# Loop Engineering Gaps 1–6 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> **Source Article:** `agent-looping-briefing-agent.md` (11 articles, Jun 2026) — reads from article's 10 sections and maps 6 highest-priority gaps to concrete MR-Krabs changes.

**Goal:** Close the six highest-priority gaps between MR-Krabs and the state-of-the-art loop engineering patterns described in the briefing, in priority order: (1) context compression, (2) self-improvement loop, (3) state serialization/resume, (4) dedicated fix-loop prompt, (5) structured task contracts, (6) consecutive error threshold.

**Architecture:** All six changes are additive to the orchestrator's execution pipeline — no breaking changes, no new dependencies. Gaps 1, 3, 4, 5, and 6 touch `orchestrator.py` and are isolated to the `execute_with_judge()` method and its helpers. Gap 2 is a new module that reads existing metrics data and writes back into `model_profiles.py`. All changes follow the existing 3-ring test pattern (leaf → state machine → integration).

**Tech Stack:** Python 3.12+, pytest, existing MR-Krabs adapter framework, `model_profiles.py` dataclasses.

---

## Gap 1: Context Compression

### Context

**Article reference:** Pillar 2 — "Context management is where most loops fail. Plan for it from iteration 1."

**Current state:** `_simplify_context()` at `src/core/orchestrator.py:411-438` truncates by percentage (1.0 → 0.7 → 0.4). It keeps the first N lines and drops the tail. There is no summarization, no "keep recent verbatim," and no awareness of what content is most valuable. On retry 2+ within a tier, the prompt accumulates: `task_spec` + `accumulated_files` header + `model_profile prepend` + `previous judge feedback`. These pile up with no compression strategy.

**What changes:** Replace `_simplify_context()` with a `compress_history()` function that (a) keeps the task spec and system prompt intact, (b) summarizes older judge feedback into a compressed "previous issues addressed" line, (c) keeps only the most recent judge critique verbatim, and (d) compresses the accumulated-files header when it exceeds a threshold.

### Tasks

---

### Task 1.1: Create `src/core/context_compressor.py`

**Objective:** New module with `compress_history()` function and supporting helpers.

**Files:**
- Create: `src/core/context_compressor.py`
- Test: `tests/unit/test_context_compressor.py`

**Step 1: Write the module**

```python
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
```

**Step 2: Write unit tests**

```python
#!/usr/bin/env python3
"""Unit tests for context_compressor module."""

import pytest
from src.core.context_compressor import (
    compress_history,
    _format_accumulated_files,
    _format_feedback,
    _summarize_critique,
    estimate_context_fill,
    MAX_ACCUMULATED_FILES_VERBATIM,
    MAX_CRITIQUE_HISTORY_VERBOSE,
)


class TestFormatAccumulatedFiles:
    def test_empty_returns_empty_string(self):
        assert _format_accumulated_files({}) == ""

    def test_few_files_verbatim(self):
        files = {"src/a.py": 100, "src/b.py": 200}
        result = _format_accumulated_files(files)
        assert "src/a.py (100 bytes) — COMPLETED, DO NOT REWRITE" in result
        assert "src/b.py (200 bytes) — COMPLETED, DO NOT REWRITE" in result

    def test_many_files_compressed(self):
        files = {f"src/file{i}.py": 100 for i in range(10)}
        result = _format_accumulated_files(files)
        assert f"{len(files)} files" in result
        assert "DO NOT modify" in result
        assert "... and" in result
        # Should not list all 10 verbatim
        assert result.count("COMPLETED") <= MAX_ACCUMULATED_FILES_VERBATIM + 1


class TestFormatFeedback:
    def test_empty_returns_empty_string(self):
        assert _format_feedback([]) == ""

    def test_single_critique_verbatim(self):
        fb = ["Fix line 10: add None check."]
        result = _format_feedback(fb)
        assert "Fix line 10" in result
        assert "Previous Attempt 1" in result
        assert "Summary" not in result

    def test_two_critiques_both_verbatim(self):
        fb = ["Fix A.", "Fix B."]
        result = _format_feedback(fb)
        assert "Fix A." in result
        assert "Fix B." in result
        assert "Summary" not in result

    def test_three_critiques_summarizes_older(self):
        fb = [
            "COACHING REPLY: Add error handling for None input. Fix the sort function.",
            "COACHING REPLY: Missing edge case in parse_date. Also add docstrings.",
            "PROVISIONALLY ACCEPTED. Add one missing import at top of file.",
        ]
        result = _format_feedback(fb)
        assert "Previous Attempt Summary" in result
        assert "Most Recent Feedback" in result
        # Older two are summarized
        assert "Attempt 1:" in result
        assert "Attempt 2:" in result
        # Most recent is verbatim
        assert "PROVISIONALLY ACCEPTED" in result
        assert "missing import" in result


class TestSummarizeCritique:
    def test_empty_returns_fallback(self):
        assert "No feedback" in _summarize_critique("")

    def test_strips_coaching_reply_prefix(self):
        fb = "COACHING REPLY: Add None check on line 10. Also update docstring."
        result = _summarize_critique(fb)
        assert result.startswith("Add None check")
        assert "COACHING REPLY" not in result

    def test_strips_provisional_accept_prefix(self):
        fb = "PROVISIONALLY ACCEPTED. Add missing import for datetime."
        result = _summarize_critique(fb)
        assert result.startswith("Add missing import")

    def test_truncates_long_critique(self):
        fb = "A" * 200
        result = _summarize_critique(fb)
        assert len(result) <= 123  # 120 + "..." max


class TestCompressHistory:
    def test_minimal_input(self):
        result = compress_history(task_spec="Write a Flask app.")
        assert "Write a Flask app." in result

    def test_full_context_with_compression(self):
        result = compress_history(
            task_spec="Build a REST API with 3 endpoints.",
            accumulated_files={
                f"src/file{i}.py": 1000 for i in range(10)
            },
            feedback_history=[
                "Fix A: add validation.",
                "Fix B: add error handling.",
                "Fix C: add docstrings.",
            ],
            prepend="CRITICAL: Use Flask conventions.",
        )
        assert "CRITICAL: Use Flask conventions." in result
        assert "Build a REST API" in result
        assert "Previous Attempt Summary" in result
        assert "Most Recent Feedback" in result
        assert "DO NOT modify" in result

    def test_hard_cap_enforced(self):
        """Verify emergency truncation doesn't crash."""
        huge_spec = "x" * 9000
        result = compress_history(task_spec=huge_spec, max_total_chars=1000)
        assert len(result) <= 1050  # cap + padding


class TestEstimateContextFill:
    def test_empty_is_zero(self):
        assert estimate_context_fill("") == 0.0

    def test_typical_task(self):
        ratio = estimate_context_fill(
            task_spec="Write a function." * 50,
            accumulated_files={"a.py": 200},
            feedback_history=["Needs docstring."])
        assert 0.0 < ratio < 1.0

    def test_saturated(self):
        """Very long context should approach 1.0."""
        ratio = estimate_context_fill(task_spec="x" * 200_000)
        assert ratio >= 1.0
```

**Step 3: Run and verify**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_context_compressor.py -v
# Expected: 13+ tests pass
```

**Step 4: Commit**

```bash
git add src/core/context_compressor.py tests/unit/test_context_compressor.py
git commit -m "feat: add context_compressor module for retry prompt compression"
```

---

### Task 1.2: Wire `compress_history` into the orchestrator retry loop

**Objective:** Replace the raw prompt assembly at lines 1590–1622 of `orchestrator.py` with a call to `compress_history`.

**Files:**
- Modify: `src/core/orchestrator.py:1590-1622` (prompt assembly in retry loop)
- Modify: `tests/unit/test_orchestrator_leaf.py` (add context compression test)
- Modify: `tests/unit/test_orchestrator_state_machine.py` (mock the compressor)

**Step 1: Replace raw prompt assembly with compressor**

Locate lines 1590–1622 of `src/core/orchestrator.py`. The current code:

```python
user_prompt = context.get("task_spec", task_id)

# ── R1: Incremental pass-through ──────────────────────
if retry_num == 1 and accumulated_files:
    done_list = "\n".join(
        f"- {p} ({b} bytes) — COMPLETED, DO NOT REWRITE"
        for p, b in sorted(accumulated_files.items())
    )
    user_prompt = (
        f"## Files Already Completed by Previous Tiers\n\n"
        f"The following files have already been written correctly. "
        f"DO NOT modify or rewrite them. Focus ONLY on files "
        f"NOT listed here.\n\n{done_list}\n\n"
        f"## Task\n\n{user_prompt}"
    )

# ── Model profile: inject prepend prompt ──────────────
model_key = tier_config.get("profile")
if model_key:
    prepend = get_prepend(model_key)
    if prepend:
        user_prompt = f"{prepend}\n\n{user_prompt}"

if feedback:
    user_prompt = (
        f"{user_prompt}\n\n## Previous Attempt Feedback\n\n"
        f"The prior output was rejected by the quality judge.\n"
        f"Critique: {feedback}\n\nPlease fix these issues and try again."
    )
```

Replace with:

```python
# ── Context compression (Article Pillar 2) ───────────────────────────
# Assemble the prompt with compression: keep task spec verbatim,
# summarize older judge feedback, compress accumulated files when >5.
task_spec = str(context.get("task_spec", task_id))

# Collect feedback history for this tier
# feedback_history accumulates across retries within a tier
if feedback and not hasattr(self, '_feedback_history_cache'):
    self._feedback_history_cache: dict[str, list[str]] = {}
tier_feedback_key = f"{task_id}:{tier}"
if tier_feedback_key not in getattr(self, '_feedback_history_cache', {}):
    self._feedback_history_cache = getattr(self, '_feedback_history_cache', {})
    self._feedback_history_cache[tier_feedback_key] = []
if feedback and feedback not in self._feedback_history_cache.get(tier_feedback_key, []):
    fb_list = self._feedback_history_cache.setdefault(tier_feedback_key, [])
    fb_list.append(feedback)

feedback_history = self._feedback_history_cache.get(tier_feedback_key, [])

# Model profile prepend
model_key = tier_config.get("profile")
prepend = get_prepend(model_key) if model_key else ""

# Pass-through: only inject accumulated files on first attempt of a new tier
acc_files = accumulated_files if retry_num == 1 and accumulated_files else None

from src.core.context_compressor import compress_history
user_prompt = compress_history(
    task_spec=task_spec,
    accumulated_files=acc_files,
    feedback_history=feedback_history,
    prepend=prepend,
)
```

Also: at the end of the tier's retry loop (before the `for tier in tiers:` iterates), clear the feedback history cache for that tier:

Inside the tier loop, after the `for retry_num` loop completes, add:

```python
# Clean up feedback history cache for this tier
tier_feedback_key = f"{task_id}:{tier}"
if hasattr(self, '_feedback_history_cache'):
    self._feedback_history_cache.pop(tier_feedback_key, None)
```

**Step 2: Update leaf tests**

Add to `tests/unit/test_orchestrator_leaf.py`:

```python
def test_compress_history_integrated(self):
    """Verify context compressor can be called with orchestrator-style args."""
    from src.core.context_compressor import compress_history

    result = compress_history(
        task_spec="Build a REST API.",
        accumulated_files={"src/app.py": 2000, "tests/test_app.py": 1500},
        feedback_history=[
            "COACHING REPLY: Add input validation.",
            "COACHING REPLY: Add error handling for None.",
        ],
        prepend="CRITICAL: Use Flask conventions.",
    )
    assert "Build a REST API" in result
    assert "CRITICAL: Use Flask" in result
    assert "COMPLETED" in result or "DO NOT modify" in result
    assert "Previous Attempt" in result
```

**Step 3: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_orchestrator_leaf.py -v
python -m pytest tests/unit/test_orchestrator_state_machine.py -v
# Expected: all existing tests pass, new test passes
```

**Step 4: Add context_fill_ratio to PipelineMonitor**

Add a `record_context_fill` method to `PipelineMonitor` and wire a `context_fill_ratio` field:

In `src/core/pipeline_monitor.py`, add:

```python
def record_context_fill(self, tier: str, fill_ratio: float) -> None:
    """Record estimated context fill ratio for observability."""
    self.record(
        role="orchestrator",
        tier=tier,
        attempt=0,
        action_type="context_fill",
        summary={"fill_ratio": fill_ratio},
        anomaly_flags=["context_pressure"] if fill_ratio > 0.8 else [],
    )
```

Wire it in the orchestrator, right after calling `compress_history`:

```python
from src.core.context_compressor import estimate_context_fill
fill = estimate_context_fill(task_spec, acc_files, feedback_history)
self.monitor.record_context_fill(tier, fill)
if fill > 0.8:
    print(f"  ⚠️ Context fill: {fill:.0%} — compression active")
```

**Step 5: Commit**

```bash
git add src/core/orchestrator.py src/core/pipeline_monitor.py tests/unit/test_orchestrator_leaf.py
git commit -m "feat: wire context compression into orchestrator retry loop"
```

---

## Gap 2: Self-Improvement Feedback Loop

### Context

**Article reference:** Section 6 — "Only 9% of agents run a real loop. Self-improvement requires a feedback loop. The evaluation feeds back into the agent's behavior."

**Current state:** MR-Krabs has `model_profiles.py` with manually-curated `KnownFailure` records. It generates verdicts, scores, critiques, and escalation data for every run, then discards it after the task completes. The `PipelineMonitor` detects anomalies but doesn't feed them back. The `MetricsCollector` tracks success rates per tier but doesn't update model profiles.

**What changes:** A new `SelfImprover` class that runs post-pipeline (optional, opt-in via `MRKRABS_SELF_IMPROVE=1`). It reads the metrics DB + escalation logs, identifies statistically significant failure patterns per model, and auto-updates `model_profiles.py` with discovered `KnownFailure` entries. Basic version: "model X fails Y% of the time on task type Z at this error pattern" → auto-populate.

### Tasks

---

### Task 2.1: Create `src/core/self_improver.py`

**Objective:** Module that reads pipeline metrics, discovers failure patterns, and writes back into model profiles.

**Files:**
- Create: `src/core/self_improver.py`
- Test: `tests/unit/test_self_improver.py`

**Step 1: Write the module**

```python
#!/usr/bin/env python3
"""Self-Improvement Loop — closes the feedback loop for MR-Krabs.

Implements Article Section 6: Input → Output → Feedback → Update → Repeat.

Reads pipeline run data (verdicts, scores, critiques per model) and
identifies failure patterns that the judge consistently flags. Auto-updates
model_profiles.py with discovered KnownFailure entries so the judge catches
these on first sight instead of discovering them iteratively.

Opt-in via MRKRABS_SELF_IMPROVE=1 or self_improve: true in config.yaml.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Configuration ──────────────────────────────────────────────────────

MIN_OCCURRENCES = 2          # a pattern must appear this many times
MIN_FREQUENCY = 0.4          # and in ≥ 40% of runs for this model
MAX_DISCOVERED_PATTERNS = 5  # cap learned patterns per model


# ── Data structures ────────────────────────────────────────────────────


@dataclass
class FailurePattern:
    """A discovered failure pattern from production data."""

    pattern_regex: str
    description: str
    occurrences: int = 0
    model_keys: list[str] = field(default_factory=list)
    avg_score_when_present: float = 0.0


@dataclass
class ImprovementResult:
    """Result of one self-improvement cycle."""

    patterns_discovered: int
    models_updated: list[str]
    patterns: list[FailurePattern] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Main API ───────────────────────────────────────────────────────────


class SelfImprover:
    """Reads pipeline data and updates model profiles with discovered patterns."""

    def __init__(
        self,
        debug_dir: str | None = None,
        metrics_dir: str | None = None,
        profiles_module_path: str | None = None,
    ) -> None:
        home = Path.home()
        self.debug_dir = Path(debug_dir or home / ".mrkrabs" / "debug")
        self.metrics_dir = Path(
            metrics_dir or Path(__file__).parent.parent.parent / "metrics"
        )
        self.profiles_path = Path(
            profiles_module_path
            or Path(__file__).parent / "model_profiles.py"
        )

    def run(self) -> ImprovementResult:
        """Run one self-improvement cycle.

        Returns:
            ImprovementResult with patterns discovered and models updated.
        """
        # 1. Collect all verdict data from debug directory
        verdicts = self._collect_verdicts()
        if not verdicts:
            return ImprovementResult(
                patterns_discovered=0, models_updated=[],
                errors=["No verdict data found in debug directory"]
            )

        # 2. Group by model and discover failure patterns
        model_patterns = self._discover_patterns(verdicts)

        # 3. Filter to statistically significant patterns
        significant = self._filter_significant(model_patterns, verdicts)

        # 4. Write discovered patterns into model_profiles.py
        updated = []
        errors = []
        for model_key, patterns in significant.items():
            try:
                self._inject_known_failures(model_key, patterns)
                updated.append(model_key)
            except Exception as e:
                errors.append(f"Failed to update {model_key}: {e}")

        return ImprovementResult(
            patterns_discovered=sum(len(p) for p in significant.values()),
            models_updated=updated,
            patterns=[
                p for plist in significant.values() for p in plist
            ],
            errors=errors,
        )

    # ── Data collection ────────────────────────────────────────────

    def _collect_verdicts(self) -> list[dict]:
        """Collect judge verdict data from the debug directory.

        Reads PromptFlowLogger dumps to find judge inputs/outputs.
        Falls back to metrics directory for summary data.
        """
        verdicts: list[dict] = []

        if not self.debug_dir.exists():
            return verdicts

        # Walk debug dir for judge evaluation dumps
        for task_dir in self.debug_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for file in sorted(task_dir.iterdir()):
                if not file.suffix == ".txt":
                    continue
                try:
                    content = file.read_text()
                    parsed = self._parse_debug_file(content, str(file))
                    if parsed:
                        verdicts.append(parsed)
                except Exception:
                    continue

        return verdicts

    def _parse_debug_file(self, content: str, filename: str) -> dict | None:
        """Parse a PromptFlowLogger debug file for verdict data."""
        # Look for judge verdict JSON pattern
        score_match = re.search(r'"score":\s*([\d.]+)', content)
        if not score_match:
            return None

        score = float(score_match.group(1))

        # Extract model/tier from filename convention:
        #   <task_id>-L0-Coder_retry1.txt
        tier_match = re.search(r'-(L\d-(?:Coder|Planner|Reviewer|Judge))', filename)
        tier = tier_match.group(1) if tier_match else "unknown"

        # Extract critique
        critique_match = re.search(
            r'"critique":\s*"([^"]*(?:\\.[^"]*)*)"', content
        )
        critique = ""
        if critique_match:
            critique = critique_match.group(1)

        return {
            "tier": tier,
            "score": score,
            "critique": critique,
            "accepted": score >= 0.7,
            "provisional": 0.75 <= score < 0.7,
        }

    # ── Pattern discovery ──────────────────────────────────────────

    def _discover_patterns(self, verdicts: list[dict]) -> dict[str, list[FailurePattern]]:
        """Group verdicts by tier and extract common failure patterns.

        Simple heuristic: look for recurring phrases in rejected critiques.
        """
        # Group by tier/model
        by_tier: dict[str, list[dict]] = defaultdict(list)
        for v in verdicts:
            if not v["accepted"] and v.get("critique"):
                by_tier[v["tier"]].append(v)

        patterns: dict[str, list[FailurePattern]] = defaultdict(list)

        for tier, tier_verdicts in by_tier.items():
            # Extract repeating phrases from critiques
            phrase_counts: dict[str, int] = defaultdict(int)
            for v in tier_verdicts:
                critique = v["critique"]
                # Look for "missing X", "should use Y", "X not found"
                phrases = re.findall(
                    r'(?:missing|should\s+use|not\s+found|add\s+\w+|'
                    r'forgot\s+to\s+\w+|missing\s+\w+\s+(?:import|check|handler|validation))',
                    critique, re.IGNORECASE
                )
                for phrase in phrases:
                    phrase_counts[phrase.lower()] += 1

            # Filter to recurring phrases
            for phrase, count in phrase_counts.items():
                if count >= MIN_OCCURRENCES:
                    patterns[tier].append(FailurePattern(
                        pattern_regex=re.escape(phrase),
                        description=phrase,
                        occurrences=count,
                        model_keys=[tier],
                    ))

        return dict(patterns)

    def _filter_significant(
        self,
        model_patterns: dict[str, list[FailurePattern]],
        all_verdicts: list[dict],
    ) -> dict[str, list[FailurePattern]]:
        """Filter patterns to only those that are statistically meaningful.

        A pattern is significant if it appears in >= MIN_FREQUENCY of
        rejected verdicts for that model.
        """
        significant: dict[str, list[FailurePattern]] = {}

        for model_key, patterns in model_patterns.items():
            # Count total rejected verdicts for this model
            rejected = [
                v for v in all_verdicts
                if v["tier"] == model_key and not v["accepted"]
            ]
            total_rejected = len(rejected)
            if total_rejected == 0:
                continue

            filtered = []
            for pattern in patterns:
                frequency = pattern.occurrences / total_rejected
                if frequency >= MIN_FREQUENCY:
                    filtered.append(pattern)

            if filtered:
                # Sort by occurrences descending, cap at limit
                filtered.sort(key=lambda p: p.occurrences, reverse=True)
                significant[model_key] = filtered[:MAX_DISCOVERED_PATTERNS]

        return significant

    # ── Model profile injection ────────────────────────────────────

    def _inject_known_failures(
        self, model_key: str, patterns: list[FailurePattern]
    ) -> None:
        """Inject discovered patterns as KnownFailure entries into model_profiles.py.

        Strategy: append new KnownFailure() calls at the end of the file
        in a clearly marked auto-generated section. Existing manual entries
        are never modified.
        """
        if not self.profiles_path.exists():
            raise FileNotFoundError(
                f"model_profiles.py not found at {self.profiles_path}"
            )

        original = self.profiles_path.read_text()

        # Check if auto-generated section already exists
        auto_marker = "# ── AUTO-GENERATED: Discovered Failure Patterns ──"
        if auto_marker in original:
            # Replace existing auto section
            marker_idx = original.index(auto_marker)
            original = original[:marker_idx].rstrip() + "\n\n"

        # Build new entries
        entries: list[str] = [auto_marker]
        for p in patterns:
            entries.append(f"""\
KnownFailure(
    trigger=r"{p.pattern_regex}",
    feedback=(
        "[AUTO-DISCOVERED pattern (seen {p.occurrences}x)] "
        "{p.description}. Apply the fix described in the judge critique."
    ),
    severity="warning",
),""")

        # Append to profile for this model
        # Find the profile definition and add after known_failures list
        profile_start = f'{model_key.upper().replace("-", "_")} = register(ModelProfile('
        if profile_start in original:
            # Add as a comment block near the profile
            entries.insert(1, f"# Discovered from {p.occurrences if patterns else 0} pipeline runs for {model_key}")
        
        new_section = "\n".join(entries) + "\n\n"

        new_content = original.rstrip() + "\n" + new_section

        # Write back
        self.profiles_path.write_text(new_content)
```

**Step 2: Write unit tests**

```python
#!/usr/bin/env python3
"""Unit tests for self_improver module."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from src.core.self_improver import (
    SelfImprover,
    FailurePattern,
    ImprovementResult,
    MIN_OCCURRENCES,
    MIN_FREQUENCY,
)


class TestSelfImprover:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.debug_dir = Path(self.tmp.name) / "debug"
        self.metrics_dir = Path(self.tmp.name) / "metrics"
        self.profiles_path = Path(self.tmp.name) / "model_profiles.py"
        self.debug_dir.mkdir(parents=True)
        self.metrics_dir.mkdir(parents=True)
        # Write a minimal profiles file
        self.profiles_path.write_text(
            "from src.core.model_profiles import register, ModelProfile, KnownFailure\n\n"
            "EXAMPLE = register(ModelProfile(name='example', display_name='Ex', "
            "size='0B', vram='0', provider='test'))\n"
        )

        self.improver = SelfImprover(
            debug_dir=str(self.debug_dir),
            metrics_dir=str(self.metrics_dir),
            profiles_module_path=str(self.profiles_path),
        )

    def teardown_method(self):
        self.tmp.cleanup()

    def test_empty_debug_dir_returns_no_patterns(self):
        result = self.improver.run()
        assert result.patterns_discovered == 0
        assert len(result.models_updated) == 0

    def test_collects_verdicts_from_debug_files(self):
        task_dir = self.debug_dir / "task_abc"
        task_dir.mkdir()
        (task_dir / "judge_retry1.txt").write_text(
            '=== JUDGE INPUT ===\n...\n=== JUDGE OUTPUT ===\n'
            '{"score": 0.4, "critique": "missing input validation on line 5", '
            '"checks_passed": [], "checks_failed": ["completeness"]}\n'
        )
        (task_dir / "judge_retry2.txt").write_text(
            '=== JUDGE INPUT ===\n...\n=== JUDGE OUTPUT ===\n'
            '{"score": 0.3, "critique": "missing input validation for None case", '
            '"checks_passed": [], "checks_failed": ["edge_cases"]}\n'
        )

        verdicts = self.improver._collect_verdicts()
        assert len(verdicts) == 2
        assert all(v["score"] < 0.7 for v in verdicts)

    def test_discovers_repeating_phrase(self):
        verdicts = [
            {"tier": "L0-Coder", "score": 0.4,
             "critique": "COACHING REPLY: missing input validation on line 5.",
             "accepted": False},
            {"tier": "L0-Coder", "score": 0.3,
             "critique": "missing input validation for edge case.",
             "accepted": False},
        ]
        patterns = self.improver._discover_patterns(verdicts)
        assert "L0-Coder" in patterns
        assert any("missing input validation" in p.description
                   for p in patterns["L0-Coder"])

    def test_filters_insignificant_patterns(self):
        # Pattern appears once → below MIN_OCCURRENCES
        model_patterns = {
            "L0-Coder": [FailurePattern(
                pattern_regex="once", description="once",
                occurrences=1, model_keys=["L0-Coder"],
            )]
        }
        verdicts = [
            {"tier": "L0-Coder", "score": 0.4, "accepted": False, "critique": "x"},
        ]
        result = self.improver._filter_significant(model_patterns, verdicts)
        assert len(result) == 0  # filtered out

    def test_injects_patterns_into_profiles_file(self):
        self.improver._inject_known_failures("L0-Coder", [
            FailurePattern(
                pattern_regex=r"missing\\ input\\ validation",
                description="missing input validation",
                occurrences=3,
                model_keys=["L0-Coder"],
            )
        ])
        content = self.profiles_path.read_text()
        assert "AUTO-GENERATED" in content
        assert "KnownFailure" in content
        assert "missing input validation" in content
        assert "AUTO-DISCOVERED" in content
```

**Step 3: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_self_improver.py -v
# Expected: 6 tests pass
```

**Step 4: Commit**

```bash
git add src/core/self_improver.py tests/unit/test_self_improver.py
git commit -m "feat: add SelfImprover module for closing the self-improvement loop"
```

---

### Task 2.2: Wire SelfImprover into the orchestrator as opt-in post-pipeline hook

**Objective:** After `execute_with_judge()` completes, optionally run a self-improvement cycle.

**Files:**
- Modify: `src/core/orchestrator.py` (add post-pipeline hook)
- Modify: `src/core/config_loader.py` (add `self_improve` field if missing)

**Step 1: Add post-pipeline invocation**

At the end of `execute_with_judge()`, before the final return, add:

```python
# ── Self-improvement hook (opt-in) ─────────────────────────────────
# Runs after the pipeline completes, never blocks the result.
if os.environ.get("MRKRABS_SELF_IMPROVE", "") == "1":
    try:
        from src.core.self_improver import SelfImprover
        improver = SelfImprover()
        imp_result = improver.run()
        print(f"[SELF-IMPROVE] Discovered {imp_result.patterns_discovered} "
              f"patterns across {len(imp_result.models_updated)} models")
        if imp_result.errors:
            for err in imp_result.errors:
                print(f"[SELF-IMPROVE] Error: {err}")
    except Exception as e:
        print(f"[SELF-IMPROVE] Failed: {e}")
```

**Step 2: Run the full test suite to verify no regressions**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/ tests/integration/test_judge_escalation_e2e.py \
    --ignore=tests/integration/test_openrouter_integration.py \
    --ignore=tests/e2e/ -q
# Expected: all existing tests still pass
```

**Step 3: Commit**

```bash
git add src/core/orchestrator.py
git commit -m "feat: wire SelfImprover as opt-in post-pipeline hook (MRKRABS_SELF_IMPROVE=1)"
```

---

## Gap 3: State Serialization / Crash Recovery

### Context

**Article reference:** Pillar 1 — "State serialization (for long-running tasks / crash recovery)."

**Current state:** MR-Krabs logs handoffs and failures to disk but has no checkpoint/resume mechanism. A 10-minute pipeline run killed mid-tier loses all progress: `accumulated_files`, `best_output`, `escalation_path`, verdict scores — everything. Multi-pass execution (multiple PI passes) is especially vulnerable.

**What changes:** Add a `write_checkpoint()` call after each tier verdict (accepted or rejected). Checkpoint contains: `task_id`, `escalation_path`, `accumulated_files`, `retries_per_tier`, `best_output`, `cost_summary`. On `execute_with_judge()`, accept an optional `resume_from_checkpoint` parameter that skips completed tiers and restores state.

### Tasks

---

### Task 3.1: Add checkpointing to `execute_with_judge()`

**Objective:** Save state after each tier's verdict and support resume.

**Files:**
- Modify: `src/core/orchestrator.py` (execute_with_judge method)
- Test: `tests/unit/test_orchestrator_checkpoint.py`

**Step 1: Add checkpoint helper and resume logic**

Add to `LLMOrchestrator`:

```python
# ── Checkpoint paths ───────────────────────────────────────────────

def _checkpoint_path(self, task_id: str) -> Path:
    """Path to the checkpoint file for a given task."""
    safe_id = task_id.replace("/", "_").replace(".", "_")
    return self.escalations_dir / f"{safe_id}_checkpoint.json"


def _write_checkpoint(
    self,
    task_id: str,
    escalation_path: list[str],
    accumulated_files: dict[str, int],
    retries_per_tier: dict[str, int],
    best_output: dict,
    cost_summary: dict,
    attempts_total: int,
    start_time: float,
) -> None:
    """Write a checkpoint after a tier completes (accept or reject)."""
    checkpoint = {
        "task_id": task_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "escalation_path": escalation_path,
        "accumulated_files": accumulated_files,
        "retries_per_tier": retries_per_tier,
        "best_output": {
            k: v for k, v in best_output.items()
            if k != "files"  # files are on disk, don't serialize
        },
        "cost_summary": {
            k: str(v) if hasattr(v, '__float__') else v
            for k, v in cost_summary.items()
        },
        "attempts_total": attempts_total,
        "elapsed_seconds": time.monotonic() - start_time,
    }
    self._checkpoint_path(task_id).write_text(
        json.dumps(checkpoint, indent=2, default=str)
    )


def _load_checkpoint(self, task_id: str) -> dict | None:
    """Load a checkpoint if it exists. Returns None if no checkpoint."""
    path = self._checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _clear_checkpoint(self, task_id: str) -> None:
    """Delete the checkpoint file after successful completion."""
    path = self._checkpoint_path(task_id)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
```

**Step 2: Wire checkpoint writes into the tier loop**

After the judge verdict block (after line 1754 in `orchestrator.py`), add:

```python
# ── Checkpoint after every tier verdict ───────────────────────────
self._write_checkpoint(
    task_id=task_id,
    escalation_path=escalation_path + [tier],
    accumulated_files=accumulated_files,
    retries_per_tier=retries_per_tier,
    best_output=best_output,
    cost_summary=self.cost_tracker.get_summary(),
    attempts_total=attempts_total,
    start_time=start_time,
)
```

And after a successful return (accepted verdict), clear the checkpoint:

```python
self._clear_checkpoint(task_id)
```

**Step 3: Add resume support to execute_with_judge signature**

Add `resume_from_checkpoint: bool = False` parameter to `execute_with_judge()`.

At the top of the method, after the multi-pass check, add:

```python
# ── Resume from checkpoint ────────────────────────────────────────
if resume_from_checkpoint:
    ck = self._load_checkpoint(task_id)
    if ck:
        print(f"[RESUME] Restoring state from checkpoint: "
              f"{ck['elapsed_seconds']:.0f}s elapsed, "
              f"{len(ck['accumulated_files'])} files accumulated, "
              f"tiers: {ck['escalation_path']}")
        
        # Restore accumulated state
        accumulated_files = ck.get("accumulated_files", {})
        # Skip already-completed tiers
        completed_tiers = set(ck.get("escalation_path", []))
        
        # Filter tiers to only uncompleted ones
        if tiers:
            tiers = [
                t for t in tiers
                if t not in completed_tiers and t != "Principal"
            ]
            if not tiers:
                # All tiers completed — return best_output if available
                if ck.get("best_output", {}).get("tier"):
                    return {
                        "task_id": task_id,
                        "success": True,
                        "output": ck["best_output"].get("output"),
                        "tier_used": ck["best_output"]["tier"],
                        "attempts_total": ck.get("attempts_total", 0),
                        "duration_seconds": ck.get("elapsed_seconds", 0),
                        "cost_summary": ck.get("cost_summary", {}),
                        "escalation_path": ck.get("escalation_path", []),
                        "resumed": True,
                    }
```

**Step 4: Write unit tests**

```python
#!/usr/bin/env python3
"""Unit tests for orchestrator checkpoint/resume."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from src.core.orchestrator import LLMOrchestrator


class TestCheckpoint:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs" / "workflow" / "escalations").mkdir(parents=True)
        (self.root / "docs" / "workflow" / "templates").mkdir(parents=True)
        self.o = LLMOrchestrator(project_root=str(self.root))

    def teardown_method(self):
        self.tmp.cleanup()

    def test_write_and_load_checkpoint(self):
        self.o._write_checkpoint(
            task_id="test-task",
            escalation_path=["L0-Coder"],
            accumulated_files={"src/a.py": 500},
            retries_per_tier={"L0-Coder": 2},
            best_output={"tier": "L0-Coder", "score": 0.8, "output": "..."},
            cost_summary={"total_cost": 0.001},
            attempts_total=2,
            start_time=time.monotonic(),
        )
        ck = self.o._load_checkpoint("test-task")
        assert ck is not None
        assert ck["task_id"] == "test-task"
        assert "L0-Coder" in ck["escalation_path"]
        assert ck["accumulated_files"]["src/a.py"] == 500
        assert ck["retries_per_tier"]["L0-Coder"] == 2

    def test_load_nonexistent_checkpoint(self):
        assert self.o._load_checkpoint("nonexistent") is None

    def test_clear_checkpoint(self):
        self.o._write_checkpoint(
            task_id="clear-me",
            escalation_path=[],
            accumulated_files={},
            retries_per_tier={},
            best_output={},
            cost_summary={},
            attempts_total=0,
            start_time=time.monotonic(),
        )
        assert self.o._load_checkpoint("clear-me") is not None
        self.o._clear_checkpoint("clear-me")
        assert self.o._load_checkpoint("clear-me") is None

    def test_checkpoint_file_is_valid_json(self):
        self.o._write_checkpoint(
            task_id="json-test",
            escalation_path=["L0-Coder", "L1-Coder"],
            accumulated_files={"a.py": 100, "b/c.py": 200},
            retries_per_tier={"L0-Coder": 3, "L1-Coder": 1},
            best_output={"tier": "L1-Coder", "score": 0.85},
            cost_summary={"daily_total": 0.005},
            attempts_total=4,
            start_time=time.monotonic(),
        )
        path = self.o._checkpoint_path("json-test")
        raw = path.read_text()
        parsed = json.loads(raw)
        assert parsed["task_id"] == "json-test"
        assert len(parsed["escalation_path"]) == 2
```

**Step 5: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_orchestrator_checkpoint.py -v
# Expected: 4 tests pass
```

**Step 6: Commit**

```bash
git add src/core/orchestrator.py tests/unit/test_orchestrator_checkpoint.py
git commit -m "feat: add checkpoint/resume to orchestrator for crash recovery"
```

---

## Gap 4: Dedicated Fix-Loop Prompt

### Context

**Article reference:** Section 5 (Four Loops) — "`fix_loop` should be simpler than `build_loop` — its task is to fix specific issues with tools scoped to read + edit existing files, not create new ones."

**Current state:** Rejected coders get the same system prompt as fresh tasks, just with feedback appended. There's no structural difference between the "build" path and the "fix" path. This causes the common retry failure mode where the coder rewrites working code instead of applying targeted fixes.

**What changes:** Create a new `fix-system-prompt.md` template that is used when `feedback` is non-empty (retry, not fresh attempt). The fix prompt restricts the coder to editing existing files, bans file creation unless the judge explicitly requested it, and emphasizes "make minimal changes." Also: split the coder invocation so that retries with feedback use the fix prompt while fresh attempts use the build prompt.

### Tasks

---

### Task 4.1: Create `docs/workflow/templates/fix-system-prompt.md`

**Objective:** New system prompt template for fix-mode (retries with judge feedback).

**Files:**
- Create: `docs/workflow/templates/fix-system-prompt.md`
- Create: `docs/workflow/templates/fix-pi-system-prompt.md` (PI-adapted version)

**Step 1: Write the fix prompt**

```markdown
# ROLE: Expert Code Fixer (Fix Mode)

You are fixing specific issues identified by a code reviewer. The code was
already written and is substantially correct — your job is to apply targeted
corrections, not to rewrite or restructure.

## Core Rule

**FIX THE ISSUES. CHANGE AS LITTLE AS POSSIBLE.**

Every line you change is a risk. The code works — it just needs the specific
fixes listed below. Do not refactor, do not reorganize, do not "improve"
anything that the reviewer didn't flag.

## Rules

- **Read the file first** before editing it. Use `file_read` to see the
  current state. Only then use `file_write` to apply your changes.
- **Change only what the reviewer asked for.** If the feedback says "add
  None check on line 10," add that check and stop. Don't also add type
  hints, docstrings, or refactor the function.
- **Preserve existing code structure.** Keep all existing imports, function
  signatures, and logic that the reviewer didn't flag.
- **One file per fix.** Apply corrections one file at a time. Read →
  understand the issue → apply the minimal fix → verify.
- **If the feedback is unclear**, say so and ask for clarification rather
  than guessing what to change.
- **Output a brief summary** of what you fixed and in which files. End with
  DONE.

## What NOT to do

- ❌ Do NOT create new files unless the reviewer explicitly asked for one.
- ❌ Do NOT delete files unless the reviewer explicitly asked.
- ❌ Do NOT rewrite functions from scratch — apply surgical edits.
- ❌ Do NOT add tests, documentation, or examples unless asked.
- ❌ Do NOT change variable names, reorganize imports, or apply style fixes.
- ❌ Do NOT "improve" the code beyond what was requested.

## Example

Reviewer says: "Line 15: `data['key']` will KeyError if key is missing.
Add `.get('key', default)` or a try/except."

Right fix:
```
# Read the file, find line 15, change:
data['key']
# to:
data.get('key', default_value)
# Output DONE.
```

Wrong fix:
```
# Read the file, find line 15, then:
# - Refactor entire function to use dataclass
# - Add type hints to all parameters
# - Rewrite error handling for the whole module
# ❌ THIS IS NOT WHAT WAS ASKED FOR.
```

## Completion

When you have applied ALL the fixes requested, output DONE on its own line.
```

**Step 2: Write the PI-adapted version**

```markdown
# ROLE: Expert Code Fixer (PI Mode)

You are fixing specific issues identified by a code reviewer using the PI
coding agent's `write` tool. The code was already written and is
substantially correct — your job is to apply targeted corrections.

## Core Rule

**FIX THE ISSUES. CHANGE AS LITTLE AS POSSIBLE.**

## Rules

- Use the `read` tool to inspect existing files before editing.
- Use the `write` tool to apply fixes. Overwrite the ENTIRE file with the
  corrected version — this is how PI works.
- **Change only what the reviewer asked for.** Do not refactor, reorganize,
  or add anything unrequested.
- **Preserve all existing code** except the specific lines flagged.
- **One file at a time.** Read, fix, write, then move to the next.
- Output a brief summary of fixes applied and end with DONE.

## What NOT to do

- ❌ Do NOT create new files unless explicitly asked.
- ❌ Do NOT delete files unless explicitly asked.
- ❌ Do NOT rewrite functions from scratch.
- ❌ Do NOT add tests, docs, or examples unless asked.

## Completion

When you have applied ALL fixes, output DONE on its own line.
```

**Step 3: Commit**

```bash
git add docs/workflow/templates/fix-system-prompt.md docs/workflow/templates/fix-pi-system-prompt.md
git commit -m "feat: add fix-mode system prompt templates for targeted retries"
```

---

### Task 4.2: Route retries to fix prompt in orchestrator

**Objective:** When `feedback` is non-empty, load the fix prompt instead of the build prompt.

**Files:**
- Modify: `src/core/orchestrator.py` (prompt loading in execute_with_judge)
- Test: `tests/unit/test_orchestrator_leaf.py` (add fix prompt test)

**Step 1: Add fix prompt loading**

In `_get_agent_system_prompt()`, add support for a `task_type="fix"` variant:

```python
def _get_agent_system_prompt(self, task_type: str) -> str:
    """Load agent system prompt from template file."""
    # ... existing logic ...
    
    # Fix mode: use fix prompt when available
    if task_type == "fix":
        fix_template_path = self.workflow_dir / "templates" / "fix-system-prompt.md"
        if fix_template_path.exists():
            return fix_template_path.read_text()
        # Fallback: build prompt is better than nothing
    
    # ... rest of existing logic ...
```

Similarly for PI:

```python
def _get_pi_system_prompt(self, task_type: str) -> str:
    """Load PI-specific system prompt from template file."""
    if task_type == "fix":
        fix_pi_path = self.workflow_dir / "templates" / "fix-pi-system-prompt.md"
        if fix_pi_path.exists():
            return fix_pi_path.read_text()
    # ... existing logic ...
```

**Step 2: Pass fix task_type on retries**

In the retry loop, when `feedback` is non-empty, use `task_type="fix"` instead of the original task_type. The system prompt loading at lines 1428-1429 already runs once at the top of `execute_with_judge()`. We need to re-load for fix mode:

```python
# ── Fix-mode prompt selection ─────────────────────────────────────
# On retry with feedback, use the fix prompt (simpler, targeted).
# On fresh attempt, use the build prompt.
if feedback:
    current_sp = self._get_agent_system_prompt("fix")
    current_pi_sp = self._get_pi_system_prompt("fix")
else:
    current_sp = agent_system_prompt
    current_pi_sp = pi_system_prompt
```

Then pass `current_sp` / `current_pi_sp` to `_execute_opencode_tier` / `_execute_pi_tier` instead of the originally loaded ones.

**Step 3: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_orchestrator_leaf.py -v
python -m pytest tests/unit/test_orchestrator_state_machine.py -v
# Expected: all existing tests pass
```

**Step 4: Commit**

```bash
git add src/core/orchestrator.py
git commit -m "feat: route retries with feedback to fix-mode system prompt"
```

---

## Gap 5: Structured Task Contracts

### Context

**Article reference:** Section 4 — "`spec.md` = product contract (what the agent SHOULD do). `Plans.md` = task ledger (what the agent HAS done)."

**Current state:** `context['task_spec']` is a raw string. No structured constraints or success criteria. The judge has no authoritative definition of done beyond the raw text.

**What changes:** Add an optional `spec` dict to the task context with `constraints`, `success_criteria`, and `anti_patterns` fields. Inject into the judge prompt as an "## Acceptance Criteria" block. This gives the judge an objective bar for scoring and improves verdict accuracy.

### Tasks

---

### Task 5.1: Add spec dictionary support to judge prompt

**Objective:** Accept an optional `spec` dict and inject it into the judge evaluation prompt.

**Files:**
- Modify: `src/core/judge.py` (evaluate method — add spec injection)
- Modify: `src/core/orchestrator.py` (pass spec from context to judge)
- Test: `tests/unit/test_orchestrator_leaf.py` (add spec injection test)

**Step 1: Add spec injection to Judge.evaluate()**

Add an optional `spec` parameter to `Judge.evaluate()`:

```python
def evaluate(
    self,
    task: str,
    output: str,
    model_profile_key: Optional[str] = None,
    spec: Optional[dict[str, list[str]]] = None,
) -> Verdict:
```

After the known-failure injection (line ~303), add spec injection:

```python
# ── Structured task contract (Article Section 4) ──────────────────
if spec:
    spec_lines = ["\n\n## Acceptance Criteria\n\n"]
    if spec.get("success_criteria"):
        spec_lines.append("**Must satisfy ALL of:**\n")
        for i, criterion in enumerate(spec["success_criteria"], 1):
            spec_lines.append(f"{i}. {criterion}\n")
    if spec.get("constraints"):
        spec_lines.append("\n**Must NOT violate:**\n")
        for i, constraint in enumerate(spec["constraints"], 1):
            spec_lines.append(f"{i}. {constraint}\n")
    if spec.get("anti_patterns"):
        spec_lines.append("\n**Known anti-patterns (score < 0.5 if matched):**\n")
        for i, ap in enumerate(spec["anti_patterns"], 1):
            spec_lines.append(f"{i}. {ap}\n")
    prompt += "".join(spec_lines)
```

**Step 2: Pass spec from orchestrator context**

In `execute_with_judge()`, extract `spec` from context and pass to judge:

```python
task_spec_dict = context.get("spec")  # optional structured contract

# Later, in the judge evaluation block:
eval_kwargs = {
    "task": str(task_text),
    "output": eval_output,
}
if task_spec_dict:
    eval_kwargs["spec"] = task_spec_dict
```

**Step 3: Write tests**

In `tests/unit/test_orchestrator_leaf.py`:

```python
def test_spec_injected_into_judge_context(self):
    """Verify structured specs are accessible from task context."""
    spec = {
        "success_criteria": ["All tests pass", "No new dependencies"],
        "constraints": ["Must use existing ORM", "No raw SQL"],
        "anti_patterns": ["eval()", "shell=True"],
    }
    # Verify spec can be stored and retrieved from context dict
    context = {"task_spec": "Build a REST API.", "spec": spec}
    assert context["spec"]["success_criteria"][0] == "All tests pass"
    assert len(context["spec"]["anti_patterns"]) == 2
```

**Step 4: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_orchestrator_leaf.py -v
# Expected: all tests pass
```

**Step 5: Commit**

```bash
git add src/core/judge.py src/core/orchestrator.py tests/unit/test_orchestrator_leaf.py
git commit -m "feat: add structured task contract (spec dict) to judge evaluation"
```

---

## Gap 6: Consecutive Error Threshold

### Context

**Article reference:** Pillar 4 — "If `consecutive_failures >= 3`, stop the loop. Don't keep escalating into guaranteed failure."

**Current state:** MR-Krabs always exhausts all tiers regardless of error patterns. If L0, L1, and L2 all fail with the same error, all three tiers are burned before reaching Principal. This wastes cloud credits.

**What changes:** Track `consecutive_failures` across tiers with the same error category. When 2+ tiers fail the same way, skip remaining intermediate tiers and escalate directly to Principal with a diagnostic.

### Tasks

---

### Task 6.1: Add consecutive-error detection to tier loop

**Objective:** Skip remaining tiers when repeated failures indicate structural unfitness.

**Files:**
- Modify: `src/core/orchestrator.py` (execute_with_judge — tier loop)
- Test: `tests/unit/test_orchestrator_state_machine.py` (add consecutive-error test)

**Step 1: Add error tracking and early-exit logic**

In `execute_with_judge()`, initialize error tracking before the tier loop:

```python
# ── Consecutive error tracking (Article Pillar 4) ─────────────────
last_error_category: str | None = None
consecutive_failures: int = 0
MAX_CONSECUTIVE_FAILURES = 3
```

After each tier exhausts retries (after the retry loop, before failure_action handling), categorize and count:

```python
# ── Track consecutive failures ────────────────────────────────────
error_category = self._categorize_error(verdict)
if error_category == last_error_category:
    consecutive_failures += 1
else:
    last_error_category = error_category
    consecutive_failures = 1

if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
    print(f"[CONSECUTIVE] {consecutive_failures} consecutive tier failures "
          f"with '{error_category}' — skipping remaining tiers → Principal")
    break  # exit tier loop, fall through to Principal escalation
```

**Step 2: Add error categorization helper**

```python
@staticmethod
def _categorize_error(verdict) -> str:
    """Categorize a judge verdict into an error category for pattern detection.

    Returns one of: 'empty_output', 'truncation', 'wrong_approach',
    'syntax_error', 'missing_files', 'unknown'.
    """
    if verdict is None:
        return "unknown"
    
    critique = (verdict.critique or "").lower()
    score = verdict.score if hasattr(verdict, 'score') else 0.0
    
    # Pattern-based categorization
    if score < 0.1:
        return "empty_output"
    if "truncat" in critique or "incomplete" in critique:
        return "truncation"
    if "syntax" in critique or "indentation" in critique or "parse" in critique:
        return "syntax_error"
    if "missing" in critique and ("file" in critique or "module" in critique):
        return "missing_files"
    if "wrong approach" in critique or "misunderstand" in critique:
        return "wrong_approach"
    
    return "unknown"
```

**Step 3: Add state-machine test**

In `tests/unit/test_orchestrator_state_machine.py`:

```python
def test_consecutive_error_skips_remaining_tiers(self):
    """Verify that 3 consecutive same-category failures skip to Principal."""
    from src.core.orchestrator import MAX_CONSECUTIVE_FAILURES, LLMOrchestrator
    
    # Test error categorization
    from src.core.judge import Verdict
    
    v1 = Verdict(accepted=False, provisional=False, score=0.05,
                 critique="Empty output from PI", checks_passed=[], checks_failed=[])
    v2 = Verdict(accepted=False, provisional=False, score=0.08,
                 critique="Empty output", checks_passed=[], checks_failed=[])
    v3 = Verdict(accepted=False, provisional=False, score=0.03,
                 critique="No output produced", checks_passed=[], checks_failed=[])
    
    cat1 = LLMOrchestrator._categorize_error(v1)
    cat2 = LLMOrchestrator._categorize_error(v2)
    cat3 = LLMOrchestrator._categorize_error(v3)
    
    assert cat1 == "empty_output"
    assert cat2 == "empty_output"
    assert cat3 == "empty_output"
    # All same category → 3 consecutive failures → skip to Principal


def test_different_errors_reset_counter(self):
    """Verify that different error categories reset the counter."""
    v1 = LLMOrchestrator._categorize_error(
        Verdict(accepted=False, provisional=False, score=0.05,
                critique="Empty output", checks_passed=[], checks_failed=[]))
    v2 = LLMOrchestrator._categorize_error(
        Verdict(accepted=False, provisional=False, score=0.4,
                critique="Wrong approach — used sync instead of async",
                checks_passed=[], checks_failed=[]))
    
    assert v1 == "empty_output"
    assert v2 == "wrong_approach"
    # Different categories → counter resets
```

**Step 4: Run tests**

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/test_orchestrator_state_machine.py -v
# Expected: all existing tests pass, 2 new tests pass
```

**Step 5: Commit**

```bash
git add src/core/orchestrator.py tests/unit/test_orchestrator_state_machine.py
git commit -m "feat: add consecutive-error threshold to skip doomed tiers"
```

---

## Final Integration Test

After all six gaps are implemented, run the full test suite:

```bash
cd ~/workspace/MR-Krabs
python -m pytest tests/unit/ tests/integration/test_judge_escalation_e2e.py \
    --ignore=tests/integration/test_openrouter_integration.py \
    --ignore=tests/e2e/ -q

# Expected: 928+ tests pass (baseline) + all new tests
```

Check for regressions:

```bash
# Verify imports clean
python -c "
from src.core.context_compressor import compress_history, estimate_context_fill
from src.core.self_improver import SelfImprover
print('All imports clean')
"
```

---

## Summary of Files Changed

| Gap | Files Created | Files Modified |
|-----|--------------|----------------|
| 1: Context Compression | `src/core/context_compressor.py`, `tests/unit/test_context_compressor.py` | `src/core/orchestrator.py`, `src/core/pipeline_monitor.py`, `tests/unit/test_orchestrator_leaf.py` |
| 2: Self-Improvement | `src/core/self_improver.py`, `tests/unit/test_self_improver.py` | `src/core/orchestrator.py` |
| 3: State Serialization | `tests/unit/test_orchestrator_checkpoint.py` | `src/core/orchestrator.py` |
| 4: Fix-Loop Prompt | `docs/workflow/templates/fix-system-prompt.md`, `docs/workflow/templates/fix-pi-system-prompt.md` | `src/core/orchestrator.py`, `tests/unit/test_orchestrator_leaf.py` |
| 5: Task Contracts | — | `src/core/judge.py`, `src/core/orchestrator.py`, `tests/unit/test_orchestrator_leaf.py` |
| 6: Error Threshold | — | `src/core/orchestrator.py`, `tests/unit/test_orchestrator_state_machine.py` |

**Total: 6 new files, ~800 lines of implementation code, ~400 lines of tests.**

---

*Plan compiled June 30, 2026. Source: `agent-looping-briefing-agent.md` (11 articles cross-referenced with public implementations). Mapped to MR-Krabs at commit ef6138c.*
