#!/usr/bin/env python3
"""Behavioral Test Runner — starts projects, runs HTTP/CLI tests, captures results.

Part of Loop 3 (QA). Handles the mechanical work of exercising a running
project so the QALoop can focus on test generation and gap classification.

Supports:
    - HTTP services (Flask, FastAPI, Django, etc.) — start, poll, hit endpoints
    - CLI programs — run with args, capture stdout/stderr/exit code
    - Process lifecycle management — start, health-check, stop, cleanup
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


# ── Data Classes ────────────────────────────────────────────────────────


@dataclass
class BehavioralTest:
    """A single behavioral test case."""

    name: str
    description: str
    type: str  # "http" or "cli"
    # HTTP fields
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    expected_status: int = 200
    expected_body_contains: list[str] = field(default_factory=list)
    expected_body_regex: str | None = None
    # CLI fields
    command: str = ""
    expected_exit_code: int = 0
    expected_stdout_contains: list[str] = field(default_factory=list)
    expected_stderr_contains: list[str] = field(default_factory=list)
    # Metadata
    criticality: str = "medium"  # "critical", "high", "medium", "low"
    timeout: int = 10


@dataclass
class TestResult:
    """Result of executing a single behavioral test."""

    test: BehavioralTest
    passed: bool
    actual_status: int | None = None
    actual_body: str = ""
    actual_stdout: str = ""
    actual_stderr: str = ""
    duration_seconds: float = 0.0
    error: str = ""

    @property
    def summary(self) -> str:
        """One-line summary for logging."""
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.test.name} ({self.duration_seconds:.1f}s)"

    @property
    def failure_detail(self) -> str:
        """Detailed failure report for feedback."""
        lines = [f"Test: {self.test.name}", f"Description: {self.test.description}"]
        if self.error:
            lines.append(f"Error: {self.error}")
        if self.test.type == "http":
            lines.append(f"Expected status: {self.test.expected_status}")
            lines.append(f"Actual status: {self.actual_status}")
            for expected in self.test.expected_body_contains:
                if expected not in self.actual_body:
                    lines.append(f"Missing in response: '{expected}'")
        elif self.test.type == "cli":
            lines.append(f"Expected exit code: {self.test.expected_exit_code}")
            if self.actual_stdout:
                lines.append(f"Stdout (first 500 chars):\n{self.actual_stdout[:500]}")
            if self.actual_stderr:
                lines.append(f"Stderr (first 500 chars):\n{self.actual_stderr[:500]}")
        return "\n".join(lines)


@dataclass
class TestSuiteResult:
    """Results from executing a full suite of behavioral tests."""

    tests: list[TestResult]
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def failures(self) -> list[TestResult]:
        return [r for r in self.tests if not r.passed]

    @property
    def critical_failures(self) -> list[TestResult]:
        return [r for r in self.failures if r.test.criticality == "critical"]


# ── Process Manager ─────────────────────────────────────────────────────


class ProcessManager:
    """Start, health-check, and stop a test project process."""

    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root)
        self._process: subprocess.Popen | None = None
        self._entry_point: str = ""

    # ── Entry Point Detection ──────────────────────────────────────

    def detect_entry_point(self) -> str | None:
        """Detect how to start the project.

        Priority:
          1. Procfile (Heroku-style)
          2. package.json scripts.start
          3. Makefile run/server/start target
          4. app.py / main.py / server.py / run.py (Flask/FastAPI)
          5. setup.py / pyproject.toml console_scripts
        """
        root = self.project_root

        # 1. Procfile
        procfile = root / "Procfile"
        if procfile.exists():
            for line in procfile.read_text().splitlines():
                line = line.strip()
                if line.startswith("web:") or line.startswith("app:"):
                    self._entry_point = line.split(":", 1)[1].strip()
                    return self._entry_point

        # 2. package.json
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                start = pkg.get("scripts", {}).get("start")
                if start:
                    self._entry_point = f"npm start"
                    return self._entry_point
            except (json.JSONDecodeError, OSError):
                pass

        # 3. Makefile
        makefile = root / "Makefile"
        if makefile.exists():
            content = makefile.read_text()
            for target in ["run", "start", "serve"]:
                if re.search(rf"^{target}\s*:", content, re.MULTILINE):
                    self._entry_point = f"make {target}"
                    return self._entry_point

        # 4. Common Python entry points
        for candidate in ["app.py", "main.py", "server.py", "run.py", "manage.py"]:
            if (root / candidate).exists():
                content = (root / candidate).read_text()
                # Check if it's a Flask/FastAPI app
                if "flask" in content.lower() or "fastapi" in content.lower():
                    self._entry_point = f"python {candidate}"
                    return self._entry_point
                # Generic Python entry
                self._entry_point = f"python {candidate}"
                return self._entry_point

        # 5. Python package with console_scripts
        setup_py = root / "setup.py"
        if setup_py.exists():
            self._entry_point = "python -m <project>"
            return self._entry_point

        return None

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(
        self,
        command: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> tuple[bool, str]:
        """Start the project process. Returns (success, message).

        Args:
            command: Override auto-detected command.
            env: Extra environment variables.
            timeout: Max seconds to wait for health check.
        """
        cmd = command or self._entry_point or self.detect_entry_point()
        if not cmd:
            return False, "Could not detect how to start the project"

        # Build environment
        proc_env = os.environ.copy()
        proc_env.update(env or {})
        # Common Flask/FastAPI defaults
        proc_env.setdefault("FLASK_APP", "app.py")
        proc_env.setdefault("FLASK_ENV", "development")
        proc_env.setdefault("PYTHONUNBUFFERED", "1")

        try:
            self._process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(self.project_root),
                env=proc_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # process group for cleanup
            )
        except Exception as e:
            return False, f"Failed to start process: {e}"

        # Health check — wait for the service to be ready
        time.sleep(1)  # brief startup grace
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                # Process died — collect stderr
                stderr = ""
                try:
                    stderr = self._process.stderr.read().decode()[:500] if self._process.stderr else ""
                except Exception:
                    pass
                return False, f"Process exited immediately (code {self._process.returncode}): {stderr}"

            # Try health check — HTTP on common ports
            if self._is_http_service(cmd):
                if self._health_check_http():
                    return True, f"Service healthy on detected port (PID {self._process.pid})"
            else:
                # CLI tool — just confirm it's still running after 2s
                if time.monotonic() - deadline + timeout > 2:
                    return True, f"CLI process running (PID {self._process.pid})"

            time.sleep(0.5)

        return False, f"Health check timed out after {timeout}s"

    def stop(self) -> None:
        """Stop the process and clean up."""
        if self._process is None:
            return
        try:
            # Kill the entire process group
            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                self._process.wait(timeout=2)
        except (ProcessLookupError, OSError):
            pass
        finally:
            self._process = None

    def is_running(self) -> bool:
        """Check if the process is still alive."""
        return self._process is not None and self._process.poll() is None

    # ── Health Checks ──────────────────────────────────────────────

    def _is_http_service(self, command: str) -> bool:
        """Heuristic: does this command likely start an HTTP service?"""
        http_keywords = ["flask", "fastapi", "uvicorn", "gunicorn", "django",
                         "node", "npm", "http", "serve", "app.py", "server.py"]
        return any(kw in command.lower() for kw in http_keywords)

    def _health_check_http(self, ports: list[int] | None = None) -> bool:
        """Try to connect to common HTTP ports."""
        ports = ports or [5000, 8000, 3000, 8080, 4000]
        for port in ports:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/",
                    headers={"User-Agent": "MR-Krabs-QA/1.0"},
                )
                urllib.request.urlopen(req, timeout=2)
                return True
            except Exception:
                continue
        return False


# ── Test Executors ───────────────────────────────────────────────────────


class HTTPTestExecutor:
    """Execute HTTP-based behavioral tests against a running service."""

    def __init__(self, base_url: str = "http://127.0.0.1:5000"):
        self.base_url = base_url.rstrip("/")

    def execute(self, test: BehavioralTest) -> TestResult:
        """Execute a single HTTP test."""
        start = time.monotonic()
        url = test.url if test.url.startswith("http") else f"{self.base_url}{test.url}"

        try:
            data = test.body.encode() if test.body else None
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "User-Agent": "MR-Krabs-QA/1.0",
                    "Content-Type": "application/json",
                    **test.headers,
                },
                method=test.method,
            )
            resp = urllib.request.urlopen(req, timeout=test.timeout)
            body = resp.read().decode()
            status = resp.status

            # Check expectations
            failures: list[str] = []
            if status != test.expected_status:
                failures.append(f"Expected status {test.expected_status}, got {status}")

            for expected in test.expected_body_contains:
                if expected not in body:
                    failures.append(f"Expected body to contain '{expected}'")

            if test.expected_body_regex:
                if not re.search(test.expected_body_regex, body, re.DOTALL):
                    failures.append(f"Body doesn't match regex: {test.expected_body_regex}")

            duration = time.monotonic() - start
            passed = len(failures) == 0

            return TestResult(
                test=test,
                passed=passed,
                actual_status=status,
                actual_body=body[:2000],
                duration_seconds=duration,
                error="; ".join(failures),
            )

        except urllib.error.HTTPError as e:
            duration = time.monotonic() - start
            body = ""
            try:
                body = e.read().decode()[:2000]
            except Exception:
                pass
            passed = test.expected_status == e.code and not test.expected_body_contains
            return TestResult(
                test=test,
                passed=passed,
                actual_status=e.code,
                actual_body=body,
                duration_seconds=duration,
                error=f"HTTP {e.code}" if not passed else "",
            )
        except Exception as e:
            duration = time.monotonic() - start
            return TestResult(
                test=test,
                passed=False,
                duration_seconds=duration,
                error=str(e),
            )


class CLITestExecutor:
    """Execute CLI-based behavioral tests."""

    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root)

    def execute(self, test: BehavioralTest) -> TestResult:
        """Execute a single CLI test."""
        start = time.monotonic()
        try:
            proc = subprocess.run(
                test.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=test.timeout,
                cwd=str(self.project_root),
            )
            stdout = proc.stdout
            stderr = proc.stderr

            failures: list[str] = []
            if proc.returncode != test.expected_exit_code:
                failures.append(
                    f"Expected exit {test.expected_exit_code}, got {proc.returncode}"
                )

            for expected in test.expected_stdout_contains:
                if expected not in stdout:
                    failures.append(f"Expected stdout to contain '{expected}'")

            for expected in test.expected_stderr_contains:
                if expected not in stderr:
                    failures.append(f"Expected stderr to contain '{expected}'")

            duration = time.monotonic() - start
            passed = len(failures) == 0

            return TestResult(
                test=test,
                passed=passed,
                actual_stdout=stdout[:2000],
                actual_stderr=stderr[:2000],
                duration_seconds=duration,
                error="; ".join(failures),
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return TestResult(
                test=test,
                passed=False,
                duration_seconds=duration,
                error=f"Command timed out after {test.timeout}s",
            )
        except Exception as e:
            duration = time.monotonic() - start
            return TestResult(
                test=test,
                passed=False,
                duration_seconds=duration,
                error=str(e),
            )


# ── Suite Runner ─────────────────────────────────────────────────────────


def run_test_suite(
    tests: list[BehavioralTest],
    project_root: str | Path = ".",
    base_url: str = "http://127.0.0.1:5000",
) -> TestSuiteResult:
    """Run a full suite of behavioral tests against a project.

    Handles process lifecycle: detect entry point, start, run tests, stop.
    """
    proc_mgr = ProcessManager(project_root)
    http_exec = HTTPTestExecutor(base_url)
    cli_exec = CLITestExecutor(project_root)

    results: list[TestResult] = []
    suite_start = time.monotonic()

    # Start the project
    ok, msg = proc_mgr.start()
    if not ok:
        # All tests fail if we can't start
        for test in tests:
            results.append(TestResult(
                test=test, passed=False,
                error=f"Failed to start project: {msg}",
            ))
        return TestSuiteResult(
            tests=results,
            errors=len(results),
            duration_seconds=time.monotonic() - suite_start,
        )

    # Execute tests
    for test in tests:
        try:
            if test.type == "http":
                result = http_exec.execute(test)
            elif test.type == "cli":
                result = cli_exec.execute(test)
            else:
                result = TestResult(test=test, passed=False, error=f"Unknown test type: {test.type}")
        except Exception as e:
            result = TestResult(test=test, passed=False, error=str(e))
        results.append(result)

    # Stop the project
    proc_mgr.stop()

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.error)
    errors = sum(1 for r in results if r.error and not r.passed)

    return TestSuiteResult(
        tests=results,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_seconds=time.monotonic() - suite_start,
    )
