#!/usr/bin/env python3
"""Runtime Verifier — Loop 2 of Steinberger's Four Loops (build → verify → fix → scale).

Runs after Judge acceptance to actually execute the produced code and catch
runtime errors before declaring success. Auto-detects the project's test/run
command, falling back to config if needed.

Architecture:
    Judge accepts → RuntimeVerifier.verify() → runtime OK? → return success
                                            → runtime errors? → (phase 2: fix loop)

Auto-detection priority:
    1. pytest (pyproject.toml, pytest.ini, setup.cfg, tox.ini)
    2. Python unittest (discover pattern)
    3. Makefile test target
    4. package.json scripts.test
    5. Config-specified command
    6. Bare `python -c "import <project>; ..."` sanity import
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VerifyResult:
    """Result of a runtime verification attempt."""

    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    command: str
    duration_seconds: float
    attempts: int = 1
    errors: list[str] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        """Human-readable error summary for feedback to the coder."""
        if self.passed:
            return ""
        lines = []
        lines.append(f"Command: {self.command}")
        lines.append(f"Exit code: {self.exit_code}")
        # Extract the most useful error lines
        stderr_tail = _extract_error_lines(self.stderr)
        if stderr_tail:
            lines.append(f"Errors:\n{stderr_tail}")
        stdout_tail = _extract_error_lines(self.stdout)
        if stdout_tail and stdout_tail != stderr_tail:
            lines.append(f"Output:\n{stdout_tail}")
        return "\n".join(lines)


def _extract_error_lines(text: str, max_lines: int = 40) -> str:
    """Extract the most informative error lines from output.

    Prioritizes: tracebacks, FAILED lines, ERROR lines, then last N lines.
    """
    if not text.strip():
        return ""
    lines = text.splitlines()

    # Look for traceback
    tb_start = None
    for i, line in enumerate(lines):
        if "Traceback (most recent call last)" in line:
            tb_start = i
            break
    if tb_start is not None:
        return "\n".join(lines[tb_start:tb_start + max_lines])

    # Look for FAILED/ERROR lines
    failures = [l for l in lines if "FAILED" in l or "ERROR" in l or "Error:" in l]
    if failures:
        return "\n".join(failures[:max_lines])

    # Return last N lines
    return "\n".join(lines[-max_lines:])


class RuntimeVerifier:
    """Run and verify code produced by MR-Krabs coder tiers.

    Hooks into execute_with_judge() after Judge acceptance. Attempts to
    actually run the project's test suite or entry point, captures output,
    and surfaces runtime errors.
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        command: str | None = None,
        timeout: int = 300,
        max_retries: int = 3,
    ):
        self.project_root = Path(project_root)
        self._config_command = command
        self.timeout = timeout
        self.max_retries = max_retries

    # ── Public API ─────────────────────────────────────────────────

    def verify(self, files: dict[str, str] | None = None) -> VerifyResult:
        """Run the project's verification command and return results.

        Args:
            files: Dict of path → content for files produced by the coder.
                   Used for sanity checks (file existence, syntax).

        Returns:
            VerifyResult with pass/fail, exit code, output, and error details.
        """
        start = time.monotonic()
        command = self._detect_command(files)

        if command is None:
            # No test command found — do a basic syntax check instead
            return self._syntax_check(files)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.project_root),
            )
            duration = time.monotonic() - start

            stdout = proc.stdout
            stderr = proc.stderr

            passed = proc.returncode == 0
            errors = []
            if not passed:
                errors = self._parse_errors(stdout, stderr)

            return VerifyResult(
                passed=passed,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                command=command,
                duration_seconds=duration,
                errors=errors,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return VerifyResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {self.timeout}s: {command}",
                command=command,
                duration_seconds=duration,
                errors=[f"Verification timed out after {self.timeout} seconds"],
            )
        except Exception as e:
            duration = time.monotonic() - start
            return VerifyResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                command=command,
                duration_seconds=duration,
                errors=[f"Verification failed: {e}"],
            )

    # ── Command Detection ──────────────────────────────────────────

    def _detect_command(self, files: dict[str, str] | None = None) -> str | None:
        """Auto-detect the best verification command for the project.

        Priority:
          1. Config-specified command (explicit override)
          2. pytest (if pyproject.toml/pytest.ini/etc. exist)
          3. unittest discover (if test_*.py files found)
          4. Makefile test target
          5. package.json scripts.test
          6. Fall back to syntax-only check
        """
        if self._config_command:
            return self._config_command

        root = self.project_root

        # 1. pytest — if any pytest config file exists
        pytest_configs = ["pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"]
        if any((root / f).exists() for f in pytest_configs):
            return "python -m pytest -x --tb=short 2>&1"

        # 2. pytest — if test files exist even without config
        test_files = list(root.rglob("test_*.py")) + list(root.rglob("*_test.py"))
        if test_files:
            return "python -m pytest -x --tb=short 2>&1"

        # 3. unittest — if test files exist
        if test_files:
            return "python -m unittest discover -v 2>&1"

        # 4. Makefile test target
        makefile = root / "Makefile"
        if makefile.exists():
            content = makefile.read_text()
            if re.search(r"^test\s*:", content, re.MULTILINE):
                return "make test 2>&1"

        # 5. package.json scripts.test
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                if pkg.get("scripts", {}).get("test"):
                    return "npm test 2>&1"
            except (json.JSONDecodeError, OSError):
                pass

        # 6. No test infrastructure found — try a basic import sanity check
        return self._infer_sanity_check(files)

    def _infer_sanity_check(self, files: dict[str, str] | None = None) -> str | None:
        """Infer a basic sanity check: try to import the main module.

        Scans files for the most likely entry point (app.py, main.py, etc.)
        and runs `python -c "import <module>"` to catch ImportError/SyntaxError.
        """
        if not files:
            return None

        # Look for entry-point patterns in file paths
        entry_patterns = ["app.py", "main.py", "server.py", "run.py", "cli.py"]
        entry_files = [p for p in files if os.path.basename(p) in entry_patterns]
        python_files = [p for p in files if p.endswith(".py")]

        candidates = entry_files or python_files
        if not candidates:
            return None

        # Pick the most likely entry point
        candidate = candidates[0]

        # Convert path to a Python module-ish import
        # e.g., "src/app.py" → "src.app" (strip .py, replace / with .)
        module_path = candidate.replace(".py", "").replace("/", ".").replace("\\", ".")
        # Strip leading dots
        module_path = module_path.lstrip(".")

        if not module_path:
            return None

        return (
            f"python -c \"import sys; sys.path.insert(0, '.'); "
            f"__import__('{module_path}')\" 2>&1"
        )

    # ── Syntax Check (fallback) ────────────────────────────────────

    def _syntax_check(self, files: dict[str, str] | None = None) -> VerifyResult:
        """Basic Python syntax check when no test infrastructure exists.

        Runs `python -m py_compile` on each Python file. Catches SyntaxError
        and IndentationError without executing any code.
        """
        start = time.monotonic()
        if not files:
            return VerifyResult(
                passed=True,  # nothing to check
                exit_code=0,
                stdout="No files to verify",
                stderr="",
                command="(no test infrastructure detected)",
                duration_seconds=0.0,
            )

        python_files = [p for p in files if p.endswith(".py")]
        if not python_files:
            return VerifyResult(
                passed=True,
                exit_code=0,
                stdout="No Python files to syntax-check",
                stderr="",
                command="(no Python files found)",
                duration_seconds=0.0,
            )

        errors = []
        for fpath in python_files:
            full_path = self.project_root / fpath
            if not full_path.exists():
                errors.append(f"File not found: {fpath}")
                continue
            try:
                proc = subprocess.run(
                    ["python", "-m", "py_compile", str(full_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode != 0:
                    errors.append(f"{fpath}: {proc.stderr.strip() or proc.stdout.strip()}")
            except subprocess.TimeoutExpired:
                errors.append(f"{fpath}: compile timed out")
            except Exception as e:
                errors.append(f"{fpath}: {e}")

        duration = time.monotonic() - start
        passed = len(errors) == 0

        return VerifyResult(
            passed=passed,
            exit_code=0 if passed else 1,
            stdout=f"Syntax-checked {len(python_files)} files: "
                    f"{len(python_files) - len(errors)} passed, "
                    f"{len(errors)} failed",
            stderr="\n".join(errors),
            command="python -m py_compile (per-file)",
            duration_seconds=duration,
            errors=errors,
        )

    # ── Error Parsing ──────────────────────────────────────────────

    def _parse_errors(self, stdout: str, stderr: str) -> list[str]:
        """Parse stdout/stderr into actionable error messages.

        Extracts: tracebacks, pytest FAILED lines, assertion errors,
        import errors. Deduplicates and returns a clean list.
        """
        combined = (stderr + "\n" + stdout).strip()
        if not combined:
            return ["Unknown runtime error (no output captured)"]

        errors: list[str] = []
        lines = combined.splitlines()

        # Extract traceback blocks
        tb_lines: list[str] = []
        in_tb = False
        for line in lines:
            if "Traceback (most recent call last)" in line:
                if tb_lines:
                    errors.append("\n".join(tb_lines))
                    tb_lines = []
                in_tb = True
                tb_lines.append(line)
            elif in_tb:
                tb_lines.append(line)
                # Stop at the actual error
                if re.match(r'^\S.*Error:', line) and not line.startswith(" "):
                    errors.append("\n".join(tb_lines))
                    tb_lines = []
                    in_tb = False
            elif "FAILED" in line:
                errors.append(line.strip())
            elif "ERROR" in line and "ERRORS" not in line:
                errors.append(line.strip())

        # Catch leftover traceback
        if tb_lines:
            errors.append("\n".join(tb_lines))

        # If nothing structured found, return last 10 lines
        if not errors:
            errors = [l.strip() for l in lines[-10:] if l.strip()]

        # Deduplicate
        seen = set()
        unique = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)

        return unique[:20]  # cap at 20 errors


def create_verifier_from_config(
    project_root: str | Path = ".",
    config: dict | None = None,
) -> RuntimeVerifier | None:
    """Create a RuntimeVerifier from config, or None if verify is disabled.

    Config format:
        verify:
          enabled: true
          command: "python -m pytest -x --tb=short"
          max_retries: 3
          timeout: 300
    """
    if config is None:
        return None

    enabled = config.get("enabled", False)
    if not enabled:
        return None

    return RuntimeVerifier(
        project_root=project_root,
        command=config.get("command"),
        timeout=int(config.get("timeout", 300)),
        max_retries=int(config.get("max_retries", 3)),
    )
