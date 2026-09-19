#!/usr/bin/env python3
"""Unit tests for human_gate.py — RAE operator attribution on confirmation."""

import json
from unittest.mock import patch

import pytest

from src.core import human_gate
from src.core.human_gate import confirm_task, deny_task, write_pending_file


@pytest.fixture
def pending_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(human_gate, "_pending_dir", lambda: tmp_path)
    return tmp_path


class TestWritePendingFile:
    def test_includes_operator(self, pending_dir):
        write_pending_file("task-1", {"tier": "L2"})
        data = json.loads((pending_dir / "task-1.json").read_text())
        assert data["operator_id"] != ""
        assert data["operator_name"] != ""

    def test_operator_falls_back_to_os_username(self, pending_dir):
        with patch("getpass.getuser", return_value="sblanken"):
            write_pending_file("task-1", {"tier": "L2"})
        data = json.loads((pending_dir / "task-1.json").read_text())
        assert data["operator_id"] == "sblanken"
        assert data["operator_name"] == "sblanken"


class TestConfirmDenyOperator:
    def test_confirm_records_who_confirmed(self, pending_dir):
        with patch("getpass.getuser", return_value="sblanken"):
            write_pending_file("task-1", {"tier": "L2"})
            confirm_task("task-1")
        data = json.loads((pending_dir / "task-1.json").read_text())
        assert data["confirmed"] is True
        assert "confirmed_by" in data
        assert data["confirmed_by"]["operator_id"] == "sblanken"

    def test_deny_records_who_denied(self, pending_dir):
        with patch("getpass.getuser", return_value="sblanken"):
            write_pending_file("task-1", {"tier": "L2"})
            deny_task("task-1", reason="Reviewed manually")
        data = json.loads((pending_dir / "task-1.json").read_text())
        assert data["confirmed"] is False
        assert "denied_by" in data
        assert data["denied_by"]["operator_id"] == "sblanken"

    def test_confirm_noop_when_no_pending_file(self, pending_dir):
        confirm_task("nonexistent")
        assert not (pending_dir / "nonexistent.json").exists()