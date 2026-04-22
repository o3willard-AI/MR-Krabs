#!/usr/bin/env python3
"""Unit tests for ToolExecutor class."""
import sys, pytest, tempfile
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.core.orchestrator import FileTools, ToolExecutor

class TestToolExecutor:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def executor(self, temp_dir):
        return ToolExecutor(FileTools(temp_dir))
    
    def test_custom_write(self, executor, temp_dir):
        r = executor.parse_and_execute_tools('file_write("t.txt", """c""")')
        assert r["tools_executed"] == 1
        assert (temp_dir / "t.txt").exists()
    
    def test_custom_read(self, executor, temp_dir):
        (temp_dir / "r.txt").write_text("data")
        r = executor.parse_and_execute_tools('file_read("r.txt")')
        assert r["tools_executed"] == 1
        assert r["tool_results"][0]["content"] == "data"
    
    def test_claude_write(self, executor, temp_dir):
        r = executor.parse_and_execute_tools('{"name":"write_file","parameters":{"path":"c.txt","content":"d"}}')
        assert r["tools_executed"] >= 1
        assert (temp_dir / "c.txt").exists()
    
    def test_claude_read(self, executor, temp_dir):
        (temp_dir / "cr.txt").write_text("cd")
        r = executor.parse_and_execute_tools('{"name":"read_file","parameters":{"path":"cr.txt"}}')
        assert r["tools_executed"] >= 1
    
    def test_multiple_tools(self, executor, temp_dir):
        r = executor.parse_and_execute_tools('file_write("a.txt", """1""")\\nfile_write("b.txt", """2""")')
        assert r["tools_executed"] == 2
        assert r["all_succeeded"] is True
    
    def test_empty_response(self, executor, temp_dir):
        r = executor.parse_and_execute_tools('')
        assert r["tools_executed"] == 0
        assert r["all_succeeded"] is True
