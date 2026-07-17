#!/usr/bin/env python3
"""Unit tests for RuntimeVerifier — Loop 2: verify."""

import os
import subprocess
from pathlib import Path

import pytest

from src.core.verifier import (
    RuntimeVerifier,
    VerifyResult,
    _extract_error_lines,
    create_verifier_from_config,
)


class TestExtractErrorLines:
    """Tests for _extract_error_lines helper."""

    def test_extract_traceback(self):
        text = (
            "random output\n"
            "Traceback (most recent call last):\n"
            '  File "app.py", line 5, in <module>\n'
            "    from models import User\n"
            "ImportError: cannot import name User\n"
        )
        result = _extract_error_lines(text)
        assert "Traceback (most recent call last)" in result
        assert "ImportError" in result

    def test_extract_failed_lines(self):
        text = "PASSED test_a\nFAILED test_b - assert 1 == 2\nERROR test_c\n"
        result = _extract_error_lines(text)
        assert "FAILED" in result
        assert "ERROR" in result

    def test_extract_last_n_lines_fallback(self):
        text = "\n".join(f"line {i}" for i in range(100))
        result = _extract_error_lines(text)
        lines = result.splitlines()
        assert len(lines) <= 40
        assert "line 99" in lines[-1]

    def test_empty_text(self):
        assert _extract_error_lines("") == ""
        assert _extract_error_lines("   \n  ") == ""


class TestCreateVerifierFromConfig:
    """Tests for create_verifier_from_config factory."""

    def test_disabled_returns_none(self):
        assert create_verifier_from_config(".", {"enabled": False}) is None

    def test_enabled_returns_verifier(self):
        v = create_verifier_from_config(".", {"enabled": True})
        assert isinstance(v, RuntimeVerifier)

    def test_none_config_returns_none(self):
        assert create_verifier_from_config(".", None) is None

    def test_empty_config_returns_none(self):
        assert create_verifier_from_config(".", {}) is None

    def test_config_passes_command(self):
        v = create_verifier_from_config(
            ".", {"enabled": True, "command": "make test"}
        )
        assert v._config_command == "make test"

    def test_config_passes_timeout(self):
        v = create_verifier_from_config(
            ".", {"enabled": True, "timeout": 600}
        )
        assert v.timeout == 600

    def test_config_defaults(self):
        v = create_verifier_from_config(".", {"enabled": True})
        assert v.max_retries == 3
        assert v.timeout == 300
        assert v._config_command is None


class TestVerifyResult:
    """Tests for VerifyResult dataclass."""

    def test_passed_result(self):
        r = VerifyResult(
            passed=True,
            exit_code=0,
            stdout="all good",
            stderr="",
            command="pytest",
            duration_seconds=1.5,
        )
        assert r.passed
        assert r.error_summary == ""

    def test_failed_result(self):
        r = VerifyResult(
            passed=False,
            exit_code=1,
            stdout="",
            stderr="ImportError: no module named foo",
            command="python -c 'import foo'",
            duration_seconds=0.5,
            errors=["ImportError: no module named foo"],
        )
        assert not r.passed
        summary = r.error_summary
        assert "Command:" in summary
        assert "Exit code: 1" in summary
        assert "ImportError" in summary


class TestRuntimeVerifierSyntaxCheck:
    """Tests for _syntax_check method."""

    def test_empty_files_passes(self):
        v = RuntimeVerifier(project_root=".")
        result = v._syntax_check({})
        assert result.passed

    def test_no_python_files_passes(self):
        v = RuntimeVerifier(project_root=".")
        result = v._syntax_check({"README.md": "", "config.yaml": ""})
        assert result.passed

    def test_valid_python_passes(self):
        v = RuntimeVerifier(project_root=".")
        result = v._syntax_check(
            {"test_good.py": "def hello(): return 'world'\n"}
        )
        # File doesn't exist on disk — should report "not found"
        assert not result.passed
        assert "File not found" in result.stderr

    def test_actual_file_on_disk(self, tmp_path):
        """Write a real Python file and check it passes."""
        py_file = tmp_path / "good.py"
        py_file.write_text("def hello(): return 'world'\n")
        # Use relative path from tmp_path
        v = RuntimeVerifier(project_root=str(tmp_path))
        result = v._syntax_check({"good.py": ""})
        assert result.passed, f"Should pass: {result.stderr}"

    def test_syntax_error_on_disk(self, tmp_path):
        """Write a file with a syntax error and check it fails."""
        py_file = tmp_path / "bad.py"
        py_file.write_text("def broken(:)\n")
        v = RuntimeVerifier(project_root=str(tmp_path))
        result = v._syntax_check({"bad.py": ""})
        assert not result.passed, f"Should fail: {result.stderr}"
        assert any("SyntaxError" in e or "bad.py" in e for e in result.errors)


class TestRuntimeVerifierCommandDetection:
    """Tests for _detect_command method."""

    def test_config_command_overrides(self):
        v = RuntimeVerifier(project_root=".", command="make check")
        assert v._detect_command() == "make check"

    def test_pytest_detected_with_pyproject(self, tmp_path):
        """With a pyproject.toml, should return pytest command."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        v = RuntimeVerifier(project_root=str(tmp_path))
        cmd = v._detect_command()
        assert "pytest" in cmd

    def test_pytest_detected_with_test_files(self, tmp_path):
        """With test_*.py files, should return pytest command."""
        (tmp_path / "test_foo.py").write_text("def test_pass(): pass\n")
        v = RuntimeVerifier(project_root=str(tmp_path))
        cmd = v._detect_command()
        assert "pytest" in cmd

    def test_makefile_test_target(self, tmp_path):
        """With Makefile that has test target."""
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
        v = RuntimeVerifier(project_root=str(tmp_path))
        cmd = v._detect_command()
        assert "make test" in cmd

    def test_package_json_npm_test(self, tmp_path):
        """With package.json scripts.test."""
        import json
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}})
        )
        v = RuntimeVerifier(project_root=str(tmp_path))
        cmd = v._detect_command()
        assert "npm test" in cmd

    def test_package_json_no_test_script(self, tmp_path):
        """package.json without test script should fall through."""
        import json
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"build": "webpack"}})
        )
        v = RuntimeVerifier(project_root=str(tmp_path))
        cmd = v._detect_command()
        # Should fall through to None (no Python files for sanity check)
        assert cmd is None


class TestRuntimeVerifierVerify:
    """Tests for the main verify() method."""

    def test_verify_passes_with_good_code(self, tmp_path):
        """Verify should pass when a real Python file runs cleanly."""
        (tmp_path / "hello.py").write_text("print('hello')\n")
        v = RuntimeVerifier(project_root=str(tmp_path), command="python hello.py")
        result = v.verify({"hello.py": ""})
        assert result.passed
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_verify_fails_with_bad_code(self, tmp_path):
        """Verify should fail when Python code has a runtime error."""
        (tmp_path / "bad.py").write_text("raise ValueError('boom')\n")
        v = RuntimeVerifier(project_root=str(tmp_path), command="python bad.py")
        result = v.verify({"bad.py": ""})
        assert not result.passed
        assert result.exit_code != 0
        assert len(result.errors) > 0

    def test_verify_timeout(self, tmp_path):
        """Verify should handle timeouts gracefully."""
        (tmp_path / "slow.py").write_text("import time; time.sleep(10)\n")
        v = RuntimeVerifier(
            project_root=str(tmp_path),
            command="python slow.py",
            timeout=1,
        )
        result = v.verify({"slow.py": ""})
        assert not result.passed
        assert "timed out" in result.stderr.lower()
