#!/usr/bin/env python3
"""End-to-end smoke tests for Multi-Tier Orchestrator."""
import os, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.core.orchestrator import LLMOrchestrator, FileTools, ToolExecutor
from src.validators.startup import StartupValidator

class SmokeTestResult:
    def __init__(self, name):
        self.name, self.passed, self.error, self.duration = name, False, None, 0.0
    def __str__(self):
        s = "PASS" if self.passed else "FAIL"
        return f"[{s}] {self.name} ({self.duration:.1f}s)" + (f" - {self.error}" if self.error else "")

def test_startup():
    r = SmokeTestResult("Startup Validation")
    t0 = time.time()
    try:
        v = StartupValidator()
        ok, _ = v.validate_all()
        r.passed = ok
    except Exception as e: r.error = str(e)
    r.duration = time.time() - t0
    return r

def test_executor_custom():
    r = SmokeTestResult("ToolExecutor Custom")
    t0 = time.time()
    try:
        ex = ToolExecutor(FileTools(PROJECT_ROOT))
        res = ex.parse_and_execute_tools('file_write("t1.txt", """c""")')
        r.passed = res["tools_executed"] == 1
    except Exception as e: r.error = str(e)
    r.duration = time.time() - t0
    return r

def test_executor_claude():
    r = SmokeTestResult("ToolExecutor Claude")
    t0 = time.time()
    try:
        ex = ToolExecutor(FileTools(PROJECT_ROOT))
        res = ex.parse_and_execute_tools('{"name":"write_file","parameters":{"path":"t2.txt","content":"d"}}')
        r.passed = res["tools_executed"] >= 1
    except Exception as e: r.error = str(e)
    r.duration = time.time() - t0
    return r

def run_all():
    print("=" * 60)
    print("SMOKE TESTS")
    print("=" * 60)
    tests = [test_startup, test_executor_custom, test_executor_claude]
    results = [t() for t in tests]
    for r in results: print(r)
    print("=" * 60)
    passed = sum(1 for r in results if r.passed)
    print(f"Results: {passed}/{len(results)} passed")
    return all(r.passed for r in results)

if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
