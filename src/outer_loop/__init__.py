#!/usr/bin/env python3
"""Outer Loop module for MR-Krabs.

Decomposition → MR-Krabs (inner) → Integration Verification → Learning.

Public API:
    execute_with_outer_loop(task_spec, project_name) -> OuterLoopResult
    OuterLoopOrchestrator — full control over the meta-pipeline
    PatternLibrary — read/write learned decomposition rules
    generate_learning_summary() — human-readable learning state
"""

from src.outer_loop.orchestrator import (
    OuterLoopOrchestrator,
    OuterLoopResult,
    execute_with_outer_loop,
)
from src.outer_loop.pattern_library import (
    Chunk,
    Decomposition,
    DecompositionRule,
    FailureRecord,
    PatternLibrary,
    compute_spec_metrics,
    hash_spec,
)
from src.outer_loop.learner import (
    generate_learning_summary,
    process_new_failures,
)

__all__ = [
    "execute_with_outer_loop",
    "OuterLoopOrchestrator",
    "OuterLoopResult",
    "PatternLibrary",
    "DecompositionRule",
    "FailureRecord",
    "Chunk",
    "Decomposition",
    "compute_spec_metrics",
    "hash_spec",
    "generate_learning_summary",
    "process_new_failures",
]
