#!/usr/bin/env python3
"""Decomposer — analyzes specs and chunks them into kiosk-sized sub-tasks.

Primary: rule engine (explicit decomposition rules from learned patterns)
Fallback: semantic matching (embed spec → find nearest successful decomposition)

Produces a Decomposition plan that the orchestrator feeds chunk-by-chunk into MR-Krabs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.config_loader import get_config
from src.outer_loop.models import get_outer_loop_models
from src.outer_loop.pattern_library import (
    Chunk,
    Decomposition,
    PatternLibrary,
    compute_spec_metrics,
    hash_spec,
)


# ── Chunk size baseline ─────────────────────────────────────────────────────
# The kiosk challenge is our proven sweet spot. Chunks should be roughly
# this size or smaller.
#
# These are FALLBACK values. The decomposer now:
#   1. Checks learned rules from the pattern library (from past failures)
#   2. Probes the L0 tier's actual context window
#   3. Uses the SMALLEST of: learned limit, context-window limit, or hardcoded max

KIOSK_FILE_COUNT = 17   # baseline reference
MAX_FILES_PER_CHUNK = 20  # absolute ceiling
MIN_FILES_PER_CHUNK = 1   # allow single-file chunks (Jetson, small models)


def probe_tier_capacity() -> int:
    """Query the L0 tier's actual context window and compute safe files-per-pass.

    Returns the recommended max files per chunk based on available context.
    Smaller models (8K ctx) → 1-2 files. Mid-size (32K) → 3-5 files.
    Large (128K+) → 10-15 files.

    Falls back to MAX_FILES_PER_CHUNK if probing fails.
    """
    try:
        from src.core.token_budget import resolve_base_url, query_context_window
        base_url = resolve_base_url(
            "l0-coder",
            getattr(get_config(), 'opencode_models', {}),
            getattr(get_config(), 'pi_models', {}),
        )
        if base_url:
            n_ctx = query_context_window(base_url)
            if n_ctx:
                # Conservative formula: ~1 file per 8K of context
                # 8K → 1 file, 32K → 4 files, 128K → 16 files
                files_per_pass = max(1, n_ctx // 8192)
                # Cap at absolute max
                return min(files_per_pass, MAX_FILES_PER_CHUNK)
    except Exception:
        pass
    return MAX_FILES_PER_CHUNK


def get_learned_chunk_limit(library: "PatternLibrary") -> int | None:
    """Check if the library has a learned max_files_per_chunk rule from failures.

    Returns the learned limit, or None if no failures have been recorded.
    """
    if library is None:
        return None
    try:
        for rule in library.rules.values():
            if "max_files_per_chunk" in rule.condition:
                # Extract the limit from the condition: "max_files_per_chunk <= N"
                import re
                match = re.search(r'<=\s*(\d+)', rule.condition)
                if match and rule.confidence >= 0.5:
                    limit = int(match.group(1))
                    # Only apply if it's more restrictive than the ceiling
                    if limit < MAX_FILES_PER_CHUNK:
                        return limit
    except Exception:
        pass
    return None


def compute_adaptive_chunk_limit(library: "PatternLibrary") -> int:
    """Compute the optimal max files per chunk for current hardware.

    Combines three signals:
    1. Learned limit from past failures (most important)
    2. Context window probe (hardware capacity)
    3. Absolute ceiling (safety)

    Returns the smallest of all three, clamped to [MIN_FILES_PER_CHUNK, MAX_FILES_PER_CHUNK].
    """
    limits = [MAX_FILES_PER_CHUNK]

    learned = get_learned_chunk_limit(library)
    if learned:
        limits.append(learned)

    capacity = probe_tier_capacity()
    if capacity:
        limits.append(capacity)

    return max(MIN_FILES_PER_CHUNK, min(limits))


class Decomposer:
    """Analyze a task spec and produce a decomposition plan."""

    def __init__(self, library: PatternLibrary | None = None):
        self.library = library or PatternLibrary()
        self.models = get_outer_loop_models()

    def decompose(self, spec_text: str) -> Decomposition:
        """Analyze spec and produce a chunk plan.

        Priority:
        1. Rule engine match (fast, deterministic)
        2. LLM structural analysis (when no rules match)
        3. Semantic fallback (novel project shapes, only if embeddings available)

        The chunk size adapts to the hardware: probes context window and
        incorporates learned limits from past failures.
        """
        project_id = hash_spec(spec_text)
        metrics = compute_spec_metrics(spec_text)

        # ── Adaptive chunk limit ──────────────────────────────────
        # Check if past failures have taught us a smaller chunk size
        adaptive_limit = compute_adaptive_chunk_limit(self.library)
        if adaptive_limit < MAX_FILES_PER_CHUNK:
            metrics["max_files_per_chunk"] = adaptive_limit
            print(f"  [DECOMPOSE] Adaptive chunk limit: {adaptive_limit} files "
                  f"(learned={get_learned_chunk_limit(self.library)}, "
                  f"capacity={probe_tier_capacity()})")

        # ── Step 1: Try rule engine ────────────────────────────────
        matching_rules = self.library.get_matching_rules(metrics)
        if matching_rules:
            best_rule = matching_rules[0]
            chunks = self._apply_rule(best_rule, spec_text, metrics)
            if chunks:
                dec = Decomposition(
                    project_id=project_id,
                    chunks=chunks,
                    reasoning=f"Matched rule: {best_rule.id} — {best_rule.action}",
                    matched_rule=best_rule.id,
                )
                self.library.record_decomposition(dec)
                return dec

        # ── Step 2: LLM-driven structural analysis ──────────────────
        chunks = self._llm_decompose(spec_text, metrics)
        if chunks:
            dec = Decomposition(
                project_id=project_id,
                chunks=chunks,
                reasoning="LLM structural analysis — no matching rule found",
            )
            self.library.record_decomposition(dec)
            return dec

        # ── Step 3: Single-chunk fallback (under threshold) ─────────
        # If the spec is small enough, run it as one chunk (passthrough)
        if metrics["file_count"] <= MAX_FILES_PER_CHUNK:
            # Extract file list from spec
            files_in_spec = self._extract_files(spec_text)
            chunk = Chunk(
                name="full_project",
                files=files_in_spec,
                description="Single chunk — within kiosk size threshold",
            )
            dec = Decomposition(
                project_id=project_id,
                chunks=[chunk],
                reasoning="Spec within kiosk threshold — single chunk passthrough",
            )
            self.library.record_decomposition(dec)
            return dec

        # ── Step 4: Emergency chunk by directory ────────────────────
        chunks = self._directory_chunk(spec_text, metrics)
        dec = Decomposition(
            project_id=project_id,
            chunks=chunks,
            reasoning="Emergency directory-based chunking — all other methods failed",
        )
        self.library.record_decomposition(dec)
        return dec

    def _apply_rule(
        self, rule, spec_text: str, metrics: dict
    ) -> list[Chunk] | None:
        """Apply a decomposition rule. Rules can specify actions like
        'group by directory, max 15 per chunk' or 'split frontend from backend'.
        """
        action = rule.action.lower()

        if "group by directory" in action or "directory" in action:
            # Extract max per chunk from rule action
            max_per = MAX_FILES_PER_CHUNK
            match = re.search(r"max\s+(\d+)", action)
            if match:
                max_per = int(match.group(1))
            return self._directory_chunk(spec_text, metrics, max_per)

        if "frontend" in action and "backend" in action:
            return self._split_frontend_backend(spec_text)

        if "single chunk" in action or "passthrough" in action:
            files_in_spec = self._extract_files(spec_text)
            return [
                Chunk(
                    name="full_project",
                    files=files_in_spec,
                    description=f"Single chunk — rule: {rule.id}",
                )
            ]

        # Unrecognized action — fall through to LLM
        return None

    def _llm_decompose(
        self, spec_text: str, metrics: dict
    ) -> list[Chunk] | None:
        """Use the decomposer LLM to analyze the spec and produce chunks.

        If the models are not reachable (e.g., unit test context), returns None
        so the caller can fall back to directory-based chunking.
        """
        import subprocess
        import shlex

        model = self.models.get("decomposer")
        if not model:
            return None

        # Build the decomposition prompt
        prompt = self._build_decompose_prompt(spec_text, metrics)

        # Call LLM via the existing orchestrator patterns (OpenAI-compatible)
        try:
            result = self._call_llm(model, prompt)
            if not result:
                return None
            return self._parse_chunks(result)
        except Exception:
            return None

    def _build_decompose_prompt(self, spec_text: str, metrics: dict) -> str:
        """Build the decomposition prompt for the LLM."""
        # Include past successful decompositions as examples if available
        examples = ""
        past_decs = self.library.get_latest_decompositions(3)
        if past_decs:
            examples = "\n## Past Successful Decompositions (for reference)\n\n"
            for dec in past_decs:
                chunk_names = [c.name for c in dec.chunks]
                examples += (
                    f"- Project {dec.project_id}: "
                    f"{len(dec.chunks)} chunks → {chunk_names}\n"
                )

        return f"""# Task Decomposition Analysis

