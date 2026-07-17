#!/usr/bin/env python3
"""Unit tests for behavioral_runner and QA loop."""

import json
import time
from pathlib import Path

import pytest

from src.core.behavioral_runner import (
    BehavioralTest,
    TestResult,
    TestSuiteResult,
    ProcessManager,
    HTTPTestExecutor,
    CLITestExecutor,
    run_test_suite,
)
from src.core.qa_loop import (
    QALoop,
    QAResult,
    GapReport,
    ClassifiedGap,
    create_qa_loop_from_config,
)


# ── BehavioralTest ────────────────────────────────────────────────────


class TestBehavioralTest:
    def test_http_test_creation(self):
        t = BehavioralTest(
            name="homepage",
            description="Check homepage loads",
            type="http",
            method="GET",
            url="/",
            expected_status=200,
            expected_body_contains=["Welcome"],
        )
        assert t.type == "http"
        assert t.method == "GET"
        assert "Welcome" in t.expected_body_contains

    def test_cli_test_creation(self):
        t = BehavioralTest(
            name="help",
            description="Check help output",
            type="cli",
            command="python app.py --help",
            expected_exit_code=0,
            expected_stdout_contains=["usage"],
        )
        assert t.type == "cli"
        assert "usage" in t.expected_stdout_contains

    def test_defaults(self):
        t = BehavioralTest(name="test", description="", type="cli")
        assert t.criticality == "medium"
        assert t.timeout == 10
        assert t.expected_status == 200
        assert t.expected_exit_code == 0


# ── TestResult ────────────────────────────────────────────────────────


class TestTestResult:
    def test_passed_summary(self):
        r = TestResult(
            test=BehavioralTest(name="test", description="", type="cli"),
            passed=True,
            duration_seconds=0.5,
        )
        assert "PASS" in r.summary

    def test_failed_summary(self):
        r = TestResult(
            test=BehavioralTest(name="test", description="", type="http"),
            passed=False,
            error="404 not found",
            duration_seconds=0.3,
        )
        assert "FAIL" in r.summary

    def test_failure_detail_http(self):
        r = TestResult(
            test=BehavioralTest(
                name="home",
                description="Homepage check",
                type="http",
                expected_status=200,
                expected_body_contains=["Hello"],
            ),
            passed=False,
            actual_status=500,
            actual_body="Internal Error",
            error="Expected status 200, got 500",
        )
        detail = r.failure_detail
        assert "home" in detail.lower()
        assert "500" in detail

    def test_failure_detail_cli(self):
        r = TestResult(
            test=BehavioralTest(
                name="run",
                description="CLI run",
                type="cli",
                expected_exit_code=0,
            ),
            passed=False,
            actual_stdout="error occurred",
            actual_stderr="Traceback...",
            error="Expected exit 0, got 1",
        )
        detail = r.failure_detail
        assert "Traceback" in detail

    def test_failure_detail_with_error(self):
        r = TestResult(
            test=BehavioralTest(name="test", description="", type="cli"),
            passed=False,
            error="Connection refused",
        )
        detail = r.failure_detail
        assert "Connection refused" in detail


# ── TestSuiteResult ───────────────────────────────────────────────────


class TestTestSuiteResult:
    def test_empty_suite(self):
        s = TestSuiteResult(tests=[])
        assert s.all_passed
        assert s.failures == []
        assert s.critical_failures == []

    def test_mixed_suite(self):
        tests = [
            TestResult(
                test=BehavioralTest(name="pass", description="", type="cli", criticality="low"),
                passed=True,
            ),
            TestResult(
                test=BehavioralTest(name="fail", description="", type="cli", criticality="critical"),
                passed=False,
            ),
            TestResult(
                test=BehavioralTest(name="error", description="", type="cli", criticality="high"),
                passed=False,
                error="timeout",
            ),
        ]
        s = TestSuiteResult(tests=tests, passed=1, failed=1, errors=1)
        assert not s.all_passed
        assert len(s.failures) == 2
        assert len(s.critical_failures) == 1
        assert s.critical_failures[0].test.name == "fail"


# ── ProcessManager ────────────────────────────────────────────────────


