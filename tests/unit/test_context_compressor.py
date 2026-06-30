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
