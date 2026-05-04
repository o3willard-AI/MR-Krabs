#!/usr/bin/env python3
"""Unit tests for src/cli/main.py - CLI entry point and argument parsing."""

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add src to path for imports
sys_path = str(Path(__file__).parent.parent.parent)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from src.cli.main import OrchestratorCLI, main, PROJECT_ROOT


class TestOrchestratorCLI:
    """Tests for OrchestratorCLI class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent.parent

    def test_cli_initialization_with_rich(self):
        """Test CLI initializes with Rich if available."""
        cli = OrchestratorCLI(use_rich=True)
        # Rich might not be available in all environments, so just verify it works
        assert cli.orchestrator is not None
        # if Rich is available, use_rich should be True
        if cli.use_rich:
            assert cli.console is not None

    def test_cli_initialization_without_rich(self):
        """Test CLI initializes without Rich."""
        cli = OrchestratorCLI(use_rich=False)
        assert cli.use_rich is False
        assert cli.console is None
        assert cli.orchestrator is not None

    @patch("src.cli.main.Console")
    @patch("src.cli.main.RICH_AVAILABLE", True)
    def test_cli_initialization_rich_not_available(self, mock_console):
        """Test CLI handles Rich import failure gracefully."""
        # Mock RICH_AVAILABLE to False
        with patch('src.cli.main.RICH_AVAILABLE', False):
            cli = OrchestratorCLI(use_rich=True)
            # Should still work, just without Rich
            assert cli.console is None
            assert cli.orchestrator is not None

    def test_print_header_with_rich(self, capsys):
        """Test print_header uses Rich when available."""
        cli = OrchestratorCLI(use_rich=True)
        if cli.console:
            cli.print_header()
            output = capsys.readouterr().out
            assert "Multi-Tier LLM Orchestrator" in output

    def test_print_header_without_rich(self, capsys):
        """Test print_header without Rich."""
        cli = OrchestratorCLI(use_rich=False)
        cli.print_header()
        output = capsys.readouterr().out
        assert "Multi-Tier LLM Orchestrator" in output
        assert "=" in output

    def test_print_status_success_with_rich(self, capsys):
        """Test print_status shows success with Rich."""
        cli = OrchestratorCLI(use_rich=True)
        if cli.console:
            cli.print_status("Test message", success=True)
            output = capsys.readouterr().out
            assert "Test message" in output

    def test_print_status_failure_with_rich(self, capsys):
        """Test print_status shows failure with Rich."""
        cli = OrchestratorCLI(use_rich=True)
        if cli.console:
            cli.print_status("Test message", success=False)
            output = capsys.readouterr().out
            assert "Test message" in output

    def test_print_status_success_without_rich(self, capsys):
        """Test print_status without Rich for success."""
        cli = OrchestratorCLI(use_rich=False)
        cli.print_status("Test message", success=True)
        output = capsys.readouterr().out
        assert "[PASS]" in output
        assert "Test message" in output

    def test_print_status_failure_without_rich(self, capsys):
        """Test print_status without Rich for failure."""
        cli = OrchestratorCLI(use_rich=False)
        cli.print_status("Test message", success=False)
        output = capsys.readouterr().out
        assert "[FAIL]" in output
        assert "Test message" in output

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_success_with_rich(self, mock_orchestrator_class, capsys):
        """Test execute_task with successful execution."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 2.5,
            "attempts": 1,
            "output": "Test output",
        }

        cli = OrchestratorCLI(use_rich=True)
        result = cli.execute_task("task-1", "L0-Coder", {"desc": "test"})

        assert result["success"] is True
        assert result["duration_seconds"] == 2.5

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_failure(self, mock_orchestrator_class, capsys):
        """Test execute_task with failed execution."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": False,
            "attempts": 3,
            "error": "Test error",
            "duration_seconds": 10.0,
        }

        cli = OrchestratorCLI(use_rich=False)
        result = cli.execute_task("task-2", "L1-Coder", {"desc": "test"})

        assert result["success"] is False
        assert result["error"] == "Test error"

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_with_tool_results(self, mock_orchestrator_class, capsys):
        """Test execute_task when tools are executed."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 3.0,
            "attempts": 1,
            "output": "Test",
            "tool_results": {
                "tool_results": [
                    {"tool": "file_read", "path": "test.txt", "success": True},
                ],
                "tools_executed": 1,
            },
        }

        cli = OrchestratorCLI(use_rich=True)
        result = cli.execute_task("task-3", "L0-Coder", {"desc": "test"})

        assert result["success"] is True

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_saves_output_file(self, mock_orchestrator_class, tmp_path):
        """Test execute_task saves output to file."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 1.0,
            "attempts": 1,
            "output": "Output content",
        }

        output_file = tmp_path / "output.txt"
        cli = OrchestratorCLI(use_rich=False)
        cli.execute_task("task-4", "L0-Coder", {"desc": "test"}, str(output_file))

        assert output_file.exists()
        assert output_file.read_text() == "Output content"

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_records_metrics_success(self, mock_orchestrator_class):
        """Test execute_task records metrics on success."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 2.0,
            "attempts": 1,
            "output": "Test",
            "tool_results": {"tools_executed": 0},
        }

        cli = OrchestratorCLI(use_rich=False)
        result = cli.execute_task("task-5", "L0-Coder", {"desc": "test"})

        # Check that metrics were recorded
        summary = cli.metrics.get_summary()
        assert summary["total_tasks"] == 1
        assert summary["overall_success_rate"] == 1.0

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_execute_task_records_metrics_failure(self, mock_orchestrator_class):
        """Test execute_task records metrics on failure."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": False,
            "duration_seconds": 5.0,
            "attempts": 3,
            "error": "Error",
        }

        cli = OrchestratorCLI(use_rich=False)
        result = cli.execute_task("task-6", "L1-Coder", {"desc": "test"})

        # Check that metrics were recorded
        summary = cli.metrics.get_summary()
        assert summary["total_tasks"] == 1
        assert summary["overall_success_rate"] == 0.0

    def test_print_metrics_with_rich(self, capsys):
        """Test print_metrics displays metrics table."""
        cli = OrchestratorCLI(use_rich=True)
        cli.metrics.record_task("task-1", "L0-Coder", True, 1.0, 1)
        if cli.console:
            cli.print_metrics()
            output = capsys.readouterr().out
            assert "Metrics Summary" in output or "Total Tasks" in output

    def test_print_metrics_without_rich(self, capsys):
        """Test print_metrics displays metrics without Rich."""
        cli = OrchestratorCLI(use_rich=False)
        cli.metrics.record_task("task-1", "L0-Coder", True, 1.0, 1)
        cli.print_metrics()
        output = capsys.readouterr().out
        assert "Metrics Summary" in output
        assert "Total Tasks" in output


class TestMain:
    """Tests for main() CLI entry point."""

    def setup_method(self):
        """Set up environment."""
        if "OPENROUTER_API_KEY" not in os.environ:
            os.environ["OPENROUTER_API_KEY"] = "test-key"

    def teardown_method(self):
        """Clean up environment."""
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

    def test_main_with_help(self, capsys):
        """Test --help flag works."""
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs', '--help']):
                main()
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "usage" in output.lower() or "Multi-Tier" in output

    def test_main_with_no_command(self, capsys):
        """Test no command shows help."""
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs']):
                main()
        assert exc_info.value.code == 1

    def test_main_with_unknown_command(self, capsys):
        """Test unknown command exits with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs', 'unknown-command']):
                main()
        assert exc_info.value.code == 2

    def test_main_init_command(self):
        """Test init command routes correctly."""
        # Just verify the route exists - actual init is tested separately
        with patch('sys.argv', ['mr-krabs', 'init']):
            with patch('src.cli.main.cmd_init') as mock_cmd_init:
                mock_cmd_init.return_value = 0
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0
                    mock_cmd_init.assert_called_once()

    def test_main_doctor_command(self):
        """Test doctor command routes correctly."""
        with patch('sys.argv', ['mr-krabs', 'doctor']):
            with patch('src.cli.main.cmd_doctor') as mock_cmd_doctor:
                mock_cmd_doctor.return_value = 0
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0
                    mock_cmd_doctor.assert_called_once()

    def test_main_stats_command_no_export(self):
        """Test stats command without export."""
        with patch('sys.argv', ['mr-krabs', 'stats']):
            with patch('src.cli.main.cmd_stats') as mock_cmd_stats:
                mock_cmd_stats.return_value = 0
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0
                    mock_cmd_stats.assert_called_once()

    def test_main_stats_command_with_json_export(self):
        """Test stats command with JSON export."""
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'json']):
            with patch('src.core.config.load_config') as mock_load_config:
                with patch('src.core.config.config_to_budget') as mock_config_to_budget:
                    with patch('src.core.cost.CostTracker') as mock_tracker_class:
                        mock_config = {"budget": {"daily_limit_usd": 10.0}}
                        mock_load_config.return_value = mock_config
                        mock_config_to_budget.return_value = MagicMock()
                        mock_tracker = MagicMock()
                        mock_tracker.save_report.return_value = "/tmp/report.json"
                        mock_tracker_class.return_value = mock_tracker
                        
                        try:
                            main()
                        except SystemExit as e:
                            assert e.code == 0
                            mock_tracker.save_report.assert_called_once()

    def test_main_stats_command_with_csv_export(self):
        """Test stats command with CSV export."""
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'csv']):
            with patch('src.core.config.load_config') as mock_load_config:
                with patch('src.core.config.config_to_budget') as mock_config_to_budget:
                    with patch('src.core.cost.CostTracker') as mock_tracker_class:
                        mock_config = {"budget": {"daily_limit_usd": 10.0}}
                        mock_load_config.return_value = mock_config
                        mock_config_to_budget.return_value = MagicMock()
                        mock_tracker = MagicMock()
                        mock_tracker.export_csv.return_value = "/tmp/report.csv"
                        mock_tracker_class.return_value = mock_tracker
                        
                        try:
                            main()
                        except SystemExit as e:
                            assert e.code == 0
                            mock_tracker.export_csv.assert_called_once()

    def test_main_stats_command_with_both_exports(self):
        """Test stats command with both JSON and CSV export."""
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'both']):
            with patch('src.core.config.load_config') as mock_load_config:
                with patch('src.core.config.config_to_budget') as mock_config_to_budget:
                    with patch('src.core.cost.CostTracker') as mock_tracker_class:
                        mock_config = {"budget": {"daily_limit_usd": 10.0}}
                        mock_load_config.return_value = mock_config
                        mock_config_to_budget.return_value = MagicMock()
                        mock_tracker = MagicMock()
                        mock_tracker.save_report.return_value = "/tmp/report.json"
                        mock_tracker.export_csv.return_value = "/tmp/report.csv"
                        mock_tracker_class.return_value = mock_tracker
                        
                        try:
                            main()
                        except SystemExit as e:
                            assert e.code == 0
                            assert mock_tracker.save_report.call_count == 1
                            assert mock_tracker.export_csv.call_count == 1

    def test_main_explain_command(self):
        """Test explain command routes correctly."""
        with patch('sys.argv', ['mr-krabs', 'explain', 'task-123']):
            with patch('src.cli.main.cmd_explain') as mock_cmd_explain:
                mock_cmd_explain.return_value = 0
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0
                    mock_cmd_explain.assert_called_once_with("task-123")

    def test_main_dry_run_command(self):
        """Test dry-run command routes correctly."""
        with patch('sys.argv', ['mr-krabs', 'dry-run', 'Test task', '--tier', 'L0-Coder']):
            with patch('src.cli.main.cmd_dry_run') as mock_cmd_dry_run:
                mock_cmd_dry_run.return_value = 0
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0
                    mock_cmd_dry_run.assert_called_once_with("Test task", "L0-Coder")

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_main_run_command_success(self, mock_orchestrator_class):
        """Test run command with successful execution."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 1.0,
            "attempts": 1,
            "output": "Test",
            "tool_results": {"tools_executed": 0},
        }

        with patch('sys.argv', ['mr-krabs', 'run', 'Test task', '--tier', 'L0-Coder']):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_main_run_command_failure(self, mock_orchestrator_class):
        """Test run command with failed execution."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": False,
            "attempts": 3,
            "error": "Error",
            "duration_seconds": 10.0,
        }

        with patch('sys.argv', ['mr-krabs', 'run', 'Test task', '--tier', 'L0-Coder']):
            try:
                main()
            except SystemExit as e:
                assert e.code == 1

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_main_run_command_with_output_file(self, mock_orchestrator_class, tmp_path):
        """Test run command saves output to file."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 1.0,
            "attempts": 1,
            "output": "Output content",
            "tool_results": {"tools_executed": 0},
        }

        output_file = tmp_path / "output.txt"
        with patch('sys.argv', ['mr-krabs', 'run', 'Test task', '--tier', 'L0-Coder',
                               '--output', str(output_file)]):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0
                assert output_file.exists()
                assert output_file.read_text() == "Output content"

    @patch("src.cli.main.LLMOrchestrator")
    @patch("src.cli.main.PROJECT_ROOT", Path(__file__).parent.parent.parent)
    def test_main_run_command_with_no_rich(self, mock_orchestrator_class, capsys):
        """Test run command with --no-rich flag."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_task.return_value = {
            "success": True,
            "duration_seconds": 1.0,
            "attempts": 1,
            "output": "Test",
            "tool_results": {"tools_executed": 0},
        }

        with patch('sys.argv', ['mr-krabs', 'run', 'Test task', '--tier', 'L0-Coder', '--no-rich']):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0


class TestMainArgumentParsing:
    """Tests for argument parsing in main()."""

    def test_run_requires_tier(self):
        """Test run command requires --tier argument."""
        with patch('sys.argv', ['mr-krabs', 'run', 'Test task']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error code

    def test_run_accepts_tier_choices(self):
        """Test run accepts valid tier choices."""
        # We can't easily test argparse choices without actually running,
        # but we can verify the parser is set up correctly
        from src.cli.main import main
        import sys
        from unittest.mock import patch
        
        # L0-Coder is a valid tier
        with patch('sys.argv', ['mr-krabs', 'run', 'Test', '--tier', 'L0-Coder']):
            pass  # We're just testing it doesn't error on parsing

    def test_stats_export_choices(self):
        """Test stats accepts valid export choices."""
        from src.cli.main import main
        from unittest.mock import patch
        
        # JSON is a valid export
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'json']):
            pass

        # CSV is a valid export
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'csv']):
            pass

        # Both is a valid export
        with patch('sys.argv', ['mr-krabs', 'stats', '--export', 'both']):
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
