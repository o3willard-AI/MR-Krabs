#!/usr/bin/env python3
"""QA Loop — Loop 3 of Steinberger's Four Loops (build → verify → fix → scale).

Orchestrates behavioral testing of completed projects:
    1. Generates behavioral tests from the task spec (using Judge)
    2. Starts the project, executes tests against the live system
    3. Classifies failures: implementation bug, missing feature, architectural
    4. Routes feedback to the appropriate tier for fixes

Architecture:
    QALoop.evaluate()
      ├── _generate_tests() → Judge interprets spec → list[BehavioralTest]
      ├── run_test_suite()  → start project → execute tests → results
      └── _classify_gaps()  → categorize failures → GapReport

    GapReport routes feedback:
      - implementation_bugs → coder tier (targeted file fixes)
      - missing_features   → orchestrator (re-plan needed)
      - architectural      → principal (design issue)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.behavioral_runner import (
    BehavioralTest,
    TestSuiteResult,
    run_test_suite,
)
from src.core.judge import Judge, Verdict


# ── Data Classes ────────────────────────────────────────────────────────


@dataclass
class ClassifiedGap:
    """A single failure classified by type and target tier."""

    test_name: str
    description: str
    failure_detail: str
    gap_type: str  # "implementation_bug", "missing_feature", "architectural"
    target_tier: str  # "l0-coder", "l1-coder", "orchestrator", "principal"
    fix_instruction: str
    criticality: str = "medium"


@dataclass
class GapReport:
    """Classified failures from behavioral QA, ready for fix routing."""

    gaps: list[ClassifiedGap] = field(default_factory=list)
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    duration_seconds: float = 0.0

    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0

    @property
    def critical_gaps(self) -> list[ClassifiedGap]:
        return [g for g in self.gaps if g.criticality == "critical"]

    @property
    def by_tier(self) -> dict[str, list[ClassifiedGap]]:
        """Group gaps by target tier for routing."""
        grouped: dict[str, list[ClassifiedGap]] = {}
        for gap in self.gaps:
            grouped.setdefault(gap.target_tier, []).append(gap)
        return grouped

    def feedback_for_tier(self, tier: str) -> str:
        """Generate fix feedback text for a specific tier."""
        gaps = self.by_tier.get(tier, [])
        if not gaps:
            return ""

        lines = [f"## QA Behavioral Test Failures — {tier}\n"]
        lines.append(f"{len(gaps)} issue(s) found during behavioral testing:\n")
        for i, gap in enumerate(gaps, 1):
            lines.append(f"### Issue {i}: {gap.test_name}")
            lines.append(f"**Type:** {gap.gap_type}")
            lines.append(f"**Detail:** {gap.failure_detail}")
            lines.append(f"**Fix:** {gap.fix_instruction}")
            lines.append("")
        return "\n".join(lines)

    def summary(self) -> str:
        """One-line summary."""
        return (
            f"QA: {self.passed}/{self.total_tests} passed, "
            f"{self.failed} failed → "
            f"{len(self.by_tier)} tiers need fixes"
        )


@dataclass
class QAResult:
    """Full result of a QA evaluation run."""

    passed: bool
    suite_result: TestSuiteResult | None = None
    gap_report: GapReport | None = None
    error: str = ""
    duration_seconds: float = 0.0

    @property
    def summary(self) -> str:
        if self.error:
            return f"QA ERROR: {self.error}"
        if self.passed:
            return "QA PASSED — all behavioral tests passed"
        return self.gap_report.summary() if self.gap_report else "QA FAILED"


# ── QA Loop ─────────────────────────────────────────────────────────────


class QALoop:
    """Loop 3: Behavioral QA — test the running system against the spec.

    Hooks in after Loop 2 (verify) passes. Actually starts the project,
    runs behavioral tests, and classifies failures for routing back to
    the coder/orchestrator/principal tiers.
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        judge_model: str = "Judge",
        coder_tier: str = "l0-coder",
        orchestrator_tier: str = "l0-planner",
        timeout: int = 300,
    ):
        self.project_root = Path(project_root)
        self.judge_model = judge_model
        self.coder_tier = coder_tier
        self.orchestrator_tier = orchestrator_tier
        self.timeout = timeout

    # ── Public API ─────────────────────────────────────────────────

    def evaluate(
        self,
        task_spec: str,
        files: dict[str, str] | None = None,
        *,
        base_url: str = "http://127.0.0.1:5000",
    ) -> QAResult:
        """Run the full QA evaluation: generate tests, execute, classify.

        Args:
            task_spec: The original task specification.
            files: Dict of path → content for produced files.
            base_url: Base URL for HTTP tests.

        Returns:
            QAResult with pass/fail and gap report.
        """
        start = time.monotonic()

        # 1. Generate behavioral tests from spec
        tests, gen_error = self._generate_tests(task_spec, files)
        if gen_error:
            return QAResult(
                passed=False,
                error=f"Test generation failed: {gen_error}",
                duration_seconds=time.monotonic() - start,
            )
        if not tests:
            return QAResult(
                passed=True,  # Nothing to test — assume ok
                duration_seconds=time.monotonic() - start,
            )

        print(f"[QA] Generated {len(tests)} behavioral tests from spec")

        # 2. Execute tests against the running project
        suite_result = run_test_suite(
            tests=tests,
            project_root=self.project_root,
            base_url=base_url,
        )

        print(f"[QA] {suite_result.passed}/{suite_result.passed + suite_result.failed + suite_result.errors} "
              f"passed ({suite_result.duration_seconds:.1f}s)")

        if suite_result.all_passed:
            # Check spec coverage even if all generated tests pass.
            # A project can pass 2 trivial tests while missing 6 of 8
            # spec requirements — that's a skeleton, not a working project.
            coverage = self._compute_spec_coverage(task_spec, suite_result)
            if coverage < 0.50:  # Below 50% spec coverage is a failure
                print(f"[QA] All tests passed but spec coverage is only "
                      f"{coverage:.0%} — flagging as incomplete")
                gap_report = GapReport(
                    total_tests=suite_result.passed + suite_result.failed + suite_result.errors,
                    passed=suite_result.passed,
                    duration_seconds=suite_result.duration_seconds,
                    gaps=[ClassifiedGap(
                        test_name="spec_coverage",
                        description=f"Only {coverage:.0%} of spec requirements verified",
                        failure_detail=(
                            f"The project passed all behavioral tests but only "
                            f"covers {coverage:.0%} of the requirements in the "
                            f"specification. Missing requirements need to be "
                            f"implemented."
                        ),
                        gap_type="missing_feature",
                        target_tier=self.orchestrator_tier,
                        fix_instruction=(
                            f"Re-plan the project to include ALL spec "
                            f"requirements. Current coverage: {coverage:.0%}. "
                            f"Expected: ≥70%."
                        ),
                        criticality="critical",
                    )],
                )
            else:
                return QAResult(
                    passed=True,
                    suite_result=suite_result,
                    duration_seconds=time.monotonic() - start,
                )

        # 3. Classify failures into gaps
        gap_report = self._classify_gaps(
            task_spec=task_spec,
            suite_result=suite_result,
            files=files,
        )

        print(f"[QA] {len(gap_report.gaps)} gaps classified → "
              f"{', '.join(f'{tier}: {len(gaps)}' for tier, gaps in gap_report.by_tier.items())}")

        return QAResult(
            passed=False,
            suite_result=suite_result,
            gap_report=gap_report,
            duration_seconds=time.monotonic() - start,
        )

    # ── Spec Coverage ────────────────────────────────────────────

    def _compute_spec_coverage(self, task_spec: str, suite_result: TestSuiteResult) -> float:
        """Estimate what fraction of spec requirements have passing tests.

        Extracts requirement-like phrases from the spec (MUST, should,
        implement, create, build, support) and checks how many match
        passing behavioral test names/descriptions.

        Returns a float 0.0–1.0. Below 0.50 the project is a skeleton.
        """
        requirements = _extract_requirement_phrases(task_spec)
        if not requirements:
            return 1.0  # No requirements found — can't measure coverage

        passed_names = {t.name.lower() for t in suite_result.passed_tests}
        passed_descs = " ".join(
            t.description.lower() for t in suite_result.passed_tests
        )

        matched = 0
        for req in requirements:
            req_lower = req.lower()
            # Check if any passing test name or description references this requirement
            if any(req_lower in name for name in passed_names):
                matched += 1
            elif req_lower in passed_descs:
                matched += 1

        return matched / len(requirements)

    # ── Test Generation ────────────────────────────────────────────

    def _generate_tests(
        self, task_spec: str, files: dict[str, str] | None = None
    ) -> tuple[list[BehavioralTest], str]:
        """Generate behavioral tests from the task specification.

        Uses the Judge model to interpret the spec and produce test cases.
        Returns (tests, error_message).
        """
        # Detect project type to customize test generation
        project_type = self._detect_project_type(files or {})

        prompt = self._build_test_generation_prompt(task_spec, files, project_type)

        try:
            judge = Judge(model=self.judge_model)
            verdict = judge.evaluate(
                task=prompt,
                output="",  # We're generating, not evaluating
            )
            # Parse the judge's critique as test cases
            tests = self._parse_tests_from_judge_output(verdict.critique)
            if not tests:
                # Try parsing from a simpler prompt
                tests = self._generate_tests_via_raw_call(prompt)
            return tests, ""
        except Exception as e:
            # Fall back to heuristic test generation
            tests = self._generate_tests_heuristic(task_spec, files, project_type)
            return tests, ""

    def _build_test_generation_prompt(
        self, task_spec: str, files: dict[str, str] | None, project_type: str
    ) -> str:
        """Build the prompt for test generation."""
        file_list = "\n".join(f"- {p}" for p in (files or {}).keys()) if files else "(no files)"

        return (
            f"Generate behavioral tests for a completed software project. "
            f"The tests must verify that the project matches its specification.\n\n"
            f"## Project Type\n{project_type}\n\n"
            f"## Original Task Specification\n{task_spec}\n\n"
            f"## Files Produced\n{file_list}\n\n"
            f"Generate test cases in this exact format:\n\n"
            f"```\n"
            f"TEST: <test name>\n"
            f"DESCRIPTION: <what this test verifies>\n"
            f"TYPE: http|cli\n"
            f"METHOD: GET|POST|PUT|DELETE  (http only)\n"
            f"URL: /path  (http only)\n"
            f"EXPECTED_STATUS: 200  (http only)\n"
            f"EXPECTED_CONTAINS: <text that must appear in response>  (http only)\n"
            f"COMMAND: <shell command>  (cli only)\n"
            f"EXPECTED_EXIT: 0  (cli only)\n"
            f"EXPECTED_STDOUT: <text that must appear in stdout>  (cli only)\n"
            f"CRITICALITY: critical|high|medium|low\n"
            f"---\n"
            f"```\n\n"
            f"Generate tests that verify the core functionality described in the spec. "
            f"Focus on behavior, not implementation details. "
            f"For HTTP services: test each endpoint with expected responses. "
            f"For CLI tools: test each command with expected output. "
            f"Include both happy-path and edge-case tests."
        )

    def _parse_tests_from_judge_output(self, text: str) -> list[BehavioralTest]:
        """Parse behavioral tests from Judge model output."""
        tests: list[BehavioralTest] = []
        # Split on test boundaries
        blocks = re.split(r"\n(?=TEST:)", text)
        for block in blocks:
            block = block.strip()
            if not block or not block.startswith("TEST:"):
                continue

            test = BehavioralTest(name="", description="", type="cli")
            lines = block.split("\n")
            current_field = None
            current_value: list[str] = []

            for line in lines:
                line = line.strip()
                # Check for field headers
                field_match = re.match(
                    r"^(TEST|DESCRIPTION|TYPE|METHOD|URL|EXPECTED_STATUS|"
                    r"EXPECTED_CONTAINS|EXPECTED_EXIT|EXPECTED_STDOUT|"
                    r"EXPECTED_STDERR|COMMAND|CRITICALITY):\s*(.*)",
                    line, re.IGNORECASE,
                )
                if field_match:
                    # Save previous field
                    if current_field:
                        self._apply_field(test, current_field, "\n".join(current_value).strip())
                    current_field = field_match.group(1).upper()
                    current_value = [field_match.group(2)]
                elif current_field:
                    current_value.append(line)

            # Apply last field
            if current_field:
                self._apply_field(test, current_field, "\n".join(current_value).strip())

            if test.name:
                tests.append(test)

        # Post-process: strip any trailing separator artifacts
        for test in tests:
            for field in ["name", "description", "criticality"]:
                value = getattr(test, field, "")
                if isinstance(value, str) and "---" in value:
                    setattr(test, field, value.split("---")[0].strip())

        return tests

    def _apply_field(self, test: BehavioralTest, field: str, value: str) -> None:
        """Apply a parsed field to a BehavioralTest."""
        field = field.upper()
        value = value.strip()

        if field == "TEST":
            test.name = value
        elif field == "DESCRIPTION":
            test.description = value
        elif field == "TYPE":
            test.type = value.lower()
        elif field == "METHOD":
            test.method = value.upper()
        elif field == "URL":
            test.url = value
        elif field == "EXPECTED_STATUS":
            try:
                test.expected_status = int(value)
            except ValueError:
                pass
        elif field == "EXPECTED_CONTAINS":
            if value:
                test.expected_body_contains.append(value)
        elif field == "EXPECTED_EXIT":
            try:
                test.expected_exit_code = int(value)
            except ValueError:
                pass
        elif field == "EXPECTED_STDOUT":
            if value:
                test.expected_stdout_contains.append(value)
        elif field == "EXPECTED_STDERR":
            if value:
                test.expected_stderr_contains.append(value)
        elif field == "COMMAND":
            test.command = value
        elif field == "CRITICALITY":
            test.criticality = value.lower()

    def _generate_tests_via_raw_call(self, prompt: str) -> list[BehavioralTest]:
        """Fallback: generate tests via raw LLM call (simpler parsing)."""
        # For now, return empty — heuristic fallback handles this
        return []

    def _generate_tests_heuristic(
        self, task_spec: str, files: dict[str, str] | None, project_type: str
    ) -> list[BehavioralTest]:
        """Heuristic test generation when Judge is unavailable.

        Generates basic smoke tests based on project structure.
        """
        tests: list[BehavioralTest] = []
        project_type = project_type.lower()

        if "flask" in project_type or "fastapi" in project_type or "http" in project_type:
            # Basic HTTP smoke tests
            tests.append(BehavioralTest(
                name="Homepage loads",
                description="Verify the homepage returns 200",
                type="http", method="GET", url="/",
                expected_status=200,
                criticality="critical",
            ))
            # Check if spec mentions specific endpoints
            endpoint_pattern = re.findall(r'/([\w/-]+)', task_spec)
            for ep in set(endpoint_pattern[:5]):
                if len(ep) > 2 and not ep.startswith("/"):
                    tests.append(BehavioralTest(
                        name=f"Endpoint /{ep}",
                        description=f"Verify /{ep} endpoint",
                        type="http", method="GET", url=f"/{ep}",
                        expected_status=200,
                        criticality="high",
                    ))

        elif "cli" in project_type or "command" in project_type:
            # Basic CLI smoke test
            entry_files = [p for p in (files or {}).keys()
                          if p.endswith(".py") and "main" in p.lower()
                          or p.endswith(".py") and "cli" in p.lower()]
            if entry_files:
                tests.append(BehavioralTest(
                    name="CLI runs",
                    description="Verify the CLI runs without error",
                    type="cli",
                    command=f"python {entry_files[0]} --help",
                    expected_exit_code=0,
                    criticality="critical",
                ))

        return tests

    # ── Project Type Detection ─────────────────────────────────────

    def _detect_project_type(self, files: dict[str, str]) -> str:
        """Detect the project type from produced files."""
        filenames = list(files.keys())
        file_contents = "\n".join(
            files.get(p, "")[:200] for p in filenames[:5]
        ).lower()

        indicators = {
            "flask": ["flask", "from flask import", "@app.route"],
            "fastapi": ["fastapi", "from fastapi import"],
            "django": ["django", "from django"],
            "node.js express": ["express()", "require('express')"],
            "react": ["react", "from 'react'"],
            "cli tool": ["argparse", "click.", "def main(", "if __name__"],
        }

        for ptype, keywords in indicators.items():
            if any(kw in file_contents for kw in keywords):
                return ptype

        # Check file extensions
        exts = {Path(p).suffix for p in filenames}
        if ".py" in exts:
            return "python project (type unknown)"
        if ".js" in exts or ".ts" in exts:
            return "javascript/typescript project"

        return "unknown"


