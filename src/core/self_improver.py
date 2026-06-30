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
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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
                # Look for "missing X", "should use Y", "X not found", etc.
                # IMPORTANT: put longest alternatives first so they don't
                # get shadowed by shorter prefixes (e.g. "missing X Y"
                # before "missing").
                phrases = re.findall(
                    r'(?:missing\s+\w+\s+(?:import|check|handler|validation)'
                    r'|forgot\s+to\s+\w+'
                    r'|should\s+use\s+\w+'
                    r'|not\s+found'
                    r'|add\s+\w+'
                    r'|missing)',
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
        entries.append(
            f"# Discovered from production pipeline runs\n"
            f"# Last updated: auto-generated by SelfImprover\n"
        )

        for model_key in set(p.model_keys[0] if p.model_keys else "unknown" for p in patterns):
            model_patterns = [p for p in patterns if (p.model_keys[0] if p.model_keys else "") == model_key]
            if model_patterns:
                entries.append(f"\n# Patterns for model: {model_key}")
                for p in model_patterns:
                    entries.append(f"""\
KnownFailure(
    trigger=r"{p.pattern_regex}",
    feedback=(
        "[AUTO-DISCOVERED pattern (seen {p.occurrences}x)] "
        "{p.description}. Apply the fix described in the judge critique."
    ),
    severity="warning",
),""")

        new_section = "\n".join(entries) + "\n\n"
        new_content = original.rstrip() + "\n" + new_section

        # Write back
        self.profiles_path.write_text(new_content)
