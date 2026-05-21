#!/usr/bin/env python3
"""Unit tests for LLMOrchestrator leaf methods — pure logic, no HTTP."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.orchestrator import LLMOrchestrator


class TestOrchestratorLeafMethods(unittest.TestCase):
    """Tests for pure leaf methods with zero side effects beyond filesystem/env."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        # Create docs/workflow/templates/ for template tests
        (self.project_root / "docs" / "workflow" / "templates").mkdir(parents=True)
        self.orchestrator = LLMOrchestrator(project_root=str(self.project_root))

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── get_api_key ───────────────────────────────────────────────

    def test_get_api_key_env_var_set(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-test-123"
        try:
            result = self.orchestrator.get_api_key("L1-Coder")
            self.assertEqual(result, "sk-test-123")
        finally:
            del os.environ["OPENROUTER_API_KEY"]

    def test_get_api_key_env_var_not_set(self):
        # Ensure key is absent
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = self.orchestrator.get_api_key("L1-Coder")
        self.assertIsNone(result)

    def test_get_api_key_unknown_tier(self):
        result = self.orchestrator.get_api_key("BOGUS_TIER")
        self.assertIsNone(result)

    # ── _simplify_context ─────────────────────────────────────────

    def test_simplify_context_no_truncation(self):
        prompt = "\n".join(f"line {i}" for i in range(50))
        result = self.orchestrator._simplify_context(prompt, 1.0)
        self.assertEqual(result, prompt)

    def test_simplify_context_truncation(self):
        prompt = "\n".join(f"line {i}" for i in range(100))
        result = self.orchestrator._simplify_context(prompt, 0.5)
        result_lines = result.splitlines()
        # Should have fewer lines
        self.assertLess(len(result_lines), 100)
        # Should contain truncation message
        self.assertIn("[Context truncated", result)
        # First 10 instruction lines should be preserved
        preserved = result_lines[:10]
        for i in range(10):
            self.assertIn(f"line {i}", preserved[i])

    def test_simplify_context_short_prompt(self):
        prompt = "\n".join(f"line {i}" for i in range(5))
        result = self.orchestrator._simplify_context(prompt, 0.3)
        self.assertEqual(result, prompt)

    # ── truncate_file ─────────────────────────────────────────────

    def test_truncate_file_small_file(self):
        file_path = self.project_root / "small.py"
        content = "\n".join(f"# line {i}" for i in range(20))
        file_path.write_text(content)
        result = self.orchestrator.truncate_file(file_path, 0.5)
        self.assertIn("# line 0", result)
        # Small files (≤50 lines) pass through unchanged
        self.assertEqual(result.strip(), content.strip())

    def test_truncate_file_non_code_preserves_lines(self):
        file_path = self.project_root / "large.txt"
        content = "\n".join(f"line {i}" for i in range(200))
        file_path.write_text(content)
        result = self.orchestrator.truncate_file(file_path, 0.3)
        result_lines = result.splitlines()
        # Roughly 60 lines (200 * 0.3)
        self.assertLess(len(result_lines), 120)
        self.assertGreater(len(result_lines), 40)
        self.assertIn("[Truncated", result)

    def test_truncate_file_python_preserves_signatures(self):
        file_path = self.project_root / "large.py"
        lines = []
        # Add imports
        for i in range(5):
            lines.append(f"import module_{i}")
        lines.append("from somewhere import something")
        # Add function signatures with bodies
        for i in range(10):
            lines.append(f"def func_{i}(x):")
            for j in range(15):  # body lines
                lines.append(f"    # body line {j}")
        # Add class
        lines.append("class MyClass:")
        for j in range(15):
            lines.append(f"    def method_{j}(self):")
            for k in range(3):
                lines.append(f"        pass")
        content = "\n".join(lines)
        file_path.write_text(content)

        result = self.orchestrator.truncate_file(file_path, 0.5)
        # Function signatures should be preserved
        self.assertIn("def func_0", result)
        self.assertIn("def func_9", result)
        # Class should be preserved
        self.assertIn("class MyClass", result)
        # Imports should be preserved
        self.assertIn("import module_0", result)
        # Truncation message should be present
        self.assertIn("[Truncated", result)

    def test_truncate_file_missing_file(self):
        result = self.orchestrator.truncate_file(
            self.project_root / "nonexistent.py", 0.5
        )
        self.assertEqual(result, "")

    # ── _get_agent_system_prompt ──────────────────────────────────

    def test_get_agent_system_prompt_template_exists(self):
        template_dir = self.project_root / "docs" / "workflow" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_path = template_dir / "code-system-prompt.md"
        template_path.write_text("You are an expert developer. Use tools.")

        # Re-create orchestrator so it picks up the template
        orch = LLMOrchestrator(project_root=str(self.project_root))
        result = orch._get_agent_system_prompt("code")
        self.assertEqual(result, "You are an expert developer. Use tools.")

    def test_get_agent_system_prompt_fallback(self):
        # No template file exists in temp dir
        result = self.orchestrator._get_agent_system_prompt("code")
        self.assertIn("file_read", result)
        self.assertIn("file_write", result)

    # ── _build_user_prompt ────────────────────────────────────────

    def test_build_user_prompt_placeholder_replacement(self):
        context = {
            "task_spec": "Write a fib function",
            "existing_context": "def fib(n): pass",
        }
        template = (
            "System prompt header\n\n"
            "{INSERT: Full task specification from Mid-Tier Planner}\n\n"
            "Context:\n"
            "{INSERT: Relevant existing files, interfaces, patterns}\n"
        )
        result = self.orchestrator._build_user_prompt(
            "task-1", "L0-Coder", context, template
        )
        self.assertIn("Write a fib function", result)
        self.assertIn("def fib(n): pass", result)
        self.assertIn("## Current Task: task-1", result)

    def test_build_user_prompt_extra_context_keys(self):
        context = {
            "task_spec": "test",
            "extra_field": "extra_value",
        }
        template = "{INSERT: Full task specification from Mid-Tier Planner}"
        result = self.orchestrator._build_user_prompt(
            "task-1", "L0-Coder", context, template
        )
        self.assertIn("**extra_field:** extra_value", result)

    # ── _build_system_prompt ──────────────────────────────────────

    def test_build_system_prompt_extracts_role(self):
        template = (
            "# ROLE: Expert Coder\n\n"
            "You write code.\n\n"
            "## Tools\n\n"
            "file_read, file_write\n"
        )
        result = self.orchestrator._build_system_prompt("L0-Coder", template)
        self.assertIn("# ROLE: Expert Coder", result)
        self.assertNotIn("## Tools", result)
        self.assertNotIn("file_read", result)


if __name__ == "__main__":
    unittest.main()
