#!/usr/bin/env python3
"""Unit tests for FileTools class."""

import os
import sys
import pytest
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.orchestrator import FileTools


class TestFileTools:
    """Tests for FileTools class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def file_tools(self, temp_dir):
        """Create FileTools instance with temp directory."""
        return FileTools(temp_dir)
    
    def test_file_write_creates_file(self, file_tools, temp_dir):
        """Test file_write creates file with correct content."""
        result = file_tools.file_write("test.txt", "hello world")
        
        assert result["success"] is True
        assert result["bytes"] == 11
        assert (temp_dir / "test.txt").exists()
        assert (temp_dir / "test.txt").read_text() == "hello world"
    
    def test_file_write_creates_directories(self, file_tools, temp_dir):
        """Test file_write creates parent directories."""
        result = file_tools.file_write("sub/dir/test.txt", "content")
        
        assert result["success"] is True
        assert (temp_dir / "sub" / "dir" / "test.txt").exists()
    
    def test_file_write_absolute_path(self, file_tools, temp_dir):
        """Test file_write with absolute path."""
        abs_path = temp_dir / "abs_test.txt"
        result = file_tools.file_write(str(abs_path), "abs content")
        
        assert result["success"] is True
        assert abs_path.exists()
    
    def test_file_read_returns_content(self, file_tools, temp_dir):
        """Test file_read returns file content."""
        (temp_dir / "read_test.txt").write_text("read me")
        
        result = file_tools.file_read("read_test.txt")
        
        assert result["success"] is True
        assert result["content"] == "read me"
        assert result["lines"] == 1
    
    def test_file_read_not_found(self, file_tools, temp_dir):
        """Test file_read with non-existent file."""
        result = file_tools.file_read("nonexistent.txt")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    def test_file_write_empty_content(self, file_tools, temp_dir):
        """Test file_write with empty content."""
        result = file_tools.file_write("empty.txt", "")
        
        assert result["success"] is True
        assert result["bytes"] == 0
        assert (temp_dir / "empty.txt").read_text() == ""
    
    def test_file_read_multiline(self, file_tools, temp_dir):
        """Test file_read counts lines correctly."""
        content = "line1\nline2\nline3\n"
        (temp_dir / "multiline.txt").write_text(content)
        
        result = file_tools.file_read("multiline.txt")
        
        assert result["success"] is True
        assert result["lines"] == 3
