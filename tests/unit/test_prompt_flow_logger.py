#!/usr/bin/env python3
"""Unit tests for prompt_flow_logger.py - RAE L0 operator identity."""

import json

from src.core.prompt_flow_logger import PromptFlowLogger


def test_log_writes_meta_with_operator(tmp_path, monkeypatch):
    """The per-interaction meta.json names the accountable operator (RAE L0)."""
    # Deterministic identity; removing the getuser fallback in resolve_operator
    # (or dropping the operator from the logger) makes this test fail.
    monkeypatch.setattr("src.core.config.getpass.getuser", lambda: "test-operator")

    logger = PromptFlowLogger(task_id="t-1", enabled=True, base_dir=tmp_path)
    logger.log(agent="coder", input_text="in", output_text="out")

    meta_path = tmp_path / "t-1" / "001-coder-meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    # Mutation check: if operator_id/operator_name are removed from the meta
    # dict, this assertion fails.
    assert meta["operator_id"] == "test-operator"
    assert meta["operator_name"] == "test-operator"


def test_log_uses_explicit_operator_args(tmp_path):
    """Explicitly passed operator_id/operator_name win over the resolver."""
    logger = PromptFlowLogger(
        task_id="t-2",
        enabled=True,
        base_dir=tmp_path,
        operator_id="mr-krabs",
        operator_name="MR Krabs",
    )
    logger.log(agent="coder", input_text="in", output_text="out")

    meta_path = tmp_path / "t-2" / "001-coder-meta.json"
    meta = json.loads(meta_path.read_text())
    assert meta["operator_id"] == "mr-krabs"
    assert meta["operator_name"] == "MR Krabs"


def test_log_is_noop_when_disabled(tmp_path):
    """Disabled logger writes nothing at all."""
    logger = PromptFlowLogger(task_id="t-3", enabled=False, base_dir=tmp_path)
    logger.log(agent="coder", input_text="in", output_text="out")
    assert not (tmp_path / "t-3").exists()
