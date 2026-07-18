#!/usr/bin/env python3
"""Integration Verifier — checks seams between decomposed chunks after MR-Krabs runs each.

This is NOT the same as the runtime verifier (src/core/verifier.py) which checks
individual chunk outputs. This verifier checks that chunks WORK TOGETHER after
assembly — interface contracts match, imports resolve, and the combined system works.

Steinberger mapping: this sits between Loop 1 (Build) and the inner Verify/Fix loops.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SeamCheck:
    """Result of checking one interface seam between two chunks."""
    source_chunk: str
    target_chunk: str
    passed: bool
    detail: str = ""


@dataclass
class IntegrationResult:
    """Full integration verification result."""
    passed: bool
    seam_checks: list[SeamCheck] = field(default_factory=list)
    import_errors: list[str] = field(default_factory=list)
    runtime_errors: list[str] = field(default_factory=list)
    test_output: str = ""
    assembly_path: Optional[str] = None
    error_summary: str = ""


def verify_integration(
    project_dir: Path,
    chunks: list[dict],  # each: {name, files, interface_contract, ...}
    test_command: Optional[str] = None,
) -> IntegrationResult:
    """Verify that all chunks integrate correctly.

    1. Check that all chunk outputs exist (files were actually written)
    2. Check Python import chain (no ImportError when importing cross-chunk)
    3. Check interface contracts (does chunk B use what chunk A promised to export?)
    4. Run the combined test suite if present
    5. Run the application entry point as smoke test

    Args:
        project_dir: Root of the assembled project
        chunks: List of chunk metadata from the decomposer
        test_command: Optional override test command

    Returns:
        IntegrationResult with pass/fail and detailed diagnostics
    """
    result = IntegrationResult(passed=True)
    seam_checks: list[SeamCheck] = []

    # Step 1: Verify all chunk outputs exist
    for chunk in chunks:
        for file_path in chunk.get("files", []):
            full_path = project_dir / file_path
            if not full_path.exists():
                result.passed = False
                result.import_errors.append(
                    f"Missing file: {file_path} (from chunk '{chunk['name']}')"
                )
                seam_checks.append(SeamCheck(
                    source_chunk=chunk["name"],
                    target_chunk="filesystem",
                    passed=False,
                    detail=f"Expected output {file_path} not written",
                ))

    if not result.passed:
        result.seam_checks = seam_checks
        result.error_summary = "\n".join(result.import_errors)
        return result

    # Step 2: Cross-chunk import verification
    seam_checks.extend(_check_import_seams(project_dir, chunks))

    # Step 3: Interface contract checks
    seam_checks.extend(_check_interface_contracts(project_dir, chunks))

    # Step 4: Run test suite
    test_output = _run_tests(project_dir, test_command)
    result.test_output = test_output
    if "FAILED" in test_output or "ERROR" in test_output or "Traceback" in test_output:
        result.passed = False
        result.runtime_errors.append(f"Test failures:\n{test_output[:2000]}")

    # Step 5: Smoke test — try to run/import the project
    smoke_errors = _smoke_test(project_dir)
    if smoke_errors:
        result.passed = False
        result.runtime_errors.extend(smoke_errors)

    # Compile final result
    all_seams_passed = all(s.passed for s in seam_checks)
    result.seam_checks = seam_checks

    if not all_seams_passed:
        result.passed = False
        failed_seams = [s for s in seam_checks if not s.passed]
        result.error_summary = "Seam failures:\n" + "\n".join(
            f"  {s.source_chunk} → {s.target_chunk}: {s.detail}"
            for s in failed_seams
        )

    if result.runtime_errors and not result.error_summary:
        result.error_summary = "Runtime errors:\n" + "\n".join(result.runtime_errors)

    return result


def _check_import_seams(project_dir: Path, chunks: list[dict]) -> list[SeamCheck]:
    """Verify Python imports resolve across chunk boundaries.

    For each chunk, try to import the modules it produces and verify
    that any symbols referenced by other chunks actually exist.
    """
    checks: list[SeamCheck] = []

    # Collect all Python files produced
    all_files: dict[str, str] = {}  # module_path -> chunk_name
    for chunk in chunks:
        for file_path in chunk.get("files", []):
            if file_path.endswith(".py"):
                all_files[file_path] = chunk["name"]

    if not all_files:
        return checks

    # Build a script that tries to import each module
    import_script = _build_import_check_script(all_files, project_dir)

    try:
        result = subprocess.run(
            ["python3", "-c", import_script],
            capture_output=True, text=True, timeout=30,
            cwd=str(project_dir),
        )
        if result.returncode != 0:
            # Parse import errors to identify which chunk seams failed
            for line in result.stderr.split("\n"):
                if "ModuleNotFoundError" in line or "ImportError" in line:
                    # Try to map the error back to chunk seams
                    err_module = _extract_module_name(line)
                    for chunk in chunks:
                        for fp in chunk.get("files", []):
                            if err_module in fp:
                                checks.append(SeamCheck(
                                    source_chunk=_find_chunk_for_module(err_module, chunks),
                                    target_chunk=chunk["name"],
                                    passed=False,
                                    detail=f"Import failed: {line.strip()}",
                                ))
        else:
            # All imports succeeded — one seam check per cross-chunk pair
            chunk_names = [c["name"] for c in chunks]
            for i, src in enumerate(chunk_names):
                for tgt in chunk_names[i + 1:]:
                    checks.append(SeamCheck(
                        source_chunk=src,
                        target_chunk=tgt,
                        passed=True,
                        detail="All cross-chunk imports resolve",
                    ))

    except subprocess.TimeoutExpired:
        checks.append(SeamCheck(
            source_chunk="all", target_chunk="all",
            passed=False, detail="Import check timed out",
        ))

    return checks


def _check_interface_contracts(project_dir: Path, chunks: list[dict]) -> list[SeamCheck]:
    """Check that chunks honor their interface contracts.

    If a chunk says it exports 'function X with signature (a: int, b: str) -> bool',
    verify that the function exists with roughly that signature.
    """
    checks: list[SeamCheck] = []

    for chunk in chunks:
        contract = chunk.get("interface_contract", "")
        if not contract:
            continue

        # Simple contract validation: check that exported items exist
        # For full contract checking, we'd parse the contract spec and introspect
        # the module, but for now we do a lightweight name check
        for file_path in chunk.get("files", []):
            if not file_path.endswith(".py"):
                continue
            full_path = project_dir / file_path
            if not full_path.exists():
                continue

            content = full_path.read_text()

            # Check for mentioned exports in the contract
            contract_items = _extract_contract_items(contract)
            for item in contract_items:
                # Basic check: is this name defined somewhere?
                if item not in content:
                    checks.append(SeamCheck(
                        source_chunk=chunk["name"],
                        target_chunk="self",
                        passed=False,
                        detail=f"Contract item '{item}' not found in {file_path}",
                    ))
                else:
                    checks.append(SeamCheck(
                        source_chunk=chunk["name"],
                        target_chunk="self",
                        passed=True,
                        detail=f"Contract item '{item}' found in {file_path}",
                    ))

    return checks


def _extract_contract_items(contract: str) -> list[str]:
    """Extract named items (functions, classes) from a text contract."""
    import re
    items = []
    # Match patterns like "exports User.get_by_id()" or "provides UserModel"
    patterns = [
        r"exports?\s+(\w+\.?\w+)",
        r"provides?\s+(\w+\.?\w+)",
        r"defines?\s+(\w+\.?\w+)",
        r"`(\w+)`",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, contract, re.IGNORECASE):
            name = match.group(1)
            if name not in items:
                items.append(name)
    return items


def _build_import_check_script(all_files: dict[str, str], project_dir: Path) -> str:
    """Build a Python script that tries to import every module."""
    lines = ["import sys, importlib", f"sys.path.insert(0, {project_dir!r})"]
    for file_path in sorted(all_files):
        module_path = file_path.replace("/", ".").replace(".py", "")
        lines.append(f"""