You are the MR-Krabs outer loop decomposer. Your job is to analyze a task
specification and break it into kiosk-sized chunks (~{KIOSK_FILE_COUNT} files each)
that the inner MR-Krabs pipeline can handle reliably.

## Spec Metrics
- Files referenced: {metrics["file_count"]}
- Total lines: {metrics["total_lines"]}
- Directory count: {metrics["directory_count"]}
- Has tests: {metrics["has_tests"]}
- Has docs: {metrics["has_docs"]}

{examples}

## Chunking Rules
1. Each chunk MUST have ≤ {MAX_FILES_PER_CHUNK} files
2. Each chunk MUST have ≥ {MIN_FILES_PER_CHUNK} files (don't micro-chunk)
3. Keep related files together (same import cluster, same directory)
4. Cross-cutting concerns (config, utils, base classes) should be in
   their own chunk or bundled with the chunk that depends on them.
5. Tests should be in the same chunk as the code they test
6. Order chunks by dependency — foundational chunks first

## Output Format
Return a JSON array of chunks. Each chunk has:
- name: short identifier (e.g. "models_and_db", "routes", "templates")
- files: list of file paths in this chunk
- description: what this chunk builds
- dependencies: list of other chunk names this depends on
- interface_contract: what this chunk exports/expects

```json
[
  {{
    "name": "chunk_name",
    "files": ["path/to/file1.py", "path/to/file2.py"],
    "description": "Builds the data layer and models",
    "dependencies": [],
    "interface_contract": "Exports: User model, Task model, DB session factory"
  }}
]
```

## Task Specification

{spec_text}

## Your Analysis

First, analyze the project structure and identify logical component boundaries.
Then output ONLY the JSON chunk array (no other text)."""

    def _call_llm(self, model, prompt: str) -> str | None:
        """Call the LLM via curl to the OpenAI-compatible endpoint."""
        import subprocess
        import shlex

        provider_cfg = self._get_provider_config(model.provider)
        if not provider_cfg:
            return None

        payload = json.dumps({
            "model": model.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
            "stream": False,
        })

        try:
            result = subprocess.run(
                [
                    "curl", "-sS", "--max-time", "300",
                    "-X", "POST",
                    f"{provider_cfg['base_url']}/chat/completions",
                    "-H", "Content-Type: application/json",
                    "-H", f"Authorization: Bearer {provider_cfg['api_key']}",
                    "-d", payload,
                ],
                capture_output=True, text=True, timeout=310,
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception:
            return None

    def _get_provider_config(self, provider_name: str) -> dict | None:
        """Look up provider config from ~/.mrkrabs/config.yaml."""
        try:
            from src.core.config_loader import get_config
            config = get_config()
            provider = config.providers.get(provider_name)
            if provider:
                return {
                    "base_url": provider.base_url.rstrip("/"),
                    "api_key": provider.api_key or "",
                }
        except Exception:
            pass
        return None

    def _parse_chunks(self, llm_output: str) -> list[Chunk] | None:
        """Parse chunk JSON from LLM output."""
        try:
            # Extract JSON array (may be wrapped in markdown code blocks)
            json_match = re.search(
                r"```(?:json)?\s*(\[.*?\])\s*```", llm_output, re.DOTALL
            )
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(llm_output)

            chunks = []
            for item in data:
                chunks.append(Chunk(
                    name=item.get("name", f"chunk_{len(chunks)}"),
                    files=item.get("files", []),
                    description=item.get("description", ""),
                    dependencies=item.get("dependencies", []),
                    interface_contract=item.get("interface_contract", ""),
                ))
            return chunks if chunks else None
        except (json.JSONDecodeError, KeyError):
            return None

    def _directory_chunk(
        self, spec_text: str, metrics: dict, max_per: int = MAX_FILES_PER_CHUNK
    ) -> list[Chunk]:
        """Fallback: chunk by directory proximity."""
        files = self._extract_files(spec_text)
        if not files:
            return [
                Chunk(
                    name="full_project",
                    files=["(no files detected)"],
                    description="No file references found in spec",
                )
            ]

        # Group by directory
        dir_groups: dict[str, list[str]] = {}
        for fp in files:
            parts = fp.split("/")
            key = "/".join(parts[:-1]) if len(parts) >= 2 else "root"
            dir_groups.setdefault(key, []).append(fp)

        # Pack into chunks
        chunks: list[Chunk] = []
        current_files: list[str] = []
        current_name = ""

        for dir_name, dir_files in sorted(dir_groups.items(), key=lambda x: len(x[1]), reverse=True):
            if len(current_files) + len(dir_files) <= max_per:
                current_files.extend(dir_files)
                current_name = f"{current_name}_{dir_name}" if current_name else dir_name
            else:
                # Flush current chunk
                if current_files:
                    chunks.append(Chunk(
                        name=current_name.replace("/", "_"),
                        files=current_files,
                        description=f"Files in {current_name}",
                    ))
                current_files = list(dir_files)
                current_name = dir_name

        if current_files:
            chunks.append(Chunk(
                name=current_name.replace("/", "_"),
                files=current_files,
                description=f"Files in {current_name}",
            ))

        return chunks

    def _split_frontend_backend(self, spec_text: str) -> list[Chunk]:
        """Split a full-stack spec into frontend and backend chunks."""
        files = self._extract_files(spec_text)

        frontend_exts = {".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".vue"}
        frontend_files: list[str] = []
        backend_files: list[str] = []

        for fp in files:
            ext = "." + fp.rsplit(".", 1)[-1] if "." in fp else ""
            if ext in frontend_exts or "template" in fp.lower() or "static" in fp.lower():
                frontend_files.append(fp)
            else:
                backend_files.append(fp)

        chunks = []
        if backend_files:
            chunks.append(Chunk(
                name="backend",
                files=backend_files,
                description="Backend logic: models, routes, config",
                interface_contract="Exports: API endpoints, data models",
            ))
        if frontend_files:
            chunks.append(Chunk(
                name="frontend",
                files=frontend_files,
                description="Frontend: templates, static assets, JS/CSS",
                dependencies=["backend"] if backend_files else [],
                interface_contract="Consumes: API endpoints from backend",
            ))
        return chunks

    def _extract_files(self, spec_text: str) -> list[str]:
        """Extract file paths from spec text.

        Matches patterns like:
          - `## 1. path/to/file.py` (numbered section headers)
          - `File: path/to/file.py` (explicit prefix)
          - `- path/to/file.py` (bullet list)
          - `Write a ... called file_stats.py` (prose filename)
          - `create test_foo.py` (action + filename)
          - `path/to/file.py` (backtick-quoted)
        """
        code_ext = (
            r"\.(?:py|md|yaml|yml|toml|json|cfg|ini|sh|sql|html|css|js|ts|rs|go|java|c|cpp|h|hpp)"
        )
        seen: set[str] = set()
        files: list[str] = []

        # Pattern 1: Numbered section headers (## 1. path/to/file.py)
        numbered = re.compile(
            r"##\s+\d+\.\s+([a-zA-Z0-9_/.~@-]+" + code_ext + r")",
            re.MULTILINE,
        )
        for match in numbered.finditer(spec_text):
            path = match.group(1).strip()
            if path not in seen:
                seen.add(path)
                files.append(path)

        # Pattern 2: File: prefix or bullet
        line_pattern = re.compile(
            r"(?:^|\n)\s*(?:File:\s*|[-*]\s*)?"
            r"([a-zA-Z0-9_/.~@-]+" + code_ext + r")"
            r"(?=\s|$|,|\.|\n|—|\))",
            re.MULTILINE,
        )
        for match in line_pattern.finditer(spec_text):
            path = match.group(1).strip()
            if path not in seen:
                seen.add(path)
                files.append(path)

        # Pattern 3: Backtick-quoted paths
        backtick = re.compile(r"`([a-zA-Z0-9_/.~@-]+" + code_ext + r")`")
        for match in backtick.finditer(spec_text):
            path = match.group(1).strip()
            if path not in seen:
                seen.add(path)
                files.append(path)

        # Pattern 4: Prose filenames — "called file_stats.py", "create test_foo.py"
        prose_patterns = [
            re.compile(r"called\s+([a-zA-Z0-9_/-]+" + code_ext + r")", re.IGNORECASE),
            re.compile(r"create\s+([a-zA-Z0-9_/-]+" + code_ext + r")", re.IGNORECASE),
            re.compile(r"write\s+(?:a\s+)?(?:Python\s+)?(?:module|tool|script|file|app)\s+(?:called\s+)?([a-zA-Z0-9_/-]+" + code_ext + r")", re.IGNORECASE),
            re.compile(r"(?:^|\n)([a-zA-Z0-9_/-]+\.py)\b", re.MULTILINE),
        ]
        for pattern in prose_patterns:
            for match in pattern.finditer(spec_text):
                path = match.group(1).strip()
                if path not in seen:
                    seen.add(path)
                    files.append(path)

        return files
