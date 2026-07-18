#!/usr/bin/env python3
"""Outer Loop Orchestrator — the meta-layer above MR-Krabs.

Receives a task of arbitrary size, decomposes it into kiosk-sized chunks,
feeds each chunk through the existing MR-Krabs pipeline, verifies
integration seams, and learns from failures.

Flow:
    1. Analyze spec → compute metrics → consult pattern library
    2. Decompose into right-sized chunks (Decomposer)
    3. Feed each chunk through MR-Krabs (inner pipeline, unchanged)
    4. Verify integration seams (Verifier)
    5. If accept → done (+ record successful decomposition)
    6. If reject → Learner analyzes failure → re-chunk → goto 3
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.outer_loop.pattern_library import (
    Chunk,
    Decomposition,
    DecompositionRule,
    FailureRecord,
    PatternLibrary,
    compute_spec_metrics,
    hash_spec,
    log_failure,
)
from src.outer_loop.verifier import (
    IntegrationResult,
    verify_integration,
)


# ── Result dataclass ────────────────────────────────────────────────────────


@dataclass
class OuterLoopResult:
    """Result from an outer loop execution."""
    project_id: str
    success: bool
    chunks_run: int
    chunks_succeeded: int
    re_chunk_attempts: int
    total_duration_seconds: float
    output_dir: Optional[str] = None
    decomposition: Optional[dict] = None
    integration_result: Optional[IntegrationResult] = None
    learning_events: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def summary(self) -> str:
        return (
            f"Outer Loop: {'✓' if self.success else '✗'} "
            f"({self.chunks_succeeded}/{self.chunks_run} chunks, "
            f"{self.re_chunk_attempts} re-chunks, "
            f"{self.total_duration_seconds:.0f}s)"
        )


# ── Orchestrator ────────────────────────────────────────────────────────────


class OuterLoopOrchestrator:
    """Meta-orchestrator: decomposer → MR-Krabs → verifier → learner."""

    MAX_RECHUNK_ATTEMPTS = 3  # maximum number of RE-chunks (not including initial attempt)

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        library_path: Optional[Path] = None,
    ):
        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="mrkrabs-outer-"))
        self.library = PatternLibrary(library_path) if library_path else PatternLibrary()
        self.project_dir: Optional[Path] = None

    @staticmethod
    def _chunks_identical(a: Decomposition, b: Decomposition) -> bool:
        """Check if two decompositions are functionally identical."""
        a_sig = sorted((c.name, tuple(sorted(c.files))) for c in a.chunks)
        b_sig = sorted((c.name, tuple(sorted(c.files))) for c in b.chunks)
        return a_sig == b_sig

    def execute(self, task_spec: str, project_name: str = "unnamed") -> OuterLoopResult:
        """Execute a task through the outer loop.

        Args:
            task_spec: The full task specification (arbitrary size)
            project_name: Human-readable project name

        Returns:
            OuterLoopResult with full execution details
        """
        start_time = time.monotonic()
        project_id = f"{project_name}-{hash_spec(task_spec)}"
        learning_events: list[str] = []

        print(f"\n{'='*60}")
        print(f"[OUTER LOOP] Starting: {project_name}")
        print(f"[OUTER LOOP] Pattern library: {self.library.rule_count()} rules, "
              f"{self.library.decomposition_count()} decompositions")
        print(f"{'='*60}\n")

        # Step 1: Analyze the spec
        metrics = compute_spec_metrics(task_spec)
        print(f"[OUTER LOOP] Spec metrics: {json.dumps(metrics)}")

        # Step 2: Decompose
        decomposition = self._decompose(task_spec, metrics, project_id)
        print(f"[OUTER LOOP] Decomposed into {len(decomposition.chunks)} chunks:")
        for chunk in decomposition.chunks:
            print(f"  - {chunk.name}: {len(chunk.files)} files")

        # If single chunk and it's kiosk-sized, fast-path through
        if len(decomposition.chunks) == 1:
            print("[OUTER LOOP] Single chunk — fast-path (no outer verification needed)")
            result = self._run_inner_pipeline(task_spec, decomposition.chunks[0], project_id)
            duration = time.monotonic() - start_time
            return OuterLoopResult(
                project_id=project_id,
                success=result.get("success", False),
                chunks_run=1,
                chunks_succeeded=1 if result.get("success") else 0,
                re_chunk_attempts=0,
                total_duration_seconds=duration,
                output_dir=str(self.project_dir) if self.project_dir else None,
                decomposition={
                    "chunks": [
                        {"name": c.name, "files": c.files, "description": c.description}
                        for c in decomposition.chunks
                    ],
                    "reasoning": decomposition.reasoning,
                },
            )

        # Step 3-6: Multi-chunk execution with verification
        re_chunk_attempts = 0
        project_dir = self.work_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir = project_dir
        chunks_succeeded = 0
        integration: Optional[IntegrationResult] = None
        previous_decomposition: Optional[Decomposition] = None  # dedup tracker

        while re_chunk_attempts < self.MAX_RECHUNK_ATTEMPTS:
            # Step 3: Run each chunk through MR-Krabs
            chunk_results = []
            for chunk in decomposition.chunks:
                print(f"\n[OUTER LOOP] Running chunk: {chunk.name}")
                chunk_spec = self._build_chunk_spec(task_spec, chunk, decomposition)
                result = self._run_inner_pipeline(chunk_spec, chunk, project_id)
                chunk_results.append((chunk, result))

            chunks_succeeded = sum(1 for _, r in chunk_results if r.get("success"))

            # Step 4: Verify integration
            chunk_dicts = [
                {
                    "name": c.name,
                    "files": c.files,
                    "interface_contract": c.interface_contract,
                    "dependencies": c.dependencies,
                }
                for c in decomposition.chunks
            ]
            integration = verify_integration(project_dir, chunk_dicts)

            # Accept if: integration passes OR (all chunks succeeded AND no cross-chunk deps)
            has_cross_deps = any(c.dependencies for c in decomposition.chunks)
            integration_ok = integration.passed or (
                chunks_succeeded == len(decomposition.chunks) and not has_cross_deps
            )

            if integration_ok and chunks_succeeded == len(decomposition.chunks):
                # Success! Record the decomposition
                self.library.record_decomposition(decomposition)
                duration = time.monotonic() - start_time
                return OuterLoopResult(
                    project_id=project_id,
                    success=True,
                    chunks_run=len(decomposition.chunks),
                    chunks_succeeded=chunks_succeeded,
                    re_chunk_attempts=re_chunk_attempts,
                    total_duration_seconds=duration,
                    output_dir=str(project_dir),
                    decomposition={
                        "chunks": [
                            {"name": c.name, "files": c.files, "description": c.description}
                            for c in decomposition.chunks
                        ],
                        "reasoning": decomposition.reasoning,
                        "matched_rule": decomposition.matched_rule,
                    },
                    integration_result=integration,
                    learning_events=learning_events,
                )

            # Step 5: Rejection — learn and re-chunk
            re_chunk_attempts += 1

            # Log failure
            failure = FailureRecord(
                project_id=project_id,
                spec_hash=hash_spec(task_spec),
                chunks=[c.name for c in decomposition.chunks],
                failure_type=_classify_failure(integration, chunk_results),
                detail=integration.error_summary or "Unknown integration failure",
                affected_files=_collect_affected_files(integration, decomposition),
            )
            log_failure(failure)
            learning_events.append(
                f"Re-chunk {re_chunk_attempts}: {failure.failure_type} — {failure.detail[:100]}"
            )

            # Run learner
            from src.outer_loop.learner import analyze_failure
            rule = analyze_failure(failure, self.library)
            if rule:
                learning_events.append(f"Learned rule: {rule.id} ({rule.condition} → {rule.action})")
                failure.generated_rule = rule.id

            if re_chunk_attempts >= self.MAX_RECHUNK_ATTEMPTS:
                break

            # Re-chunk with new knowledge — but check for dedup first
            print(f"\n[OUTER LOOP] Re-chunking attempt {re_chunk_attempts}...")
            previous_decomposition = decomposition
            decomposition = self._decompose(task_spec, metrics, project_id)

            # Dedup: if re-chunk produced same result, stop looping
            if previous_decomposition and self._chunks_identical(previous_decomposition, decomposition):
                print("[OUTER LOOP] Re-chunk produced identical decomposition — stopping")
                learning_events.append("Re-chunk dedup: identical decomposition, breaking loop")
                break

        # All re-chunk attempts exhausted
        duration = time.monotonic() - start_time
        return OuterLoopResult(
            project_id=project_id,
            success=False,
            chunks_run=len(decomposition.chunks),
            chunks_succeeded=chunks_succeeded,
            re_chunk_attempts=re_chunk_attempts,
            total_duration_seconds=duration,
            output_dir=str(project_dir) if project_dir else None,
            decomposition={
                "chunks": [
                    {"name": c.name, "files": c.files, "description": c.description}
                    for c in decomposition.chunks
                ],
                "reasoning": decomposition.reasoning,
            },
            integration_result=integration,
            learning_events=learning_events,
            error=f"Max re-chunk attempts ({self.MAX_RECHUNK_ATTEMPTS}) exhausted",
        )

    # ── Internal methods ───────────────────────────────────────────────────

    def _decompose(
        self, task_spec: str, metrics: dict, project_id: str
    ) -> Decomposition:
        """Run the decomposer — rules-first, semantic fallback."""
        from src.outer_loop.decomposer import Decomposer
        decomposer = Decomposer(library=self.library)
        return decomposer.decompose(task_spec)

    def _build_chunk_spec(
        self, original_spec: str, chunk: Chunk, decomposition: Decomposition
    ) -> str:
        """Build a self-contained sub-task spec for one chunk.

        Extracts only the relevant sections from the original spec and adds
        context about other chunks' interfaces.
        """
        from src.core.task_splitter import _extract_file_sections

        file_list = "\n".join(f"- {f}" for f in chunk.files) if chunk.files else "(none)"

        # Extract relevant spec sections
        try:
            from src.core.task_splitter import FileRef
            refs = [FileRef(path=f, action="modify") for f in chunk.files]
            sections = _extract_file_sections(original_spec, refs)
        except Exception:
            sections = "(Auto-extraction failed — using full spec context)"

        # Build dependency context
        dep_context = ""
        if chunk.dependencies:
            dep_context = "\n## Dependencies (other chunks)\n"
            for dep_name in chunk.dependencies:
                dep_chunk = next(
                    (c for c in decomposition.chunks if c.name == dep_name), None
                )
                if dep_chunk:
                    dep_context += (
                        f"- {dep_name}: {dep_chunk.description}\n"
                        f"  Contract: {dep_chunk.interface_contract or 'see specification'}\n"
                    )

        return f"""# {chunk.name}

