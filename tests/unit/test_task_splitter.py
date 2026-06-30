"""Tests for deterministic task splitter (Pipeline Hardening Task 1)."""

import pytest
from src.core.task_splitter import (
    FileRef,
    SubTask,
    extract_file_refs,
    group_by_directory,
    split_into_passes,
    generate_subtask_spec,
    MAX_FILES_PER_PASS,
)


class TestExtractFileRefs:
    """Parse file paths from task specs."""

    def test_finds_full_paths(self):
        """Finds paths like src/parousia/config.py in spec text."""
        spec = """
        File: src/parousia/config.py
        File: src/parousia/guard/rest_server.py
        Also modify tests/test_cli.py
        """
        refs = extract_file_refs(spec)
        paths = {r.path for r in refs}
        assert "src/parousia/config.py" in paths
        assert "src/parousia/guard/rest_server.py" in paths

    def test_finds_backtick_paths(self):
        """Finds paths in backtick-quoted format."""
        spec = """
        Modify `src/app/main.py` and `tests/test_auth.py`.
        """
        refs = extract_file_refs(spec)
        paths = {r.path for r in refs}
        assert "src/app/main.py" in paths
        assert "tests/test_auth.py" in paths

    def test_finds_bullet_list_paths(self):
        """Finds paths in markdown bullet lists."""
        spec = """
        - src/parousia/config.py
        - tests/test_rest_server.py
        - tests/test_cli.py
        """
        refs = extract_file_refs(spec)
        paths = {r.path for r in refs}
        assert "src/parousia/config.py" in paths
        assert "tests/test_rest_server.py" in paths
        assert "tests/test_cli.py" in paths

    def test_ignores_non_code_files(self):
        """Ignores .txt, .log, and other non-code extensions."""
        spec = """
        See README.md for docs. Config is at src/config.py.
        Log at /var/log/app.log.
        """
        refs = extract_file_refs(spec)
        paths = {r.path for r in refs}
        assert "src/config.py" in paths
        # .md files are included (docs are code-adjacent)
        assert "README.md" in paths
        # .log files should be excluded
        assert "/var/log/app.log" not in paths

    def test_returns_empty_for_no_files(self):
        """Returns empty list when spec has no file references."""
        refs = extract_file_refs("Just some text with no file paths.")
        assert refs == []

    def test_deduplicates_paths(self):
        """Same path mentioned multiple times = one FileRef."""
        spec = """
        File: src/main.py
        Also src/main.py needs changes.
        And don't forget src/main.py!
        """
        refs = extract_file_refs(spec)
        paths = [r.path for r in refs]
        assert paths.count("src/main.py") == 1


class TestGroupByDirectory:
    """Group file refs by parent directory."""

    def test_groups_by_parent_dir(self):
        """Files in same dir cluster together."""
        refs = [
            FileRef(path="src/parousia/guard/rest_server.py", action="modify", section_start=1, section_end=5),
            FileRef(path="src/parousia/guard/mcp_server.py", action="modify", section_start=6, section_end=10),
            FileRef(path="tests/test_inbox.py", action="modify", section_start=11, section_end=15),
        ]
        groups = group_by_directory(refs)
        # Should have 2 groups: guard/ files together, tests/ separate
        assert len(groups) == 2
        # guard group should have 2 files
        guard_group = [g for g in groups if any("guard" in r.path for r in g)][0]
        assert len(guard_group) == 2
        # test group should have 1 file
        test_group = [g for g in groups if any("test" in r.path for r in g)][0]
        assert len(test_group) == 1

    def test_sorts_largest_first(self):
        """Largest groups come first in results."""
        refs = [
            FileRef(path="src/a/x.py", action="modify", section_start=1, section_end=5),
            FileRef(path="src/a/y.py", action="modify", section_start=6, section_end=10),
            FileRef(path="src/a/z.py", action="modify", section_start=11, section_end=15),
            FileRef(path="tests/t.py", action="modify", section_start=16, section_end=20),
        ]
        groups = group_by_directory(refs)
        assert len(groups[0]) == 3  # src/a/ group first (largest)
        assert len(groups[1]) == 1  # tests/ group second


class TestSplitIntoPasses:
    """Split file refs into sequential passes."""

    def test_single_pass_when_within_limit(self):
        """≤ MAX_FILES returns one pass."""
        refs = [
            FileRef(path=f"src/file_{i}.py", action="modify", section_start=i, section_end=i+5)
            for i in range(5)
        ]
        passes = split_into_passes(refs, max_files=MAX_FILES_PER_PASS)
        assert len(passes) == 1
        assert len(passes[0].files) == 5

    def test_splits_when_over_limit(self):
        """> MAX_FILES_PER_PASS splits into multiple passes."""
        refs = [
            FileRef(path=f"src/file_{i}.py", action="modify", section_start=i, section_end=i+5)
            for i in range(25)
        ]
        passes = split_into_passes(refs, max_files=10)
        assert len(passes) >= 2
        for p in passes:
            assert len(p.files) <= 10

    def test_passes_are_sequentially_numbered(self):
        """Each pass gets a sequential pass_num."""
        refs = [
            FileRef(path=f"src/file_{i}.py", action="modify", section_start=i, section_end=i+5)
            for i in range(25)
        ]
        passes = split_into_passes(refs, max_files=10)
        for i, p in enumerate(passes):
            assert p.pass_num == i + 1


class TestGenerateSubtaskSpec:
    """Generate self-contained sub-task specs."""

    def test_includes_pass_numbering(self):
        """Generated spec shows pass X of Y."""
        spec = generate_subtask_spec(
            original_spec="Original task context here.",
            subtask=SubTask(files=[], spec="", pass_num=2),
            pass_num=2,
            total_passes=3,
            previous_files=["src/done.py"],
        )
        assert "Pass 2/3" in spec
        assert "pass_num=2" not in spec  # no raw original_spec dumping
        assert "do NOT modify" in spec

    def test_lists_previous_files(self):
        """Already-written files are listed as 'do NOT modify'."""
        spec = generate_subtask_spec(
            original_spec="Original task.",
            subtask=SubTask(files=[
                FileRef(path="src/new.py", action="create", section_start=1, section_end=5),
            ], spec="", pass_num=2),
            pass_num=2,
            total_passes=2,
            previous_files=["src/done.py", "tests/done.py"],
        )
        assert "src/done.py" in spec
        assert "do not modify" in spec.lower()
        assert "src/new.py" in spec

    def test_no_previous_files_shows_none(self):
        """First pass shows (none) for previous files."""
        spec = generate_subtask_spec(
            original_spec="Original task.",
            subtask=SubTask(files=[], spec="", pass_num=1),
            pass_num=1,
            total_passes=2,
            previous_files=[],
        )
        assert "(none)" in spec.lower()
