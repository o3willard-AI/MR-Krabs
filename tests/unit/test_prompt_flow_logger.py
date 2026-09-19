#!/usr/bin/env python3
"""Unit tests for prompt_flow_logger.py — RAE operator attribution."""

import json
from unittest.mock import patch

from src.core.prompt_flow_logger import PromptFlowLogger


class TestPromptFlowLoggerOperator:
    """Every interaction's meta.json must name the accountable human (RAE)."""

    def _log_once(self, base_dir):
        logger = PromptFlowLogger(
            task_id="task-1",
            enabled=True,
            base_dir=base_dir,
        )
        logger.log(agent="L0-Coder", input_text="prompt", output_text="code")
        return logger

    def test_meta_json_includes_operator(self, tmp_path):
        logger = self._log_once(tmp_path)
        meta_path = tmp_path / "task-1" / "001-L0-Coder-meta.json"
        meta = json.loads(meta_path.read_text())
        assert "operator_id" in meta
        assert "operator_name" in meta

    def test_operator_falls_back_to_os_username(self, tmp_path):
        with patch("getpass.getuser", return_value="sblanken"):
            self._log_once(tmp_path)
        meta_path = tmp_path / "task-1" / "001-L0-Coder-meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["operator_id"] == "sblanken"
        assert meta["operator_name"] == "sblanken"

    def test_disabled_logger_writes_nothing(self, tmp_path):
        logger = PromptFlowLogger(
            task_id="task-1",
            enabled=False,
            base_dir=tmp_path,
        )
        logger.log(agent="L0-Coder", input_text="prompt", output_text="code")
        assert not (tmp_path / "task-1").exists()