"""E2E test: multi-pass pipeline handles 22-file tasks (Pipeline Hardening Task 5)."""

import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from src.core.task_splitter import (
    extract_file_refs,
    split_into_passes,
    generate_subtask_spec,
    MAX_FILES_PER_PASS,
)


class TestE2EMultiPass:
    """End-to-end: task spec with 22 files → split → pass specs are valid."""

    def test_22_files_detected_and_split(self):
        """22 file references → correct detection and pass count."""
        files = '\n'.join(
            f'File: src/parousia/module_{i}.py' for i in range(22)
        )
        spec = f"Modify these 22 files:\n{files}"

        refs = extract_file_refs(spec)
        assert len(refs) == 22

        passes = split_into_passes(refs)
        assert len(passes) >= 2

        # Verify each pass is within limit
        for p in passes:
            assert len(p.files) <= MAX_FILES_PER_PASS

        # Verify all files are covered
        all_files = set()
        for p in passes:
            for f in p.files:
                all_files.add(f.path)
        assert len(all_files) == 22

    def test_pass_specs_are_self_contained(self):
        """Each pass spec is complete and executable."""
        files = '\n'.join(
            f'File: src/parousia/module_{i}.py' for i in range(22)
        )
        spec = f"Modify these 22 files:\n{files}"
        refs = extract_file_refs(spec)
        passes = split_into_passes(refs)

        accumulated = []
        for subtask in passes:
            sub_spec = generate_subtask_spec(
                spec, subtask, subtask.pass_num,
                len(passes), accumulated,
            )
            # Each spec must contain pass numbering
            assert f"Pass {subtask.pass_num}/{len(passes)}" in sub_spec
            # Each spec must list its files
            for f in subtask.files:
                assert f.path in sub_spec
            # Each spec must mention prior files (or "(none)" for first)
            if accumulated:
                assert accumulated[0] in sub_spec
            else:
                assert "(none)" in sub_spec.lower()
            # Simulate pass completion
            accumulated.extend(f.path for f in subtask.files)

    def test_multi_pass_accumulates_correctly(self):
        """Simulating passes: pass 3 sees files from passes 1 and 2."""
        refs = [
            __import__('src.core.task_splitter', fromlist=['FileRef']).FileRef(
                path=f"src/p1_file_{i}.py", action="modify",
                section_start=i, section_end=i+5
            ) for i in range(10)
        ] + [
            __import__('src.core.task_splitter', fromlist=['FileRef']).FileRef(
                path=f"src/p2_file_{i}.py", action="modify",
                section_start=i, section_end=i+5
            ) for i in range(10)
        ] + [
            __import__('src.core.task_splitter', fromlist=['FileRef']).FileRef(
                path=f"tests/test_{i}.py", action="modify",
                section_start=i, section_end=i+5
            ) for i in range(2)
        ]

        passes = split_into_passes(refs)
        assert len(passes) >= 2

        accumulated = []
        for subtask in passes:
            sub_spec = generate_subtask_spec(
                "Original task", subtask, subtask.pass_num,
                len(passes), accumulated,
            )
            if accumulated:
                assert "already written" in sub_spec.lower()
            accumulated.extend(f.path for f in subtask.files)

        # All 22 files should be accumulated
        assert len(accumulated) == 22

    def test_single_pass_for_small_task(self):
        """Small tasks (≤20 files) run as single pass."""
        spec = "Modify src/app.py and tests/test_app.py"
        refs = extract_file_refs(spec)
        passes = split_into_passes(refs)
        assert len(passes) == 1
        assert len(passes[0].files) == 2