def _extract_requirement_phrases(spec: str) -> list[str]:
    """Extract requirement-like phrases from a task specification.

    Looks for sentences containing action verbs that indicate a
    requirement: must, should, implement, create, build, support,
    handle, verify, test.

    Returns a deduplicated list of requirement phrases.
    """
    requirement_patterns = [
        r'(?:must|should|shall|needs?\s+to)\s+(\w[\w\s]{10,80}?)[.!]',
        r'(?:implement|create|build|develop|write)\s+(?:a\s+)?(\w[\w\s]{10,80}?)[.!]',
        r'(?:support|handle|process|verify|test)\s+(\w[\w\s]{10,80}?)[.!]',
        r'(?:the\s+\w+\s+(?:must|should))\s+(\w[\w\s]{10,80}?)[.!]',
    ]

    phrases = set()
    for pattern in requirement_patterns:
        for match in re.finditer(pattern, spec, re.IGNORECASE):
            phrase = match.group(1).strip().lower()
            if len(phrase) > 10:  # Filter noise
                phrases.add(phrase)

    return list(phrases)

    # ── Gap Classification ─────────────────────────────────────────

    def _classify_gaps(
        self,
        task_spec: str,
        suite_result: TestSuiteResult,
        files: dict[str, str] | None = None,
    ) -> GapReport:
        """Classify test failures into implementation bugs, missing features,
        or architectural issues. Routes each to the appropriate tier.

        Uses the Judge model for classification when available; falls back
        to heuristic classification.
        """
        gaps: list[ClassifiedGap] = []
        failures = suite_result.failures

        if not failures:
            return GapReport(
                total_tests=suite_result.passed + suite_result.failed + suite_result.errors,
                passed=suite_result.passed,
                duration_seconds=suite_result.duration_seconds,
            )

        # Build classification prompt
        failure_details = "\n\n".join(
            f"### {r.test.name}\n{r.failure_detail}" for r in failures
        )

        prompt = (
            f"Classify these behavioral test failures. For each failure, determine:\n"
            f"1. The gap type:\n"
            f"   - implementation_bug: code doesn't work correctly (wrong logic, bugs)\n"
            f"   - missing_feature: spec requires this but it wasn't implemented\n"
            f"   - architectural: fundamental design problem (wrong structure, missing component)\n"
            f"2. The target tier for the fix:\n"
            f"   - {self.coder_tier}: straightforward code fixes\n"
            f"   - {self.orchestrator_tier}: needs re-planning or task decomposition\n"
            f"   - principal: fundamental redesign needed\n"
            f"3. A specific fix instruction.\n\n"
            f"## Original Specification\n{task_spec[:1000]}\n\n"
            f"## Test Failures\n{failure_details}\n\n"
            f"Respond in this format for each failure:\n"
            f"```\n"
            f"TEST: <test name>\n"
            f"GAP_TYPE: implementation_bug|missing_feature|architectural\n"
            f"TARGET_TIER: {self.coder_tier}|{self.orchestrator_tier}|principal\n"
            f"FIX: <specific fix instruction>\n"
            f"---\n"
            f"```"
        )

        try:
            judge = Judge(model=self.judge_model)
            verdict = judge.evaluate(task=prompt, output="")
            gaps = self._parse_gaps_from_judge(verdict.critique, failures)
        except Exception:
            pass

        # Fall back to heuristic if Judge didn't produce gaps
        if not gaps:
            gaps = self._classify_gaps_heuristic(failures)

        return GapReport(
            gaps=gaps,
            total_tests=suite_result.passed + suite_result.failed + suite_result.errors,
            passed=suite_result.passed,
            failed=len(failures),
            duration_seconds=suite_result.duration_seconds,
        )

    def _parse_gaps_from_judge(
        self, text: str, failures: list
    ) -> list[ClassifiedGap]:
        """Parse classified gaps from Judge output."""
        gaps: list[ClassifiedGap] = []
        failure_map = {f.test.name: f for f in failures}

        blocks = re.split(r"\n(?=TEST:|---)", text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            test_name = ""
            gap_type = "implementation_bug"
            target_tier = self.coder_tier
            fix = ""

            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("TEST:"):
                    test_name = line[5:].strip()
                elif line.startswith("GAP_TYPE:"):
                    gap_type = line[9:].strip()
                elif line.startswith("TARGET_TIER:"):
                    target_tier = line[12:].strip()
                elif line.startswith("FIX:"):
                    fix = line[4:].strip()
                elif fix and line:
                    fix += " " + line

            if test_name:
                failure = failure_map.get(test_name)
                gaps.append(ClassifiedGap(
                    test_name=test_name,
                    description=failure.test.description if failure else "",
                    failure_detail=failure.failure_detail if failure else "",
                    gap_type=gap_type,
                    target_tier=target_tier,
                    fix_instruction=fix,
                    criticality=failure.test.criticality if failure else "medium",
                ))

        return gaps

    def _classify_gaps_heuristic(self, failures: list) -> list[ClassifiedGap]:
        """Heuristic gap classification without Judge.

        Rules of thumb:
        - 500/404 errors → implementation_bug → coder
        - Empty responses / missing content → missing_feature → orchestrator
        - Process crashes / startup failures → architectural → principal
        """
        gaps: list[ClassifiedGap] = []
        for failure in failures:
            detail = failure.failure_detail.lower()
            error = failure.error.lower()

            if "process exited immediately" in error or "failed to start" in error:
                gap_type = "architectural"
                target = "principal"
                fix = "Project failed to start. Check entry point, dependencies, and configuration."
            elif "500" in error or "internal server" in error:
                gap_type = "implementation_bug"
                target = self.coder_tier
                fix = f"Fix server error in {failure.test.name}. Check the endpoint implementation."
            elif "404" in error or "not found" in error:
                gap_type = "missing_feature"
                target = self.orchestrator_tier
                fix = f"Missing endpoint or route: {failure.test.url}. Add this route."
            elif "missing in response" in error.lower():
                gap_type = "missing_feature"
                target = self.coder_tier
                fix = f"Response missing expected content for {failure.test.name}."
            elif "timeout" in error:
                gap_type = "implementation_bug"
                target = self.coder_tier
                fix = f"Request timed out for {failure.test.name}. Check for infinite loops or blocking calls."
            else:
                gap_type = "implementation_bug"
                target = self.coder_tier
                fix = f"Fix test failure: {failure.test.name}"

            gaps.append(ClassifiedGap(
                test_name=failure.test.name,
                description=failure.test.description,
                failure_detail=failure.failure_detail,
                gap_type=gap_type,
                target_tier=target,
                fix_instruction=fix,
                criticality=failure.test.criticality,
            ))

        return gaps


# ── Factory ──────────────────────────────────────────────────────────────


def create_qa_loop_from_config(
    project_root: str | Path = ".",
    config: dict | None = None,
) -> QALoop | None:
    """Create a QALoop from config, or None if QA is disabled.

    Config format:
        qa:
          enabled: true
          judge_model: judge
          coder_tier: l0-coder
          orchestrator_tier: l0-planner
          timeout: 300
    """
    if config is None:
        return None

    enabled = config.get("enabled", False)
    if not enabled:
        return None

    return QALoop(
        project_root=project_root,
        judge_model=config.get("judge_model", "judge"),
        coder_tier=config.get("coder_tier", "l0-coder"),
        orchestrator_tier=config.get("orchestrator_tier", "l0-planner"),
        timeout=int(config.get("timeout", 300)),
    )
