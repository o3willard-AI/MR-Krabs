#!/usr/bin/env python3
"""Pattern library for outer loop decomposition — learned rules + semantic fallback.

Rules engine (primary): structured decomposition rules built from failure data.
Semantic matcher (fallback): embed spec → find nearest successful decomposition.

Over 6–12 projects, the rule library converges so the decomposer gets chunking
right on the first attempt.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data directory ──────────────────────────────────────────────────────────

def _data_dir() -> Path:
    env = os.environ.get("MRKRABS_DATA_DIR", "")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data"


PATTERN_LIBRARY_PATH = _data_dir() / "pattern_library.json"
FAILURE_LOG_PATH = _data_dir() / "failure_log.jsonl"
EMBEDDINGS_DIR = _data_dir() / "embeddings"


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class Chunk:
    """A single decomposed chunk of work."""
    name: str
    files: list[str]
    description: str
    dependencies: list[str] = field(default_factory=list)  # other chunk names
    interface_contract: str = ""  # what this chunk exports


@dataclass
class Decomposition:
    """The output of the decomposer — a chunk plan for one project."""
    project_id: str
    chunks: list[Chunk]
    reasoning: str  # why the decomposer chose this split
    matched_rule: Optional[str] = None  # which rule matched, if any
    semantic_match_project: Optional[str] = None  # fallback match


@dataclass
class DecompositionRule:
    """A learned decomposition rule."""
    id: str
    condition: str  # when to apply (e.g. "spec has > 20 files")
    action: str     # how to chunk (e.g. "group by directory, max 15 per chunk")
    examples: list[str] = field(default_factory=list)  # project IDs
    success_count: int = 0
    failure_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    @property
    def confidence(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total


@dataclass
class FailureRecord:
    """A verifier rejection with root cause analysis."""
    project_id: str
    spec_hash: str
    chunks: list[str]  # chunk names
    failure_type: str   # seam_mismatch | missing_dep | over_chunk | under_chunk
    detail: str         # human-readable description
    affected_files: list[str] = field(default_factory=list)
    resolution: str = ""        # what fixed it
    generated_rule: str = ""    # rule the learner produced
    timestamp: str = ""


@dataclass
class SemanticMatch:
    """Result of semantic similarity matching."""
    project_id: str
    score: float        # cosine similarity
    decomposition: dict  # the matched decomposition


# ── Pattern Library Store ───────────────────────────────────────────────────


class PatternLibrary:
    """Read/write structured decomposition rules + semantic match cache."""

    def __init__(self, path: Path = PATTERN_LIBRARY_PATH):
        self.path = path
        self.rules: dict[str, DecompositionRule] = {}
        self.decompositions: dict[str, Decomposition] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        for rule_data in data.get("rules", []):
            rule = DecompositionRule(**rule_data)
            self.rules[rule.id] = rule

        for dec_data in data.get("decompositions", []):
            # Convert chunks back to Chunk objects
            chunks = [Chunk(**c) for c in dec_data.pop("chunks", [])]
            dec = Decomposition(chunks=chunks, **dec_data)
            self.decompositions[dec.project_id] = dec

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "rules": [
                {
                    "id": r.id,
                    "condition": r.condition,
                    "action": r.action,
                    "examples": r.examples,
                    "success_count": r.success_count,
                    "failure_count": r.failure_count,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in self.rules.values()
            ],
            "decompositions": [
                {
                    "project_id": d.project_id,
                    "chunks": [
                        {
                            "name": c.name,
                            "files": c.files,
                            "description": c.description,
                            "dependencies": c.dependencies,
                            "interface_contract": c.interface_contract,
                        }
                        for c in d.chunks
                    ],
                    "reasoning": d.reasoning,
                    "matched_rule": d.matched_rule,
                    "semantic_match_project": d.semantic_match_project,
                }
                for d in self.decompositions.values()
            ],
        }
        self.path.write_text(json.dumps(data, indent=2))

    def add_rule(self, rule: DecompositionRule) -> None:
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        if not rule.created_at:
            rule.created_at = now
        rule.updated_at = now
        self.rules[rule.id] = rule
        self.save()

    def record_decomposition(self, dec: Decomposition) -> None:
        self.decompositions[dec.project_id] = dec
        self.save()

    def get_matching_rules(self, spec_metrics: dict) -> list[DecompositionRule]:
        """Find rules whose conditions match the spec metrics.

        spec_metrics includes: file_count, total_lines, has_tests, has_docs,
        directory_count, max_depth, etc.
        """
        matches = []
        for rule in self.rules.values():
            if _evaluate_condition(rule.condition, spec_metrics):
                matches.append(rule)
        # Sort by confidence descending
        matches.sort(key=lambda r: r.confidence, reverse=True)
        return matches

    def get_latest_decompositions(self, n: int = 10) -> list[Decomposition]:
        """Return n most recent successful decompositions for semantic fallback."""
        return list(self.decompositions.values())[-n:]

    def rule_count(self) -> int:
        return len(self.rules)

    def decomposition_count(self) -> int:
        return len(self.decompositions)


def _evaluate_condition(condition: str, metrics: dict) -> bool:
    """Simple rule condition evaluator.

    Supports: file_count > N, file_count < N, total_lines > N,
    has_tests == true, directory_count > N, etc.

    For complex conditions, the LLM decomposer handles evaluation directly.
    This is a fast-path for simple numeric rules.
    """
    if not condition:
        return False

    for op in [">=", "<=", ">", "<", "==", "!="]:
        parts = condition.split(op)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        value = parts[1].strip()
        if key not in metrics:
            continue

        try:
            metric_val_raw: int | bool = metrics[key]
            target_val: int | bool

            # Parse target value
            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                target_val = int(value)
            elif value.lower() in ("true", "false"):
                target_val = value.lower() == "true"
            else:
                return False

            # Normalize both sides to the same type
            if isinstance(target_val, bool):
                metric_val: int | bool = bool(metric_val_raw)
            else:
                metric_val = int(metric_val_raw)

            if op == ">":
                return metric_val > target_val
            elif op == "<":
                return metric_val < target_val
            elif op == ">=":
                return metric_val >= target_val
            elif op == "<=":
                return metric_val <= target_val
            elif op == "==":
                return metric_val == target_val
            elif op == "!=":
                return metric_val != target_val
        except (ValueError, TypeError):
            pass

    return False


# ── Failure Log ─────────────────────────────────────────────────────────────


def log_failure(record: FailureRecord) -> None:
    """Append a failure record to the failure log."""
    from datetime import UTC, datetime

    FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not record.timestamp:
        record.timestamp = datetime.now(UTC).isoformat()

    entry = {
        "project_id": record.project_id,
        "spec_hash": record.spec_hash,
        "chunks": record.chunks,
        "failure_type": record.failure_type,
        "detail": record.detail,
        "affected_files": record.affected_files,
        "resolution": record.resolution,
        "generated_rule": record.generated_rule,
        "timestamp": record.timestamp,
    }
    with open(FAILURE_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_failure_log(limit: int = 50) -> list[dict]:
    """Read recent failure records."""
    if not FAILURE_LOG_PATH.exists():
        return []
    records = []
    with open(FAILURE_LOG_PATH, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records[-limit:]


# ── Spec Hashing ────────────────────────────────────────────────────────────


def hash_spec(spec_text: str) -> str:
    """Deterministic hash of a spec for deduplication."""
    return hashlib.sha256(spec_text.encode()).hexdigest()[:16]


# ── Spec Metrics ────────────────────────────────────────────────────────────


def compute_spec_metrics(spec_text: str) -> dict:
    """Compute lightweight metrics about a spec for rule matching."""
    lines = spec_text.split("\n")
    file_count = 0

    # Count file references
    import re
    code_ext = r"\.(?:py|md|yaml|yml|toml|json|cfg|ini|sh|sql|html|css|js|ts|rs|go|java|c|cpp|h|hpp)"
    file_pattern = re.compile(r"`?([a-zA-Z0-9_/.~@-]+" + code_ext + r")`?")
    seen = set()
    for match in file_pattern.finditer(spec_text):
        path = match.group(1).strip()
        if path not in seen and "/" in path:
            seen.add(path)
            file_count += 1

    # Count directories
    directories = set()
    for fp in seen:
        parts = fp.split("/")
        for i in range(1, len(parts)):
            directories.add("/".join(parts[:i]))

    # Detect test files
    has_tests = any("test" in fp.lower() for fp in seen)

    # Detect doc files
    has_docs = any(fp.endswith(".md") or fp.endswith(".rst") for fp in seen)

    return {
        "file_count": file_count,
        "total_lines": len(lines),
        "has_tests": has_tests,
        "has_docs": has_docs,
        "directory_count": len(directories),
        "max_depth": max((fp.count("/") for fp in seen), default=0),
    }