## Files to create/modify:
{file_list}

## Description
{chunk.description}

{dep_context}

## Specification
{sections}

## Key Rules
- Complete implementations — NO stubs, NO TODO, NO pass
- Validate ALL user inputs. Handle edge cases.
- Use the write tool immediately. Output DONE when finished.
- Do NOT discuss, analyze, or plan — just write.
"""

    def _run_inner_pipeline(
        self, chunk_spec: str, chunk: Chunk, project_id: str
    ) -> dict[str, Any]:
        """Execute a single chunk through the existing MR-Krabs pipeline.

        This is the unchanged inner pipeline — same execute_with_judge(),
        same models, same everything.
        """
        # Ensure we're in the project context
        if self.project_dir:
            os.chdir(str(self.project_dir))

        try:
            from src.core.orchestrator import LLMOrchestrator

            orchestrator = LLMOrchestrator()

            # Map the chunk spec into the format execute_with_judge expects
            result = orchestrator.execute_with_judge(
                task_id=f"{project_id}-{chunk.name}",
                context={"task_spec": chunk_spec},
                tiers=None,  # Use default tiers from config
                max_retries_per_tier=3,
                judge_model="judge",
            )
            return result

        except Exception as e:
            return {
                "task_id": f"{project_id}-{chunk.name}",
                "success": False,
                "output": None,
                "tier_used": None,
                "attempts_total": 0,
                "error": str(e),
            }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _classify_failure(
    integration: IntegrationResult,
    chunk_results: list[tuple[Chunk, dict]],
) -> str:
    """Classify the type of integration failure."""
    # Check for missing files (seam mismatch)
    if any("Missing file" in e for e in integration.import_errors):
        return "seam_mismatch"

    # Check for import errors (missing dependency)
    if any("Import" in e or "ModuleNotFound" in e for e in integration.import_errors):
        return "missing_dep"

    # Check if any chunk was too large to succeed
    for chunk, result in chunk_results:
        if not result.get("success") and len(chunk.files) > 20:
            return "over_chunk"

    # Check if chunks were too granular (too many small chunks)
    if len(chunk_results) > 5:
        return "under_chunk"

    return "seam_mismatch"


def _collect_affected_files(
    integration: IntegrationResult,
    decomposition: Decomposition,
) -> list[str]:
    """Collect files affected by the integration failure."""
    files = []
    for error in integration.import_errors + integration.runtime_errors:
        # Extract file paths from error messages
        import re
        for match in re.finditer(r"['\"]?([a-zA-Z0-9_/.~@-]+\.py)['\"]?", error):
            path = match.group(1)
            if path not in files and "/" in path:
                files.append(path)

    if not files:
        # Fallback: collect all files from all chunks
        for chunk in decomposition.chunks:
            files.extend(chunk.files[:3])

    return files[:10]  # Cap at 10


# ── Convenience entry point ─────────────────────────────────────────────────


def execute_with_outer_loop(
    task_spec: str,
    project_name: str = "unnamed",
    work_dir: Optional[str] = None,
) -> OuterLoopResult:
    """Convenience function to run a task through the outer loop.

    Args:
        task_spec: The full task specification
        project_name: Human-readable project name
        work_dir: Working directory for chunk outputs (uses temp dir if None)

    Returns:
        OuterLoopResult with execution details
    """
    orchestrator = OuterLoopOrchestrator(
        work_dir=Path(work_dir) if work_dir else None,
    )
    return orchestrator.execute(task_spec, project_name)
