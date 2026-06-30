#!/usr/bin/env python3
"""Unit tests for self_improver module."""

import tempfile
from pathlib import Path

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
        # Pattern appears once in 5 rejected → frequency 0.2 < 0.4 → filtered
        model_patterns = {
            "L0-Coder": [FailurePattern(
                pattern_regex="once", description="once",
                occurrences=1, model_keys=["L0-Coder"],
            )]
        }
        # 5 rejected verdicts, but pattern only appears once → frequency 0.2
        verdicts = [
            {"tier": "L0-Coder", "score": 0.4, "accepted": False, "critique": f"critique{i}"}
            for i in range(5)
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

    def test_improvement_result_dataclass(self):
        result = ImprovementResult(
            patterns_discovered=2,
            models_updated=["L0-Coder"],
            patterns=[
                FailurePattern(
                    pattern_regex="test", description="test pattern",
                    occurrences=2, model_keys=["L0-Coder"],
                )
            ],
            errors=[],
        )
        assert result.patterns_discovered == 2
        assert len(result.models_updated) == 1
        assert len(result.patterns) == 1
