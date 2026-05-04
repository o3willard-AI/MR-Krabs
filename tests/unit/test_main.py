#!/usr/bin/env python3
"""Unit tests for main.py - CLI entry point and argument parsing."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli.main import main


class TestMain:
    """Tests for main function."""
    
    def test_main_with_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs', '--help']):
                main()
        
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "usage" in output.lower() or "multi-tier" in output.lower()
    
    def test_main_missing_command(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs']):
                main()
        assert exc_info.value.code == 1
    
    def test_main_with_unknown_command(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['mr-krabs', 'unknown']):
                main()
        assert exc_info.value.code == 2
    
    def test_main_with_explain_no_logs(self, tmp_path, monkeypatch):
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        
        with patch('src.cli.main.PROJECT_ROOT', tmp_path), \
             patch('sys.argv', ['mr-krabs', 'explain', 'task-001']):
            with pytest.raises(SystemExit) as exc_info:
                main()
        
        assert exc_info.value.code == 1
