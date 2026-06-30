#!/usr/bin/env python3
"""Deterministic task splitter — replaces LLM planner for file decomposition.

Parses file references from task specs, groups by directory proximity,
and chunks into sequential PI passes of ≤ MAX_FILES_PER_PASS files each.
No LLM call — pure deterministic parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_FILES_PER_PASS = 50
MAX_TESTS_PER_PASS = 50


@dataclass
class FileRef:
    """A file referenced in a task spec."""
    path: str
    action: str = "modify"
    section_start: int = 0
    section_end: int = 0


@dataclass
class SubTask:
    """A self-contained chunk of work for one PI pass."""
    files: list[FileRef]
    spec: str = ""
    pass_num: int = 1


def extract_file_refs(task_spec: str) -> list[FileRef]:
    """Find all code-file paths mentioned in a task spec.

    Matches patterns like:
      - `src/parousia/config.py` (backtick-quoted inline)
      - File: src/parousia/guard/rest_server.py
      - - src/parousia/config.py (bullet list)
      - Modify `tests/test_cli.py`
      - Bare paths like src/config.py in prose

    Only includes common code/config extensions.
    """
    code_extensions = (
        r'\.(?:py|md|yaml|yml|toml|json|cfg|ini|sh|sql|html|css|js|ts|rs|go|java|c|cpp|h|hpp)'
    )

    seen = set()
    refs = []

    # Pattern 1: Backtick-quoted paths (can appear anywhere inline)
    backtick_pattern = re.compile(
        r'`([a-zA-Z0-9_/.~@-]+' + code_extensions + r')`'
    )
    for match in backtick_pattern.finditer(task_spec):
        path = match.group(1).strip()
        if path in seen:
            continue
        seen.add(path)
        line_no = task_spec[:match.start()].count('\n') + 1
        refs.append(FileRef(
            path=path, action='modify',
            section_start=line_no, section_end=line_no + 5,
        ))

    # Pattern 2: Paths at start of line or after bullet/File: prefix
    line_pattern = re.compile(
        r'(?:^|\n)\s*(?:File:\s*|[-*]\s*)?'
        r'([a-zA-Z0-9_/.~@-]+' + code_extensions + r')'
        r'(?=\s|$|,|\.)',
        re.MULTILINE
    )
    for match in line_pattern.finditer(task_spec):
        path = match.group(1).strip()
        if path in seen:
            continue
        seen.add(path)
        line_no = task_spec[:match.start()].count('\n') + 1
        refs.append(FileRef(
            path=path, action='modify',
            section_start=line_no, section_end=line_no + 5,
        ))

    # Pattern 3: Bare paths anywhere in prose (catch-all)
    bare_pattern = re.compile(
        r'(?<!\w)([a-zA-Z0-9_/.~@-]+' + code_extensions + r')(?![\w`])'
    )
    for match in bare_pattern.finditer(task_spec):
        path = match.group(1).strip()
        if path in seen:
            continue
        seen.add(path)
        line_no = task_spec[:match.start()].count('\n') + 1
        refs.append(FileRef(
            path=path, action='modify',
            section_start=line_no, section_end=line_no + 5,
        ))

    return refs


def group_by_directory(refs: list[FileRef]) -> list[list[FileRef]]:
    """Group file refs by closest common parent directory.

    Files in the same top-level directory group together, keeping
    related changes in the same PI pass for context coherence.
    """
    groups: dict[str, list[FileRef]] = {}
    for ref in refs:
        parts = ref.path.split('/')
        # Group by directory (everything except the filename)
        if len(parts) >= 2:
            key = '/'.join(parts[:-1])  # e.g. "src/parousia/guard"
        else:
            key = parts[0]  # root-level file

        groups.setdefault(key, []).append(ref)

    # Sort groups by size descending — largest groups first
    return sorted(groups.values(), key=len, reverse=True)


def split_into_passes(
    refs: list[FileRef],
    max_files: int = MAX_FILES_PER_PASS,
) -> list[SubTask]:
    """Split file refs into sequential PI passes, each ≤ max_files.

    Groups files by directory, then packs groups into passes.
    If a single group exceeds max_files, it is split across passes.
    """
    if len(refs) <= max_files:
        return [SubTask(files=list(refs), spec="", pass_num=1)]

    groups = group_by_directory(refs)
    passes: list[list[FileRef]] = []
    current_pass: list[FileRef] = []
    current_count = 0

    for group in groups:
        if current_count + len(group) <= max_files:
            current_pass.extend(group)
            current_count += len(group)
        else:
            # Flush current pass if it has files
            if current_pass:
                passes.append(current_pass)

            # If this group alone exceeds max_files, split it
            if len(group) > max_files:
                for i in range(0, len(group), max_files):
                    passes.append(group[i:i + max_files])
                current_pass = []
                current_count = 0
            else:
                current_pass = list(group)
                current_count = len(group)

    if current_pass:
        passes.append(current_pass)

    return [
        SubTask(files=list(p), spec="", pass_num=i + 1)
        for i, p in enumerate(passes)
    ]


def generate_subtask_spec(
    original_spec: str,
    subtask: SubTask,
    pass_num: int,
    total_passes: int,
    previous_files: list[str],
) -> str:
    """Generate a self-contained sub-task spec for one PI pass.

    Includes:
    - Pass number and total
    - Files to modify in this pass
    - Files already written (do NOT modify)
    - Original task context
    - Clear instruction to only touch the listed files
    """
    file_list = '\n'.join(f'- {f.path}' for f in subtask.files) if subtask.files else '(none)'
    previous = '\n'.join(
        f'- {f} (already written in previous passes)'
        for f in previous_files
    ) if previous_files else '(none)'

    return f"""# Pass {pass_num}/{total_passes}

## Files to modify in this pass:
{file_list}

## Files already written (do NOT modify):
{previous}

## Original Task Context:
{original_spec}

## Instructions:
Only modify the files listed under "Files to modify in this pass."
Do NOT touch files in "Files already written."
Output DONE when all files in this pass are correctly written.
"""