class TestProcessManager:
    def test_detect_entry_point_flask(self, tmp_path):
        (tmp_path / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
        pm = ProcessManager(tmp_path)
        entry = pm.detect_entry_point()
        assert entry is not None
        assert "app.py" in entry

    def test_detect_entry_point_procfile(self, tmp_path):
        (tmp_path / "Procfile").write_text("web: gunicorn app:app\n")
        pm = ProcessManager(tmp_path)
        entry = pm.detect_entry_point()
        assert entry == "gunicorn app:app"

    def test_detect_entry_point_makefile(self, tmp_path):
        (tmp_path / "Makefile").write_text("run:\n\tpython app.py\n")
        pm = ProcessManager(tmp_path)
        entry = pm.detect_entry_point()
        assert entry is not None
        assert "make" in entry

    def test_detect_entry_point_none(self, tmp_path):
        pm = ProcessManager(tmp_path)
        entry = pm.detect_entry_point()
        assert entry is None

    def test_start_stop_cli(self, tmp_path):
        """Start a simple Python process, confirm it runs, then stop it."""
        (tmp_path / "echo.py").write_text("import time; time.sleep(10)\n")
        pm = ProcessManager(tmp_path)
        ok, msg = pm.start(command="python echo.py")
        assert ok, msg
        assert pm.is_running()
        pm.stop()
        # Give it a moment to clean up
        time.sleep(0.5)
        assert not pm.is_running()

    def test_is_http_service_detection(self):
        pm = ProcessManager(".")
        assert pm._is_http_service("flask run")
        assert pm._is_http_service("uvicorn app:app")
        assert pm._is_http_service("python app.py")
        assert not pm._is_http_service("python script.py")
        assert not pm._is_http_service("ls -la")


# ── HTTPTestExecutor ──────────────────────────────────────────────────


class TestHTTPTestExecutor:
    def test_execute_basic(self):
        # This will fail (no server running) but shouldn't crash
        executor = HTTPTestExecutor(base_url="http://127.0.0.1:1")
        test = BehavioralTest(
            name="should_fail",
            description="No server running",
            type="http",
            method="GET",
            url="/",
            expected_status=200,
            timeout=1,
        )
        result = executor.execute(test)
        assert not result.passed
        assert result.error  # should have an error message

    def test_execute_serialization(self):
        """Result should be JSON-serializable for orchestrator return."""
        executor = HTTPTestExecutor()
        test = BehavioralTest(
            name="test",
            description="",
            type="http",
            url="/",
            timeout=1,
        )
        result = executor.execute(test)
        # Should not raise
        data = {
            "passed": result.passed,
            "error": result.error,
            "duration": result.duration_seconds,
        }
        json.dumps(data)


# ── CLITestExecutor ───────────────────────────────────────────────────


class TestCLITestExecutor:
    def test_execute_passing(self):
        executor = CLITestExecutor(project_root=".")
        test = BehavioralTest(
            name="echo",
            description="Echo test",
            type="cli",
            command="echo hello",
            expected_exit_code=0,
            expected_stdout_contains=["hello"],
        )
        result = executor.execute(test)
        assert result.passed
        assert "hello" in result.actual_stdout

    def test_execute_failing_exit_code(self):
        executor = CLITestExecutor(project_root=".")
        test = BehavioralTest(
            name="false",
            description="False command",
            type="cli",
            command="python -c 'exit(1)'",
            expected_exit_code=0,
        )
        result = executor.execute(test)
        assert not result.passed
        assert "exit" in result.error

    def test_execute_timeout(self, tmp_path):
        (tmp_path / "slow.py").write_text("import time; time.sleep(10)\n")
        executor = CLITestExecutor(project_root=str(tmp_path))
        test = BehavioralTest(
            name="slow",
            description="Slow script",
            type="cli",
            command="python slow.py",
            timeout=1,
        )
        result = executor.execute(test)
        assert not result.passed
        assert "timed out" in result.error.lower()


# ── Gap Classification ────────────────────────────────────────────────


class TestGapClassification:
    def test_classified_gap_fields(self):
        gap = ClassifiedGap(
            test_name="homepage",
            description="Homepage check",
            failure_detail="Expected status 200, got 500",
            gap_type="implementation_bug",
            target_tier="l0-coder",
            fix_instruction="Fix the server error in app.py",
            criticality="critical",
        )
        assert gap.gap_type == "implementation_bug"
        assert gap.target_tier == "l0-coder"

    def test_gap_report_by_tier(self):
        gaps = [
            ClassifiedGap(
                test_name="a", description="", failure_detail="",
                gap_type="implementation_bug", target_tier="l0-coder",
                fix_instruction="fix a",
            ),
            ClassifiedGap(
                test_name="b", description="", failure_detail="",
                gap_type="implementation_bug", target_tier="l0-coder",
                fix_instruction="fix b",
            ),
            ClassifiedGap(
                test_name="c", description="", failure_detail="",
                gap_type="missing_feature", target_tier="l0-planner",
                fix_instruction="add c",
            ),
        ]
        report = GapReport(gaps=gaps, total_tests=5, passed=2, failed=3)
        by_tier = report.by_tier
        assert len(by_tier["l0-coder"]) == 2
        assert len(by_tier["l0-planner"]) == 1

    def test_gap_report_has_gaps(self):
        assert not GapReport().has_gaps
        assert GapReport(gaps=[ClassifiedGap(
            test_name="x", description="", failure_detail="",
            gap_type="implementation_bug", target_tier="l0-coder",
            fix_instruction="fix",
        )]).has_gaps

    def test_feedback_for_tier(self):
        gaps = [
            ClassifiedGap(
                test_name="test1", description="desc1",
                failure_detail="detail1", gap_type="implementation_bug",
                target_tier="l0-coder", fix_instruction="Fix the bug",
            ),
        ]
        report = GapReport(gaps=gaps, total_tests=3, passed=2, failed=1)
        feedback = report.feedback_for_tier("l0-coder")
        assert "test1" in feedback
        assert "Fix the bug" in feedback
        assert report.feedback_for_tier("nonexistent") == ""


# ── QALoop ────────────────────────────────────────────────────────────


class TestQALoop:
    def test_factory_disabled(self):
        assert create_qa_loop_from_config(".", {"enabled": False}) is None

    def test_factory_enabled(self):
        qa = create_qa_loop_from_config(".", {"enabled": True})
        assert isinstance(qa, QALoop)

    def test_factory_none_config(self):
        assert create_qa_loop_from_config(".", None) is None

    def test_detect_project_type_flask(self):
        qa = QALoop(project_root=".")
        files = {
            "app.py": "from flask import Flask\n@app.route('/')\ndef home():\n    return 'hello'\n",
        }
        ptype = qa._detect_project_type(files)
        assert "flask" in ptype

    def test_detect_project_type_cli(self):
        qa = QALoop(project_root=".")
        files = {
            "main.py": "import argparse\n\ndef main():\n    pass\n\nif __name__ == '__main__':\n    main()\n",
        }
        ptype = qa._detect_project_type(files)
        assert "cli" in ptype.lower()

    def test_detect_project_type_unknown(self):
        qa = QALoop(project_root=".")
        files = {"data.csv": "a,b,c\n1,2,3\n"}
        ptype = qa._detect_project_type(files)
        assert "unknown" in ptype

    def test_heuristic_test_generation_flask(self):
        qa = QALoop(project_root=".")
        tests = qa._generate_tests_heuristic(
            task_spec="Build a Flask app with /login and /dashboard endpoints",
            files={"app.py": "from flask import Flask\n"},
            project_type="flask",
        )
        assert len(tests) > 0
        # Should include homepage test
        homepage = [t for t in tests if t.name == "Homepage loads"]
        assert len(homepage) == 1
        assert homepage[0].criticality == "critical"

    def test_heuristic_test_generation_cli(self):
        qa = QALoop(project_root=".")
        tests = qa._generate_tests_heuristic(
            task_spec="Build a CLI tool for file processing",
            files={"cli.py": "def main(): pass\n"},
            project_type="cli tool",
        )
        assert len(tests) > 0
        cli_test = [t for t in tests if t.name == "CLI runs"]
        assert len(cli_test) == 1

    def test_parse_tests_from_judge_output(self):
        qa = QALoop(project_root=".")
        text = (
            "TEST: Homepage loads\n"
            "DESCRIPTION: Verify the homepage returns 200\n"
            "TYPE: http\n"
            "METHOD: GET\n"
            "URL: /\n"
            "EXPECTED_STATUS: 200\n"
            "EXPECTED_CONTAINS: Welcome\n"
            "CRITICALITY: critical\n"
            "---\n"
            "TEST: API health\n"
            "DESCRIPTION: Verify health endpoint\n"
            "TYPE: http\n"
            "METHOD: GET\n"
            "URL: /api/health\n"
            "EXPECTED_STATUS: 200\n"
            "EXPECTED_CONTAINS: ok\n"
            "CRITICALITY: high\n"
        )
        tests = qa._parse_tests_from_judge_output(text)
        assert len(tests) == 2
        assert tests[0].name == "Homepage loads"
        assert tests[0].criticality == "critical"
        assert tests[1].name == "API health"

    def test_classify_gaps_heuristic(self):
        qa = QALoop(project_root=".")
        from src.core.behavioral_runner import TestResult, TestSuiteResult
        failures = [
            TestResult(
                test=BehavioralTest(name="crash", description="", type="http"),
                passed=False,
                error="Process exited immediately",
            ),
            TestResult(
                test=BehavioralTest(name="500", description="", type="http"),
                passed=False,
                actual_status=500,
                error="Expected status 200, got 500",
            ),
            TestResult(
                test=BehavioralTest(name="404", description="", type="http", url="/missing"),
                passed=False,
                actual_status=404,
                error="Expected status 200, got 404",
            ),
        ]
        gaps = qa._classify_gaps_heuristic(failures)
        assert len(gaps) == 3
        # Crash → architectural → principal
        assert gaps[0].gap_type == "architectural"
        assert gaps[0].target_tier == "principal"
        # 500 → implementation bug → coder
        assert gaps[1].gap_type == "implementation_bug"
        assert gaps[1].target_tier == qa.coder_tier
        # 404 → missing feature → orchestrator
        assert gaps[2].gap_type == "missing_feature"
        assert gaps[2].target_tier == qa.orchestrator_tier


# ── QAResult ──────────────────────────────────────────────────────────


class TestQAResult:
    def test_passed_result(self):
        r = QAResult(passed=True)
        assert "PASSED" in r.summary

    def test_failed_result(self):
        report = GapReport(gaps=[], total_tests=5, passed=3, failed=2)
        r = QAResult(passed=False, gap_report=report)
        assert "3/5" in r.summary

    def test_error_result(self):
        r = QAResult(passed=False, error="Connection refused")
        assert "ERROR" in r.summary
        assert "Connection refused" in r.summary
