#!/usr/bin/env python3
"""Unit tests for orchestrator checkpoint/resume."""

import json
import tempfile
import time
from pathlib import Path

import pytest
from src.core.orchestrator import LLMOrchestrator


class TestCheckpoint:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs" / "workflow" / "escalations").mkdir(parents=True)
        (self.root / "docs" / "workflow" / "templates").mkdir(parents=True)
        self.o = LLMOrchestrator(project_root=str(self.root))

    def teardown_method(self):
        self.tmp.cleanup()

    def test_write_and_load_checkpoint(self):
        self.o._write_checkpoint(
            task_id="test-task",
            escalation_path=["L0-Coder"],
            accumulated_files={"src/a.py": 500},
            retries_per_tier={"L0-Coder": 2},
            best_output={"tier": "L0-Coder", "score": 0.8, "output": "..."},
            cost_summary={"total_cost": 0.001},
            attempts_total=2,
            start_time=time.monotonic(),
        )
        ck = self.o._load_checkpoint("test-task")
        assert ck is not None
        assert ck["task_id"] == "test-task"
        assert "L0-Coder" in ck["escalation_path"]
        assert ck["accumulated_files"]["src/a.py"] == 500
        assert ck["retries_per_tier"]["L0-Coder"] == 2

    def test_load_nonexistent_checkpoint(self):
        assert self.o._load_checkpoint("nonexistent") is None

    def test_clear_checkpoint(self):
        self.o._write_checkpoint(
            task_id="clear-me",
            escalation_path=[],
            accumulated_files={},
            retries_per_tier={},
            best_output={},
            cost_summary={},
            attempts_total=0,
            start_time=time.monotonic(),
        )
        assert self.o._load_checkpoint("clear-me") is not None
        self.o._clear_checkpoint("clear-me")
        assert self.o._load_checkpoint("clear-me") is None

    def test_checkpoint_file_is_valid_json(self):
        self.o._write_checkpoint(
            task_id="json-test",
            escalation_path=["L0-Coder", "L1-Coder"],
            accumulated_files={"a.py": 100, "b/c.py": 200},
            retries_per_tier={"L0-Coder": 3, "L1-Coder": 1},
            best_output={"tier": "L1-Coder", "score": 0.85},
            cost_summary={"daily_total": 0.005},
            attempts_total=4,
            start_time=time.monotonic(),
        )
        path = self.o._checkpoint_path("json-test")
        raw = path.read_text()
        parsed = json.loads(raw)
        assert parsed["task_id"] == "json-test"
        assert len(parsed["escalation_path"]) == 2
