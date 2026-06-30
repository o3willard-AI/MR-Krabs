"""Tests for multi-pass PI execution (Pipeline Hardening Task 2)."""

from unittest.mock import MagicMock, patch
import pytest

from src.core.task_splitter import FileRef, SubTask, generate_subtask_spec
from src.core.orchestrator import LLMOrchestrator


class TestMultiPassDetection:
    """Verify that execute_with_judge detects and splits large tasks."""

    def test_small_task_runs_single_pass(self):
        """Task with ≤ MAX_FILES_PER_PASS runs normally, no split."""
        o = LLMOrchestrator()

        # Mock the LLM call AND the judge to avoid real API calls
        with patch.object(o, 'call_llm_with_retry', return_value={
            "success": True, "output": "DONE", "attempt": 1,
            "duration_seconds": 0.1, "ready_for_escalation": False,
        }), patch('src.core.orchestrator.Judge') as MockJudge:
            mock_judge = MockJudge.return_value
            mock_judge.evaluate.return_value = MagicMock(
                accepted=True, score=0.9, critique="Good",
            )
            result = o.execute_with_judge(
                task_id='test-single',
                context={'task_spec': 'Write src/single.py'},
                tiers=['L0-Coder'],
                max_retries_per_tier=1,
                judge_model="Judge",
            )
            assert result['success'] is True

    def test_large_task_triggers_multi_pass(self):
        """Task with many file refs returns pass_count > 1."""
        o = LLMOrchestrator()

        files = '\n'.join(f'File: src/parousia/module_{i}.py' for i in range(55))
        spec = f"Modify these files:\n{files}"

        # Mock the recursive execute_with_judge to return success for each pass
        with patch.object(o, 'execute_with_judge', wraps=o.execute_with_judge) as mock_ej:
            # Override the recursive calls to return success immediately
            original = o.execute_with_judge
            call_count = [0]

            def fake_ej(**kwargs):
                call_count[0] += 1
                tid = kwargs.get('task_id', '')
                if '-p' in tid:
                    # Pass sub-call: return success
                    return {
                        "task_id": tid, "success": True,
                        "output": "Pass DONE",
                        "files": {f"src/parousia/module_{i}.py": "content"
                                  for i in range(55)},
                        "tier_used": "L0-Coder",
                        "attempts_total": 1,
                        "duration_seconds": 0.1,
                    }
                return original(**kwargs)

            with patch.object(o, 'execute_with_judge', side_effect=fake_ej):
                result = o.execute_with_judge(
                    task_id='test-multi',
                    context={'task_spec': spec},
                    tiers=['L0-Coder'],
                    max_retries_per_tier=1,
                    judge_model="Judge",
                )
                assert result['success'] is True
                # Should have been split into multiple passes
                assert result.get('pass_count', 1) >= 2


class TestMultiPassAccumulation:
    """Verify file accumulation between passes."""

    def test_pass_two_receives_pass_one_files(self):
        """Second pass sees files from first pass as 'already written'."""
        refs = [
            FileRef(path="src/first.py", action="modify", section_start=1, section_end=5),
            FileRef(path="src/second.py", action="modify", section_start=6, section_end=10),
        ]

        subtask = SubTask(files=[refs[1]], spec="", pass_num=2)
        spec = generate_subtask_spec(
            original_spec="Original task.",
            subtask=subtask,
            pass_num=2,
            total_passes=2,
            previous_files=["src/first.py"],
        )

        assert "src/first.py" in spec
        assert "already written" in spec.lower()
        assert "src/second.py" in spec
        assert "Pass 2/2" in spec


class TestMultiPassFailure:
    """Verify pass failures abort correctly."""

    def test_failed_pass_aborts_remaining(self):
        """If pass N fails, passes N+1,... are skipped."""
        o = LLMOrchestrator()

        files = '\n'.join(f'File: src/parousia/module_{i}.py' for i in range(55))
        spec = f"Modify these files:\n{files}"

        # Force split into 2 passes, first succeeds, second fails
        original_ej = o.execute_with_judge

        def fake_ej(**kwargs):
            tid = kwargs.get('task_id', '')
            if '-p1' in tid:
                return {
                    "task_id": tid, "success": True,
                    "output": "PASS 1 DONE",
                    "files": {f"src/parousia/module_{i}.py": "ok" for i in range(50)},
                    "tier_used": "L0-Coder",
                    "attempts_total": 1,
                    "duration_seconds": 0.1,
                }
            elif '-p2' in tid:
                return {
                    "task_id": tid, "success": False,
                    "output": "",
                    "error": "Empty output from PI",
                    "attempts_total": 2,
                    "duration_seconds": 1.0,
                }
            else:
                # Top-level call: use original (unmocked) method
                return original_ej(**kwargs)

        with patch.object(o, 'execute_with_judge', side_effect=fake_ej):
            result = o.execute_with_judge(
                task_id='test-fail',
                context={'task_spec': spec},
                tiers=['L0-Coder'],
                max_retries_per_tier=1,
                judge_model="Judge",
            )
            assert result['success'] is False
            assert 'pass' in str(result.get('output', '')).lower()