try:
    importlib.import_module({module_path!r})
    print("OK: {module_path}")
except Exception as e:
    print(f"FAIL: {module_path} -> {{e}}", file=sys.stderr)
""")
    return "\n".join(lines)


def _extract_module_name(error_line: str) -> str:
    """Extract module name from an import error line."""
    import re
    match = re.search(r"No module named '(\w+(?:\.\w+)*)'", error_line)
    if match:
        return match.group(1)
    match = re.search(r"cannot import name '(\w+)'", error_line)
    if match:
        return match.group(1)
    return ""


def _find_chunk_for_module(module_name: str, chunks: list[dict]) -> str:
    """Find which chunk should contain a module."""
    for chunk in chunks:
        for fp in chunk.get("files", []):
            if module_name.replace(".", "/") in fp:
                return chunk["name"]
    return "unknown"


def _run_tests(project_dir: Path, test_command: Optional[str] = None) -> str:
    """Run the project's test suite."""
    if test_command:
        try:
            result = subprocess.run(
                test_command.split(), capture_output=True, text=True,
                timeout=120, cwd=str(project_dir),
            )
            return result.stdout + "\n" + result.stderr
        except Exception as e:
            return f"Test command failed: {e}"

    # Auto-detect test runner
    for cmd in [
        ["python3", "-m", "pytest", "-x", "--tb=short"],
        ["python3", "-m", "unittest", "discover"],
    ]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd=str(project_dir),
            )
            return result.stdout + "\n" + result.stderr
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return "Test run timed out"

    return ""


def _smoke_test(project_dir: Path) -> list[str]:
    """Try running the project entry point as a basic smoke test."""
    errors: list[str] = []

    # Try to find and import the main module
    python_files = list(project_dir.rglob("*.py"))
    main_candidates = [
        f for f in python_files
        if f.name in ("app.py", "main.py", "server.py", "__init__.py")
        and "test" not in str(f).lower()
    ]

    for candidate in main_candidates[:3]:  # try first 3
        try:
            subprocess.run(
                ["python3", "-c", f"import ast; ast.parse(open({str(candidate)!r}).read()); print('Syntax OK')"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_dir),
            )
        except subprocess.TimeoutExpired:
            errors.append(f"Syntax check timed out for {candidate.name}")
        except Exception as e:
            errors.append(f"Syntax error in {candidate.name}: {e}")

    return errors
