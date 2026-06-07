#!/usr/bin/env python3
"""Prompt Flow Debug Logger — dumps inputs/outputs at every agent boundary.

When MRKRABS_PROMPT_FLOW_DEBUG=1 or prompt_flow_debug: true in config.yaml,
this logger writes structured dumps to ~/.mrkrabs/debug/<task_id>/ for every
agent-to-agent interaction in the pipeline.

Each interaction produces two files:
  - <seq>-<agent>-input.txt   → exactly what the agent received
  - <seq>-<agent>-output.txt  → exactly what the agent produced

This burns disk (and indirectly tokens since these are verbatim copies) but
is invaluable for debugging prompt transformations and model behavior.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PromptFlowLogger:
    """Writes prompt flow debug dumps. No-op when disabled."""

    def __init__(
        self,
        task_id: str,
        enabled: bool = False,
        base_dir: str | Path = "~/.mrkrabs/debug",
    ):
        self.enabled = enabled
        self.task_id = task_id
        self.base_dir = Path(base_dir).expanduser()
        self.seq = 0

    def log(self, agent: str, input_text: str, output_text: str) -> None:
        """Log an agent interaction. No-op when disabled."""
        if not self.enabled:
            return

        self.seq += 1
        task_dir = self.base_dir / self.task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).isoformat()
        meta = {
            "seq": self.seq,
            "agent": agent,
            "task_id": self.task_id,
            "timestamp": ts,
            "input_chars": len(input_text),
            "output_chars": len(output_text),
        }

        in_path = task_dir / f"{self.seq:03d}-{agent}-input.txt"
        out_path = task_dir / f"{self.seq:03d}-{agent}-output.txt"
        meta_path = task_dir / f"{self.seq:03d}-{agent}-meta.json"

        in_path.write_text(input_text)
        out_path.write_text(output_text)
        meta_path.write_text(json.dumps(meta, indent=2))

    def log_input(self, agent: str, input_text: str) -> None:
        """Log only input (for streaming agents where output is separate)."""
        if not self.enabled:
            return

        self.seq += 1
        task_dir = self.base_dir / self.task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        in_path = task_dir / f"{self.seq:03d}-{agent}-input.txt"
        in_path.write_text(input_text)
