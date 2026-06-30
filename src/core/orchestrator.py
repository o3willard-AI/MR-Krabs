#!/usr/bin/env python3
"""Multi-Tier LLM Orchestrator - Core Implementation"""

import json
import os
import re
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import warnings

from src.core.circuit_breaker import CircuitBreakerRegistry
from src.core.cost import CostTracker, TokenCount
from src.core.judge import Judge, Verdict
from src.core.model_config import get_models
from src.core.failure_action import FailureAction
from src.core.tier_config import get_tier_failure_action, get_tier_max_retries
from src.core.fail_now import get_fail_now, clear_fail_now, is_fail_now_active, check_mesh_fail_now
from src.core.fail_now import is_fail_up_active, clear_fail_up, check_mesh_fail_up
from src.core.model_profiles import get_prepend, get_known_failures
from src.core.context_compressor import compress_history, estimate_context_fill

# Prompt flow debug logger (opt-in via MRKRABS_PROMPT_FLOW_DEBUG=1)
from src.core.prompt_flow_logger import PromptFlowLogger
from src.core.task_splitter import (
    extract_file_refs,
    split_into_passes,
    generate_subtask_spec,
    MAX_FILES_PER_PASS,
)
from src.core.pi_provider_map import validate_or_diagnose, get_registry

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2

# Unbuffer stdout so pipeline progress is visible in background/piped mode
import builtins as _bi
print = lambda *a, **kw: _bi.print(*a, **{**kw, "flush": True})

CONTEXT_SIMPLIFICATION = [1.0, 0.7, 0.4]

# Import the capability checker
from src.core.model_capabilities import MODEL_REGISTRY, get_capable_models


class FileTools:
    """File read/write operations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def _fix_escaped_content(self, content: str) -> str:
        """P4: Fix escaped newlines/characters from L0-Coder output.

        L0-Coder (Qwen3-Coder 30B) often outputs \\n instead of actual newlines
        in triple-quoted strings. This method detects and fixes that pattern.
        """
        # Detect escaped newline pattern (common L0-Coder issue)
        # If content has literal backslash-n but no actual newlines, fix it
        if "\\n" in content and content.count("\n") < 5:
            # Likely escaped - convert to actual characters
            content = content.replace("\\n", "\n")
            content = content.replace("\\t", "\t")
            content = content.replace('\\"', '"')
            content = content.replace("\\\\", "\\")
        return content

    def file_read(self, path: str) -> dict[str, Any]:
        """Read a file and return contents."""
        try:
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.project_root / file_path
            if not file_path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}
            content = file_path.read_text()
            return {
                "success": True,
                "path": str(file_path),
                "content": content,
                "lines": len(content.splitlines()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def file_write(self, path: str, content: str) -> dict[str, Any]:
        """Write content to a file with post-processing for L0-Coder issues."""
        try:
            # P4: Fix escaped newlines from L0-Coder (common issue)
            content = self._fix_escaped_content(content)

            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.project_root / file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            return {"success": True, "path": str(file_path), "bytes": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ToolExecutor:
    """Executes tool calls from LLM responses."""

    def __init__(self, file_tools: FileTools):
        self.file_tools = file_tools

    def _validate_tool_call(self, tool: str, path: str) -> bool:
        """Validate tool call parameters before execution (P2)."""
        if not path:
            return False

        # Check path length
        if len(path) > 500:
            return False

        # Check for corrupted JSON artifacts
        if path.startswith("}") or path.startswith("{"):
            return False
        if path.startswith("]]") or path.startswith("[["):
            return False

        # Check for newlines in path (indicates parsing error)
        if "\n" in path or "\r" in path:
            return False

        # Check for valid path characters (allow common path chars)
        if not re.match(r"^[a-zA-Z0-9_./\-\\]+$", path):
            return False

        # Check path doesn't start with special chars
        if path.startswith("/") and len(path) > 1 and path[1] in "{}[]()":
            return False

        return True

    def parse_and_execute_tools(self, response: str) -> dict[str, Any]:
        """Parse LLM response for tool calls and execute them.

        P8 FIX: Removed broken JSON line parser that failed on multi-line content.
        Now relies on regex patterns which handle multi-line content correctly with re.DOTALL.
        """
        results = []

        # Pattern 1: Custom file_write - file_write("path", """content""")
        write_pattern = r'file_write\(["\']([^"\']+)["\'],\s*"""(.+?)"""'
        for match in re.finditer(write_pattern, response, re.DOTALL):
            path = match.group(1)
            content = match.group(2)
            result = self.file_tools.file_write(path, content)
            results.append(
                {
                    "tool": "file_write",
                    "path": path,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                    "bytes": result.get("bytes", 0),
                }
            )

        # Pattern 2: Custom file_read - file_read("path")
        read_pattern = r'file_read\(["\']([^"\']+)["\']\)'
        for match in re.finditer(read_pattern, response):
            path = match.group(1)
            result = self.file_tools.file_read(path)
            results.append(
                {
                    "tool": "file_read",
                    "path": path,
                    "success": result.get("success", False),
                    "content": result.get("content"),
                    "error": result.get("error"),
                }
            )

        # Pattern 3: Claude native write - {"name": "write_file", "parameters": {"path": "x", "content": "y"}}
        # P9 FIX: Improved pattern to handle multi-line content and escaped characters
        # Matches entire JSON object to avoid partial matches
        claude_write = r'\{\s*"name"\s*:\s*"write_file"\s*,\s*"parameters"\s*:\s*\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)+)"\s*\}\s*\}'
        for match in re.finditer(claude_write, response, re.DOTALL):
            path = match.group(1)
            content = match.group(2)
            result = self.file_tools.file_write(path, content)
            results.append(
                {
                    "tool": "file_write",
                    "path": path,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                    "bytes": result.get("bytes", 0),
                    "format": "claude_native",
                }
            )

        # Pattern 4: Claude native read - {"name": "read_file", "parameters": {"path": "x"}}
        # Fixed: Use [^{}]* to prevent matching across JSON object boundaries
        claude_read = r'\{\s*"name"\s*:\s*"read_file"\s*,\s*"parameters"\s*:\s*{\s*"path"\s*:\s*"([^"]+)"\s*}\s*}'
        for match in re.finditer(claude_read, response):
            path = match.group(1)
            result = self.file_tools.file_read(path)
            results.append(
                {
                    "tool": "file_read",
                    "path": path,
                    "success": result.get("success", False),
                    "content": result.get("content"),
                    "error": result.get("error"),
                    "format": "claude_native",
                }
            )

        # Pattern 5: MiniMax XML write - <invoke name="Write">
        minimax_write = r'<invoke\s+name="Write"[^>]*>\s*<parameter\s+name="file_path"[^>]*>([^<]+)[\s\S]*?<parameter\s+name="content"[^>]*>([^<]+)'
        for match in re.finditer(minimax_write, response, re.DOTALL):
            path = match.group(1).strip()
            content = match.group(2).strip()
            result = self.file_tools.file_write(path, content)
            results.append(
                {
                    "tool": "file_write",
                    "path": path,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                    "bytes": result.get("bytes", 0),
                    "format": "minimax_native",
                }
            )

        # Pattern 6: MiniMax XML read - <invoke name="Read">
        minimax_read = r'<invoke\s+name="Read"[^>]*>\s*<parameter\s+name="file_path"[^>]*>([^<]+)'
        for match in re.finditer(minimax_read, response, re.DOTALL):
            path = match.group(1).strip()
            result = self.file_tools.file_read(path)
            results.append(
                {
                    "tool": "file_read",
                    "path": path,
                    "success": result.get("success", False),
                    "content": result.get("content"),
                    "error": result.get("error"),
                    "format": "minimax_native",
                }
            )

        return {
            "tool_results": results,
            "tools_executed": len(results),
            "all_succeeded": all(r.get("success", False) for r in results) if results else True,
        }


class LLMOrchestrator:
    """Orchestrates multi-tier LLM workflow."""

    def __init__(self, project_root: str = str(Path(__file__).parent.parent.parent)):
        self.project_root = Path(project_root)
        self.workflow_dir = self.project_root / "docs" / "workflow"
        self.tasks_dir = self.project_root / "docs" / "tasks"
        self.handoffs_dir = self.workflow_dir / "handoffs"
        self.escalations_dir = self.workflow_dir / "escalations"
        self.file_tools = FileTools(self.project_root)
        self.tool_executor = ToolExecutor(self.file_tools)
        self.cost_tracker = CostTracker()
        self.circuit_breaker_registry = CircuitBreakerRegistry()
        
        # Initialize provider adapter router (Phase 2 — LiteLLM adapter wiring)
        from src.adapters.provider_router import ProviderRouter
        self.provider_router = ProviderRouter()
        
        # Caching middleware (Phase 3) — LRU cache for LLM responses
        from src.adapters.cache import CachingAdapter
        self.cache = CachingAdapter(config={
            "max_entries": 1000,
            "default_ttl_seconds": 3600,
            "enabled": True,
        })
        
        # Rate limiter (Phase 4) — exponential backoff with jitter
        from src.adapters.rate_limit import RateLimitHandler, RateLimitConfig
        self.rate_limiter = RateLimitHandler(config=RateLimitConfig(
            max_retries=MAX_RETRIES,
            base_delay_s=RETRY_DELAY,
            max_delay_s=60.0,
            jitter_factor=0.25,
        ))
        
        # Unified cost calculator (Phase 5)
        from src.adapters.cost_calculator import CostCalculator
        self.cost_calculator = CostCalculator()
        # Replace CostTracker's hardcoded pricing with adapter
        self.cost_tracker.cost_calculator = self.cost_calculator
        
        # Initialize notifier
        from src.core.notify import FallbackNotifier, MeshNotifier, TelegramNotifier
        self.notifier = FallbackNotifier(
            MeshNotifier(),
            TelegramNotifier(),
        )

        # Create directories
        for d in [self.handoffs_dir, self.escalations_dir, self.tasks_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Coder backends — OpenCode (default), PI (fallback)
        # Config keys: opencode_models, opencode_timeouts, pi_models, pi_timeouts
        try:
            from src.core.config_loader import load_config
            cfg = load_config()
            # OpenCode coder backend (default)
            raw_oc = getattr(cfg, "opencode_models", None) or {}
            self.opencode_models = {k.lower(): v for k, v in raw_oc.items()}
            raw_ot = getattr(cfg, "opencode_timeouts", None) or {}
            self.opencode_timeouts = {k.lower(): v for k, v in raw_ot.items()}
            # PI coder backend (fallback)
            raw_pi = getattr(cfg, "pi_models", None) or {}
            self.pi_models = {k.lower(): v for k, v in raw_pi.items()}
            raw_pt = getattr(cfg, "pi_timeouts", None) or {}
            self.pi_timeouts = {k.lower(): v for k, v in raw_pt.items()}
            raw_wf = getattr(cfg, "workflows", None) or {}
            self.workflows = {k.lower(): v for k, v in raw_wf.items()}
            # R2: Protected file patterns — PI must never write to these.
            raw_prot = getattr(cfg, "protected_files", None)
            self.protected_file_patterns = list(raw_prot) if raw_prot else [
                ".env", ".env.*", "*.kdbx", "*.key", "secrets/*",
                ".mrkrabs/config.yaml", "pyproject.toml", ".git/*",
            ]
        except Exception:
            self.opencode_models = {}
            self.opencode_timeouts = {}
            self.pi_models = {}
            self.pi_timeouts = {}
            self.workflows = {}
            self.protected_file_patterns = []

        # Prompt flow debug logger (no-op when disabled)
        debug_enabled = os.environ.get("MRKRABS_PROMPT_FLOW_DEBUG", "") == "1"
        self._prompt_flow_logger = PromptFlowLogger(
            task_id="__init__", enabled=debug_enabled
        )

        # Pipeline self-monitor — tracks role summaries and detects anomalies
        from src.core.pipeline_monitor import PipelineMonitor
        self.monitor = PipelineMonitor()

    def get_api_key(self, tier: str) -> str | None:
        """Get API key for specified tier."""
        config = get_models().get(tier, {})
        env_var = config.get("env_var")
        return os.environ.get(env_var) if env_var else None

    def call_llm_with_retry(
        self,
        tier: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Call LLM with retry logic and optional global timeout."""
        last_error = None
        start_time = time.time()  # wall clock for os.path.getmtime() comparison
        start_mono = time.monotonic()  # monotonic for duration calculation
        effective_timeout = timeout_seconds or 300.0

        for attempt in range(MAX_RETRIES):
            elapsed = time.monotonic() - start_mono
            if elapsed >= effective_timeout:
                return {
                    "success": False,
                    "error": f"Task timed out after {elapsed:.1f}s (limit: {effective_timeout}s)",
                    "attempts": attempt,
                    "ready_for_escalation": True,
                    "timed_out": True,
                }

            try:
                multiplier = CONTEXT_SIMPLIFICATION[min(attempt, len(CONTEXT_SIMPLIFICATION) - 1)]
                prompt = (
                    self._simplify_context(user_prompt, multiplier) if attempt > 0 else user_prompt
                )

                call_start = time.monotonic()
                response = self.call_llm(tier, system_prompt, prompt, temperature)
                call_end = time.monotonic()

                return {
                    "success": True,
                    "output": response,
                    "attempt": attempt + 1,
                    "duration_seconds": call_end - call_start,
                    "context_simplified": attempt > 0,
                }
            except Exception as e:
                last_error = str(e)
                print(f"  Attempt {attempt + 1}/{MAX_RETRIES} failed: {last_error}")
                if attempt < MAX_RETRIES - 1:
                    delay = self.rate_limiter.get_backoff_delay(
                        tier, retry_count=attempt
                    )
                    print(f"  Retrying in {delay:.1f}s with simplified context...")
                    time.sleep(delay)

        return {
            "success": False,
            "error": last_error,
            "attempts": MAX_RETRIES,
            "ready_for_escalation": True,
        }

    def _simplify_context(self, prompt: str, multiplier: float) -> str:
        """Simplify prompt for retry by preserving instruction and truncating from end.

        Strategy:
        1. Keep the first N lines (the original instruction / system prompt)
        2. Truncate from the end of the context
        3. For code-heavy context, try to preserve structure

        This is more robust than truncating the middle, which can remove
        the relevant function in code-heavy contexts.
        """
        if multiplier >= 1.0:
            return prompt

        lines = prompt.splitlines()
        if len(lines) <= 20:
            return prompt

        instruction_lines = min(10, len(lines) // 4)
        max_total = max(int(len(lines) * multiplier), 20)
        content_lines = max(0, max_total - instruction_lines)

        preserved = lines[:instruction_lines]
        truncated = lines[instruction_lines : instruction_lines + content_lines]

        result = preserved + truncated
        result.append(f"\n[Context truncated from {len(lines)} to {len(result)} lines]")
        return "\n".join(result)

    def truncate_file(self, file_path: Path, target_ratio: float) -> str:
        """Truncate a code file while preserving structure.

        Uses simple heuristics to keep:
        - Imports and module-level definitions
        - Function/class signatures (first line of each)
        - Docstrings (first line)
        - Truncates implementation bodies from the end

        Falls back to line-based truncation for non-code files.
        """
        if not file_path.exists():
            return ""

        content = file_path.read_text()
        lines = content.splitlines()

        if len(lines) <= 50:
            return content

        code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go", ".rs"}
        if file_path.suffix not in code_extensions:
            max_lines = max(int(len(lines) * target_ratio), 50)
            return (
                "\n".join(lines[:max_lines])
                + f"\n# [Truncated from {len(lines)} to {max_lines} lines]"
            )

        # Two-pass: first collect all function/class signatures at any indent level
        signatures = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("def ", "class ", "async def ")):
                signatures.add(i)

        max_lines = max(int(len(lines) * target_ratio), 50)
        result = []
        in_function = False
        body_lines_added = 0
        max_body_lines = max(3, max_lines - len(signatures) - 10)

        for i, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith(("import ", "from ")):
                if len(result) < max_lines:
                    result.append(line)
                continue

            if i in signatures:
                result.append(line)
                in_function = True
                body_lines_added = 0
                continue

            if in_function and stripped and not stripped.startswith("#"):
                if line and (line[0] != " " and line[0] != "\t"):
                    in_function = False
                    if len(result) < max_lines:
                        result.append(line)
                elif body_lines_added < max_body_lines:
                    result.append(line)
                    body_lines_added += 1
                else:
                    result.append(f"{line[:4]}... # [body truncated]")
                    in_function = False
            else:
                if len(result) < max_lines:
                    result.append(line)
                continue

        result.append(f"\n# [Truncated from {len(lines)} to {len(result)} lines]")
        return "\n".join(result)

    def call_llm(
        self, tier: str, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        """Call LLM through provider adapter framework (Phase 2 — adapter wiring).

        Replaces the old _call_openrouter / _call_lmstudio raw-requests path.
        Phase 3: checks LRU cache before calling adapter.
        Returns the response content string directly.
        """
        import hashlib, json

        # Phase 3: cache check
        cache_key = hashlib.sha256(
            json.dumps({
                "tier": tier,
                "system": system_prompt[:500],
                "user": user_prompt[:500],
                "temp": temperature,
            }, sort_keys=True).encode()
        ).hexdigest()

        if self.cache.enabled:
            cached = self.cache._store.get(cache_key)
            if cached:
                return cached["content"]

        adapter = self.provider_router.get_adapter(tier)
        if adapter is None:
            raise ValueError(f"No adapter for tier: {tier}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # Read max_tokens and stop tokens from tier config
            tier_cfg = self.provider_router._tiers.get(tier, {})
            max_tok = tier_cfg.get("max_tokens", 4096)
            stop = tier_cfg.get("stop")
            kwargs = {"temperature": temperature, "max_tokens": max_tok}
            if stop is not None:
                kwargs["stop"] = stop
            response = adapter.call_sync(messages, **kwargs)
            content = response.content

            # Phase 3: store in cache
            if self.cache.enabled:
                self.cache._store.set(cache_key, {"content": content})

            return content
        except Exception as e:
            raise Exception(f"Adapter call failed for tier {tier}: {e}")

    # ── Agent System Prompts ────────────────────────────────────────────

    def _get_agent_system_prompt(self, task_type: str = "code") -> str:
        """Load the agent system prompt template for the task type.

        Loads docs/workflow/templates/{task_type}-system-prompt.md.
        Falls back to a concise inline prompt if the template file is missing.
        """
        template_path = self.workflow_dir / "templates" / f"{task_type}-system-prompt.md"
        if template_path.exists():
            return template_path.read_text()
        return (
            "You are an expert software developer.\n"
            "Write complete, production-quality code.\n"
            "Use the write tool to create files — one file per tool call.\n"
            "Read existing files before modifying to match conventions.\n"
            "Handle edge cases, add docstrings, add type hints.\n"
            "If ambiguous, ask. Output DONE when finished.\n"
        )

    def _get_pi_system_prompt(self, task_type: str = "code") -> str:
        """Load the PI-adapted system prompt (uses write tool, not ===FILE: markers).

        Loads docs/workflow/templates/{task_type}-pi-system-prompt.md.
        Falls back to the standard code-system-prompt with a warning.
        """
        pi_template = self.workflow_dir / "templates" / f"{task_type}-pi-system-prompt.md"
        if pi_template.exists():
            return pi_template.read_text()
        std = self._get_agent_system_prompt(task_type)
        return (
            std
            + "\n\n## PI-SPECIFIC: Use the write tool to create files. "
            + "Do NOT use ===FILE: markers — those are for text-mode only."
        )

    def _build_system_prompt(self, tier: str, template: str) -> str:
        """Extract system prompt from template."""
        return template  # template already contains the full prompt

    def _get_opencode_rules(self) -> str:
        """Load domain-specific coding rules for OpenCode invocations.

        These rules are written to a temp file and attached via
        `opencode run -f <rules_file>`. OpenCode treats -f attachments
        as project context that persists through auto-compaction,
        unlike user-message-embedded rules that get summarized away.

        Loads docs/workflow/templates/code-opencode-rules.md.
        Returns empty string if the template doesn't exist (graceful degradation).
        """
        rules_path = self.workflow_dir / "templates" / "code-opencode-rules.md"
        if rules_path.exists():
            return rules_path.read_text()
        return ""

    def _is_protected_file(self, path: str) -> tuple[bool, str | None]:
        """Check whether a file path matches protected patterns. (R2)

        Returns (is_protected, matched_pattern).
        """
        import fnmatch
        from pathlib import Path
        clean = str(Path(path))
        for pattern in self.protected_file_patterns:
            if fnmatch.fnmatch(clean, pattern) or fnmatch.fnmatch(
                Path(clean).name, pattern
            ):
                return True, pattern
        return False, None

    def _resolve_sandboxed_path(
        self, path: str, project_root: str | None
    ) -> tuple[str | None, str | None]:
        """Resolve a file write path within the sandbox. (R3)

        If project_root is set, resolves the path relative to it and
        verifies it doesn't escape via '..' or symlinks.

        Returns (resolved_absolute_path, rejection_reason).
        rejection_reason is None if the path passes sandbox checks.
        """
        from pathlib import Path
        if not project_root:
            # No sandbox — passthrough
            return str(Path(path)), None

        root = Path(project_root).resolve()
        try:
            candidate = (root / path).resolve()
            candidate.relative_to(root)  # raises ValueError if escapes
            return str(candidate), None
        except ValueError:
            return None, f"path escapes sandbox: {path}"

    def _execute_pi_tier(
        self,
        tier: str,
        user_prompt: str,
        system_prompt: str = "",
        retry_num: int = 1,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Execute a coder tier through PI subprocess (--mode json).

        Args:
            tier: Tier key (l0-coder, l1-coder, l2-coder).
            user_prompt: The task specification / user message.
            system_prompt: Quality directives appended via --append-system-prompt.
            retry_num: Which retry attempt this is (for logging).
            project_root: Working directory for PI — file paths in the task
                spec are relative to this directory. If None, uses the
                orchestrator's CWD (typically the MR-Krabs repo).

        Returns:
            Dict matching call_llm_with_retry() shape:
            {success, output, attempt, duration_seconds, written_paths, ...}
        """
        import json as _json

        model_spec = self.pi_models.get(tier.lower())
        if not model_spec:
            return {
                "success": False,
                "error": f"No PI model for tier {tier}",
                "ready_for_escalation": True,
            }

        # ── Pre-flight: validate model in PI registry ────────────
        valid, diag = validate_or_diagnose(model_spec)
        print(f"  [PI-DIAG] {tier}: {diag}")
        if not valid:
            print(f"  [PI-WARN] {tier}: model '{model_spec}' not in PI registry — "
                  f"PI will fail. Check ~/.pi/agent/models.json")
            # Continue anyway — PI will report its own error

        # Pre-flight: server health check for local providers
        provider_name = model_spec.split("/", 1)[0] if "/" in model_spec else model_spec
        reg = get_registry()
        prov_info = reg.get_provider(provider_name)
        if prov_info and prov_info.get("base_url", "").startswith("http://192.168"):
            reachable, health_msg = reg.check_server_health(provider_name)
            if not reachable:
                print(f"  [PI-WARN] {tier}: server unreachable — {health_msg}")
            else:
                print(f"  [PI-DIAG] {tier}: {health_msg}")

        timeout = self.pi_timeouts.get(tier.lower(), 600)
        pi_cmd = ["pi", "--mode", "json", "--model", model_spec, "--no-session"]
        if system_prompt:
            # --append-system-prompt expects a FILE PATH, not inline content.
            # Write the prompt to a temp file and pass the path.
            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", prefix="mrkrabs_pi_sp_", delete=False
            )
            tmp.write(system_prompt)
            tmp.close()
            pi_cmd.extend(["--append-system-prompt", tmp.name])
            cleanup_sp = tmp.name
        else:
            cleanup_sp = None

        start_time = time.time()  # wall clock for os.path.getmtime() comparison
        start_mono = time.monotonic()  # monotonic for duration calculation

        # L1/L2 diagnostic: log model + prompt size for cloud tier debugging
        if tier.lower().startswith("l1") or tier.lower().startswith("l2"):
            print(f"  [DIAG] {tier} r{retry_num}: model={model_spec}, "
                  f"prompt={len(user_prompt)}chars, "
                  f"sys_prompt={len(system_prompt)}chars, "
                  f"cmd={' '.join(pi_cmd[:4])}...")

        try:
            proc = subprocess.run(
                pi_cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"PI timeout ({timeout}s)",
                "ready_for_escalation": True,
                "timed_out": True,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "PI not installed",
                "ready_for_escalation": True,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ready_for_escalation": True,
            }

        duration = time.monotonic() - start_mono

        if proc.returncode != 0:
            if cleanup_sp:
                try:
                    os.unlink(cleanup_sp)
                except OSError:
                    pass
            # R4: Log PI failure for debug
            self._prompt_flow_logger.log(
                agent=f"{tier}_retry{retry_num}",
                input_text=(
                    f"=== SYSTEM PROMPT ===\n{system_prompt}\n\n"
                    f"=== USER PROMPT ===\n{user_prompt}\n\n"
                    f"=== PI COMMAND ===\n{' '.join(pi_cmd)}"
                ),
                output_text=(
                    f"exit_code={proc.returncode}\n"
                    f"stderr={proc.stderr[:2000] if proc.stderr else '(none)'}\n"
                    f"stdout={proc.stdout[:2000] if proc.stdout else '(empty)'}"
                ),
            )
            return {
                "success": False,
                "error": proc.stderr[:500] if proc.stderr else f"exit {proc.returncode}",
                "exit_code": proc.returncode,
                "ready_for_escalation": True,
                "duration_seconds": duration,
            }

        # Parse JSONL — extract agent_end + tool calls
        output_parts = []
        tool_results = []
        written_paths = []

        for line in proc.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event = _json.loads(line)
            except Exception:
                continue

            etype = event.get("type", "")

            # PI wraps tool calls inside message_update → assistantMessageEvent
            if etype == "message_update":
                inner = event.get("assistantMessageEvent", {})
                inner_type = inner.get("type", "")
                if inner_type in ("toolcall_end", "toolCall"):
                    tc = inner.get("toolCall", {})
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    if name in ("write", "write_file", "Write"):
                        path = args.get("file_path") or args.get("path") or args.get("filePath") or ""
                        content_val = args.get("content", "")
                        if path and content_val:
                            try:
                                # R2: Block writes to protected files (configs, secrets, .git)
                                is_protected, matched = self._is_protected_file(path)
                                if is_protected:
                                    print(f"  ⛔ PROTECTED FILE blocked: {path} "
                                          f"(matches '{matched}')")
                                    tool_results.append({
                                        "tool": name, "args": args,
                                        "protected_block": True, "pattern": matched,
                                    })
                                else:
                                    # R3: Sandbox check — confine writes to project_root
                                    safe_path, sandbox_err = (
                                        self._resolve_sandboxed_path(path, project_root)
                                    )
                                    if sandbox_err:
                                        print(f"  ⛔ SANDBOX blocked: {sandbox_err}")
                                        tool_results.append({
                                            "tool": name, "args": args,
                                            "sandbox_block": True,
                                        })
                                    else:
                                        self.file_tools.file_write(
                                            safe_path or path, content_val
                                        )
                                        written_paths.append(safe_path or path)
                            except Exception:
                                pass
                    tool_results.append({"tool": name, "args": args})

            elif etype == "agent_end":
                msg = event.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        c.get("text", "") for c in content if c.get("type") == "text"
                    )
                if content:
                    output_parts.append(str(content))

            # Also handle direct toolCall events (legacy format)
            elif etype == "toolCall":
                name = event.get("name", "")
                args = event.get("arguments", {})
                if name in ("write", "write_file", "Write"):
                    path = args.get("file_path") or args.get("path") or args.get("filePath") or ""
                    content_val = args.get("content", "")
                    if path and content_val:
                        try:
                            # R2: Block writes to protected files
                            is_protected, matched = self._is_protected_file(path)
                            if is_protected:
                                print(f"  ⛔ PROTECTED FILE blocked: {path} "
                                      f"(matches '{matched}')")
                                tool_results.append({
                                    "tool": name, "args": args,
                                    "protected_block": True, "pattern": matched,
                                })
                            else:
                                # R3: Sandbox check
                                safe_path, sandbox_err = (
                                    self._resolve_sandboxed_path(path, project_root)
                                )
                                if sandbox_err:
                                    print(f"  ⛔ SANDBOX blocked: {sandbox_err}")
                                    tool_results.append({
                                        "tool": name, "args": args,
                                        "sandbox_block": True,
                                    })
                                else:
                                    self.file_tools.file_write(
                                        safe_path or path, content_val
                                    )
                                    written_paths.append(safe_path or path)
                        except Exception:
                            pass
                tool_results.append({"tool": name, "args": args})

        # R4: Dump PI input/output to debug dir when prompt flow logging is
        # enabled (auto-enabled on first rejection, or manually via env var).
        self._prompt_flow_logger.log(
            agent=f"{tier}_retry{retry_num}",
            input_text=(
                f"=== SYSTEM PROMPT ===\n{system_prompt}\n\n"
                f"=== USER PROMPT ===\n{user_prompt}\n\n"
                f"=== PI COMMAND ===\n{' '.join(pi_cmd)}"
            ),
            output_text=proc.stdout if proc.stdout else "(empty stdout)",
        )

        output = "\n".join(output_parts).strip()
        if not output:
            # PI may have written files via tool calls without leaving a final
            # text summary — that's valid output, not an error.
            # Salvage: accept written files rather than discarding all work.
            if written_paths:
                print(f"  Truncation detected — salvaged {len(written_paths)} files: "
                      f"{', '.join(written_paths[:5])}"
                      f"{'...' if len(written_paths) > 5 else ''}")
                output = f"[Truncated — {len(written_paths)} files salvaged: {', '.join(written_paths)}]"
                if cleanup_sp:
                    try:
                        os.unlink(cleanup_sp)
                    except OSError:
                        pass
                return {
                    "success": True,
                    "output": output,
                    "attempt": retry_num,
                    "duration_seconds": duration,
                    "written_paths": written_paths,
                    "partial": True,  # Flag for caller: more files may remain
                    "ready_for_escalation": False,
                }
            else:
                if cleanup_sp:
                    try:
                        os.unlink(cleanup_sp)
                    except OSError:
                        pass
                return {
                    "success": False,
                    "error": "Empty output from PI",
                    "stderr": proc.stderr[:500] if proc.stderr else "",
                    "written_paths": written_paths,
                    "ready_for_escalation": True,
                    "duration_seconds": duration,
                }

        if cleanup_sp:
            try:
                os.unlink(cleanup_sp)
            except OSError:
                pass
        return {
            "success": True,
            "output": output,
            "attempt": retry_num,
            "duration_seconds": duration,
            "written_paths": written_paths,
            "tool_results": tool_results,
        }

    def _execute_opencode_tier(
        self,
        tier: str,
        user_prompt: str,
        system_prompt: str = "",
        retry_num: int = 1,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Execute a coder tier through OpenCode CLI (opencode run).

        OpenCode is the default coder sub-agent. It handles file writes,
        bash execution, and multi-file tasks with native tool use. After
        OpenCode exits, the orchestrator scans the project_root for files
        written and feeds them to the Judge.

        Args:
            tier: Tier key (l0-coder, l1-coder, l2-coder).
            user_prompt: The task specification / user message.
            system_prompt: Quality directives prepended to the prompt.
            retry_num: Which retry attempt this is (for logging).
            project_root: Working directory for OpenCode — file paths in
                the task spec are relative to this directory. If None, uses
                the orchestrator's CWD (typically the MR-Krabs repo).

        Returns:
            Dict matching call_llm_with_retry() shape:
            {success, output, attempt, duration_seconds, written_paths, ...}
        """
        model_spec = self.opencode_models.get(tier.lower())
        if not model_spec:
            return {
                "success": False,
                "error": f"No OpenCode model for tier {tier}",
                "ready_for_escalation": True,
            }

        timeout = self.opencode_timeouts.get(tier.lower(), 600)
        workdir = project_root or str(self.project_root)
        workdir_path = Path(workdir)

        # Combine system prompt with user prompt
        full_prompt = user_prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # ── Attach coding rules via -f (survives auto-compaction) ────
        rules_content = self._get_opencode_rules()
        rules_path = None
        if rules_content:
            import tempfile
            rules_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", prefix="mrkrabs_opencode_rules_",
                delete=False,
            )
            rules_file.write(rules_content)
            rules_file.close()
            rules_path = rules_file.name

        # Snapshot files before execution to discover writes
        before_files: set[str] = set()
        if workdir_path.exists():
            for f in workdir_path.rglob("*"):
                if f.is_file() and ".git" not in f.parts:
                    before_files.add(str(f))

        start_time = time.time()  # wall clock for os.path.getmtime() comparison
        start_mono = time.monotonic()  # monotonic for duration calculation

        # L1/L2 diagnostic: log model + prompt size for cloud tier debugging
        if tier.lower().startswith("l1") or tier.lower().startswith("l2"):
            print(f"  [DIAG] {tier} r{retry_num}: opencode model={model_spec}, "
                  f"prompt={len(full_prompt)}chars, "
                  f"timeout={timeout}s, workdir={workdir}")

        # Build OpenCode command — prompt first, then -f (array flag consumes next arg)
        oc_cmd = ["opencode", "run", "--model", model_spec,
                   "--dangerously-skip-permissions", full_prompt]
        if rules_path:
            oc_cmd.extend(["-f", rules_path])

        try:
            # OpenCode ignores subprocess.run(cwd=...) — must cd into
            # the workdir before invoking. Use shell to chain commands.
            cd_cmd = f"cd {shlex.quote(workdir)} && {' '.join(shlex.quote(a) for a in oc_cmd)}"
            proc = subprocess.run(
                cd_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            if rules_path:
                try: os.unlink(rules_path)
                except OSError: pass
            return {
                "success": False,
                "error": f"OpenCode timeout ({timeout}s)",
                "ready_for_escalation": True,
                "timed_out": True,
            }
        except FileNotFoundError:
            if rules_path:
                try: os.unlink(rules_path)
                except OSError: pass
            return {
                "success": False,
                "error": "OpenCode not installed",
                "ready_for_escalation": True,
            }
        except Exception as e:
            if rules_path:
                try: os.unlink(rules_path)
                except OSError: pass
            return {
                "success": False,
                "error": str(e),
                "ready_for_escalation": True,
            }

        duration = time.monotonic() - start_mono

        # Clean up temp rules file
        if rules_path:
            try:
                os.unlink(rules_path)
            except OSError:
                pass

        # Discover written files (new + modified since snapshot)
        written_paths: list[str] = []
        after_files: set[str] = set()
        if workdir_path.exists():
            for f in workdir_path.rglob("*"):
                if f.is_file() and ".git" not in f.parts:
                    fp = str(f)
                    after_files.add(fp)
                    if fp not in before_files:
                        written_paths.append(fp)
                    else:
                        # File existed before — check if modified during run
                        try:
                            mtime = os.path.getmtime(fp)
                            if mtime > start_time:
                                written_paths.append(fp)
                        except OSError:
                            pass

        output = (proc.stderr or proc.stdout or "").strip()
        # OpenCode writes TUI/text to stderr by default; stdout may be empty.

        # R4: Dump OpenCode input/output to debug dir
        self._prompt_flow_logger.log(
            agent=f"{tier}_retry{retry_num}",
            input_text=(
                f"=== SYSTEM + USER PROMPT ===\n{full_prompt}\n\n"
                f"=== OPENCODE COMMAND ===\n{' '.join(oc_cmd[:4])}..."
            ),
            output_text=proc.stderr or proc.stdout or "(empty)",
        )

        if proc.returncode != 0:
            # Salvage any files written before failure
            if written_paths:
                print(f"  OpenCode exit {proc.returncode} — salvaged "
                      f"{len(written_paths)} files")
                return {
                    "success": True,
                    "output": (
                        output
                        or f"[OpenCode exit {proc.returncode} — "
                        f"{len(written_paths)} files salvaged]"
                    ),
                    "attempt": retry_num,
                    "duration_seconds": duration,
                    "written_paths": written_paths,
                    "partial": True,
                    "ready_for_escalation": False,
                }
            return {
                "success": False,
                "error": proc.stderr[:500] if proc.stderr else f"exit {proc.returncode}",
                "exit_code": proc.returncode,
                "ready_for_escalation": True,
                "duration_seconds": duration,
            }

        # Empty output but files were written — synthetic summary
        if not output and written_paths:
            print(f"  OpenCode wrote {len(written_paths)} files (no text output)")
            output = f"[OpenCode wrote {len(written_paths)} files: "
            output += ", ".join(
                str(Path(p).relative_to(workdir_path)) for p in written_paths[:10]
            )
            if len(written_paths) > 10:
                output += f" ... and {len(written_paths) - 10} more"
            output += "]"

        return {
            "success": True,
            "output": output,
            "attempt": retry_num,
            "duration_seconds": duration,
            "written_paths": written_paths,
        }

    # ── User prompt builder ─────────────────────────────────────────────

    def _build_user_prompt(self, task_id: str, tier: str, context: dict, template: str) -> str:
        """Build user prompt from template and context."""
        user_prompt = template
        if "task_spec" in context:
            user_prompt = user_prompt.replace(
                "{INSERT: Full task specification from Mid-Tier Planner}",
                context.get("task_spec", ""),
            )
        if "existing_context" in context:
            user_prompt = user_prompt.replace(
                "{INSERT: Relevant existing files, interfaces, patterns}",
                context.get("existing_context", "First task - no existing code"),
            )
        if "implementation" in context:
            user_prompt = user_prompt.replace(
                "{INSERT: Coder's implementation + self-assessment}",
                context.get("implementation", ""),
            )
        user_prompt += f"\n\n## Current Task: {task_id}\n\n"
        for key, value in context.items():
            if key not in ["task_spec", "implementation", "existing_context"]:
                user_prompt += f"**{key}:** {value}\n"
        return user_prompt

    def _log_handoff(
        self,
        task_id: str,
        tier: str,
        context: dict,
        response: str,
        timestamp: datetime,
        duration: float,
        attempt: int,
        tool_result: dict,
    ) -> str:
        """Log successful handoff."""
        safe_task_id = task_id.replace(".", "_")
        timestamp_str = timestamp.isoformat().replace(":", "-")
        log_entry = {
            "timestamp": timestamp.isoformat() + "Z",
            "task_id": task_id,
            "tier": tier,
            "attempt": attempt,
            "duration_seconds": duration,
            "success": True,
            "input_context": {k: v for k, v in context.items() if len(str(v)) < 1000},
            "output_preview": response[:500] + "..." if len(response) > 500 else response,
            "tool_results": tool_result,
        }
        log_file = self.handoffs_dir / f"{safe_task_id}-{tier.lower()}-{timestamp_str}.json"
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2)
        return str(log_file)

    def _log_failure(
        self, task_id: str, tier: str, context: dict, error: str, timestamp: datetime, attempts: int
    ) -> str:
        """Log failure for escalation."""
        safe_task_id = task_id.replace(".", "_")
        timestamp_str = timestamp.isoformat().replace(":", "-")
        log_entry = {
            "timestamp": timestamp.isoformat() + "Z",
            "task_id": task_id,
            "tier": tier,
            "attempts": attempts,
            "success": False,
            "error": error,
            "ready_for_escalation": True,
            "context_summary": {k: str(v)[:200] for k, v in context.items()},
        }
        log_file = (
            self.escalations_dir / f"{safe_task_id}-{tier.lower()}-failed-{timestamp_str}.json"
        )
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2)
        return str(log_file)

    def _build_notification_message(
        self, task_id: str, tier: str, cost_summary: dict, verdict, failure_action: "FailureAction"
    ) -> str:
        """Build notification message for escalation."""
        # Safely extract total_cost from cost_summary (handling MagicMock in tests)
        total_cost = 0.0
        if isinstance(cost_summary, dict):
            total_cost = cost_summary.get("total_cost", 0.0)
        elif hasattr(cost_summary, "get"):
            try:
                total_cost = cost_summary.get("total_cost", 0.0)
            except Exception:
                total_cost = 0.0

        message_parts = [
            "\u26a0\ufe0f *Task Escalation Alert* \u26a0\ufe0f",
            f"**Task ID:** {task_id}",
            f"**Tier:** {tier}",
            f"**Spend So Far:** ${total_cost:.4f}",
        ]

        if verdict:
            message_parts.append(f"**Failure Reason:** {verdict.critique}")

        if failure_action == FailureAction.NOTIFY_AND_ESCALATE:
            message_parts.append("**Action Taken:** Escalating to next tier")
        elif failure_action == FailureAction.NOTIFY_AND_WAIT:
            message_parts.append("**Action Taken:** WAITING FOR HUMAN CONFIRMATION")
            message_parts.append(
                f"**Human Action Needed:** Confirm or deny at "
                f"~/.mrkrabs/pending/{task_id}.json"
            )

        return "\\n".join(message_parts)

    def execute_task(
        self,
        task_id: str,
        tier: str,
        context: dict[str, Any],
        timeout_seconds: float | None = None,
        max_task_duration_seconds: int = 300,
    ) -> dict[str, Any]:
        """Execute a task using the specified tier.
        
        Args:
            task_id: Unique task identifier.
            tier: Tier to use (e.g. "L0-Coder").
            context: Task context dict.
            timeout_seconds: Global timeout for the entire escalation loop.
                Default: 300s (5 minutes).
            max_task_duration_seconds: Maximum duration for the entire task execution.
                Default: 300s (5 minutes).
        """
        warnings.warn(
            "execute_task() is deprecated and will be removed in a future version. "
            "Use execute_with_judge() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        from src.core.timeout import TaskTimeout
        with TaskTimeout(max_task_duration_seconds):
            return self.execute_with_judge(
                task_id=task_id,
                context=context,
                tiers=[tier],
                max_retries_per_tier=3,
                timeout_seconds=timeout_seconds or 300.0
            )

    @staticmethod
    def _split_plan_into_tasks(plan_text: str) -> list[str]:
        """Split a plan markdown document into individual coder tasks.

        Looks for headings like '## Task N:', '### Subtask N:', or
        numbered items like '## 1.', '### 1.' followed by task content.
        Each task block becomes a separate subtask for the coder.

        Returns a list of task strings. If no tasks found, returns
        an empty list (caller should fall through to full-text execution).
        """
        import re
        # Match markdown headings that indicate a task boundary:
        #   ## Task 1: Description
        #   ### Subtask 1 — Description
        #   ## 1. Description
        #   ### 1) Description
        task_pattern = re.compile(
            r'^(#{2,4})\s+(?:Task|Subtask|Step)?\s*(\d+)[:.\-\)]\s*(.+)',
            re.MULTILINE | re.IGNORECASE
        )
        matches = list(task_pattern.finditer(plan_text))
        if not matches:
            # Try looser: any numbered heading
            task_pattern = re.compile(
                r'^(#{2,4})\s+(\d+)[:.\-\)]\s+(.+)',
                re.MULTILINE
            )
            matches = list(task_pattern.finditer(plan_text))
        if len(matches) <= 1:
            return []

        tasks = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(plan_text)
            task_block = plan_text[start:end].strip()
            # Extract just the content after the heading line
            heading_end = task_block.index('\n') if '\n' in task_block else len(task_block)
            heading = task_block[:heading_end].strip()
            body = task_block[heading_end:].strip()
            # Combine heading + body into a self-contained task spec
            task_spec = f"{heading}\n{body}" if body else heading
            # Skip empty or near-empty tasks
            if len(task_spec) > 30:
                tasks.append(task_spec)
        return tasks

    def _execute_multi_pass(
        self,
        task_id: str,
        original_spec: str,
        passes: list,
        file_refs: list,
        tiers: list[str],
        max_retries_per_tier: int,
        judge_model: str,
        project_root: str | None,
        timeout_seconds: float = 300,
    ) -> dict[str, Any]:
        """Execute a large task split across multiple sequential PI passes.

        Each pass gets a focused sub-task spec listing only its files.
        Written files accumulate and are excluded from later passes.
        If any pass fails, remaining passes are aborted.
        """
        accumulated_files: list[str] = []
        results = []
        total_attempts = 0
        total_duration = 0.0

        # Use while loop with index — re-split may mutate the passes list
        pass_idx = 0
        while pass_idx < len(passes):
            subtask = passes[pass_idx]
            spec = generate_subtask_spec(
                original_spec, subtask, subtask.pass_num,
                len(passes), accumulated_files,
            )
            sub_id = f"{task_id}-p{subtask.pass_num}"

            print(f"  Pass {subtask.pass_num}/{len(passes)}: "
                  f"{len(subtask.files)} files ["
                  f"{', '.join(f.path for f in subtask.files[:3])}"
                  f"{'...' if len(subtask.files) > 3 else ''}]")

            sub_result = self.execute_with_judge(
                task_id=sub_id,
                context={"task_spec": spec, "_multi_pass_child": True},
                task_type="code",
                tiers=tiers,
                max_retries_per_tier=max_retries_per_tier,
                judge_model=judge_model,
                project_root=project_root,
                timeout_seconds=timeout_seconds,
                plan_first=False,  # Already split
            )

            results.append(sub_result)
            total_attempts += sub_result.get("attempts_total", 0)
            total_duration += sub_result.get("duration_seconds", 0)

            if not sub_result["success"]:
                # ── Adaptive re-split on truncation ──────────────────
                # When context window truncation is detected, halve the
                # per-pass budget and re-split ALL remaining files
                # (including this pass's unwritten files + future passes).
                # This adapts to any model/server without hardcoded estimates.
                if sub_result.get("truncated"):
                    # Collect remaining file refs: unwritten from this pass + all future passes
                    unwritten_this_pass = [
                        f for f in subtask.files
                        if f.path not in accumulated_files
                        and (not sub_result.get("written_paths")
                             or f.path not in sub_result.get("written_paths", []))
                    ]
                    # Salvage any files that WERE written before truncation
                    if sub_result.get("files"):
                        accumulated_files.extend(sub_result["files"].keys())
                    elif sub_result.get("written_paths"):
                        accumulated_files.extend(sub_result["written_paths"])

                    future_refs = [
                        f for p in passes[passes.index(subtask) + 1:]
                        for f in p.files
                    ]
                    all_remaining = unwritten_this_pass + future_refs
                    if all_remaining:
                        new_limit = max(2, len(subtask.files) // 2)  # floor at 2
                        if new_limit >= len(subtask.files):
                            # Re-split wouldn't help — already at floor
                            print(f"  Truncated at floor ({len(subtask.files)}/pass) "
                                  f"— escalating, cannot split further")
                            return {
                                "task_id": task_id, "success": False,
                                "output": f"Pass {subtask.pass_num} truncated at floor",
                                "error": "Context window too small for pass size",
                                "attempts_total": total_attempts,
                                "duration_seconds": total_duration,
                                "pass_results": results,
                            }
                        new_passes = split_into_passes(all_remaining, max_files=new_limit)
                        if new_passes:
                            print(f"  Truncated — re-splitting {len(all_remaining)} "
                                  f"remaining files with limit {new_limit}/pass "
                                  f"(was {len(subtask.files)}/pass)")
                            # Replace future passes with re-split versions
                            for i, ns in enumerate(new_passes):
                                ns.pass_num = subtask.pass_num + i
                            # Truncate the passes list at the failed subtask
                            idx = passes.index(subtask)
                            passes[idx:] = new_passes
                            continue

                # Non-truncation failure — abort remaining passes
                return {
                    "task_id": task_id, "success": False,
                    "output": f"Pass {subtask.pass_num} failed",
                    "error": sub_result.get("error", "unknown"),
                    "attempts_total": total_attempts,
                    "duration_seconds": total_duration,
                    "pass_results": results,
                }

            # Accumulate files written in this pass
            if sub_result.get("files"):
                accumulated_files.extend(sub_result["files"].keys())
            elif sub_result.get("written_paths"):
                accumulated_files.extend(sub_result["written_paths"])

        # Merge pass results
        all_files = {}
        all_outputs = []
        for r in results:
            if r.get("files"):
                all_files.update(r["files"])
            all_outputs.append(r.get("output", ""))

        return {
            "task_id": task_id, "success": True,
            "output": "\n\n".join(all_outputs),
            "files": all_files,
            "tier_used": results[-1].get("tier_used"),
            "attempts_total": total_attempts,
            "duration_seconds": total_duration,
            "pass_count": len(passes),
            "pass_results": results,
        }

    def _run_self_improve_if_enabled(self, task_id: str) -> None:
        """Run self-improvement cycle if MRKRABS_SELF_IMPROVE=1.

        Reads pipeline data, discovers failure patterns, and updates
        model_profiles.py. Never blocks execution — errors are printed
        but not raised.
        """
        if os.environ.get("MRKRABS_SELF_IMPROVE", "") != "1":
            return
        try:
            from src.core.self_improver import SelfImprover
            improver = SelfImprover()
            imp_result = improver.run()
            print(f"[SELF-IMPROVE] Discovered {imp_result.patterns_discovered} "
                  f"patterns across {len(imp_result.models_updated)} models")
            if imp_result.errors:
                for err in imp_result.errors:
                    print(f"[SELF-IMPROVE] Error: {err}")
        except Exception as e:
            print(f"[SELF-IMPROVE] Failed: {e}")

    # ── Checkpoint methods (Gap 3: Crash Recovery) ────────────────────

    def _checkpoint_path(self, task_id: str) -> Path:
        """Path to the checkpoint file for a given task."""
        safe_id = task_id.replace("/", "_").replace(".", "_")
        return self.escalations_dir / f"{safe_id}_checkpoint.json"

    def _write_checkpoint(
        self,
        task_id: str,
        escalation_path: list[str],
        accumulated_files: dict[str, int],
        retries_per_tier: dict[str, int],
        best_output: dict,
        cost_summary: dict,
        attempts_total: int,
        start_time: float,
    ) -> None:
        """Write a checkpoint after a tier completes (accept or reject)."""
        checkpoint = {
            "task_id": task_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "escalation_path": escalation_path,
            "accumulated_files": accumulated_files,
            "retries_per_tier": retries_per_tier,
            "best_output": {
                k: v for k, v in best_output.items()
                if k != "files"  # files are on disk, don't serialize
            },
            "cost_summary": {
                k: str(v) if hasattr(v, '__float__') else v
                for k, v in cost_summary.items()
            },
            "attempts_total": attempts_total,
            "elapsed_seconds": time.monotonic() - start_time,
        }
        self._checkpoint_path(task_id).write_text(
            json.dumps(checkpoint, indent=2, default=str)
        )

    def _load_checkpoint(self, task_id: str) -> dict | None:
        """Load a checkpoint if it exists. Returns None if no checkpoint."""
        path = self._checkpoint_path(task_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _clear_checkpoint(self, task_id: str) -> None:
        """Delete the checkpoint file after successful completion."""
        path = self._checkpoint_path(task_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _categorize_error(verdict) -> str:
        """Categorize a judge verdict into an error category for pattern detection.

        Returns one of: 'empty_output', 'truncation', 'wrong_approach',
        'syntax_error', 'missing_files', 'unknown'.
        """
        if verdict is None:
            return "unknown"

        critique = (verdict.critique or "").lower()
        score = verdict.score if hasattr(verdict, 'score') else 0.0

        if score < 0.1:
            return "empty_output"
        if "truncat" in critique or "incomplete" in critique:
            return "truncation"
        if "syntax" in critique or "indentation" in critique or "parse" in critique:
            return "syntax_error"
        if "missing" in critique and ("file" in critique or "module" in critique):
            return "missing_files"
        if "wrong approach" in critique or "misunderstand" in critique:
            return "wrong_approach"

        return "unknown"

    def execute_with_judge(
        self,
        task_id: str,
        context: dict[str, Any],
        task_type: str = "code",
        tiers: list[str] | None = None,
        max_retries_per_tier: int = 3,
        judge_model: str = "Judge",
        timeout_seconds: float = 300,
        plan_first: bool = False,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Execute a task using Judge-based retry/escalation logic.

        Args:
            task_type: "code" or "plan" — determines which agent system
                prompt template and judge evaluation criteria to use.
            plan_first: If True, run planning first to decompose large tasks,
                then execute each subtask through the coder tiers. The plan
                judge enforces coder_task_size limits (3KB, 5 files, 8 tests).
                Use this for tasks that may exceed PI's single-invocation limits.
            project_root: Working directory for PI subprocess. File paths in
                the task spec resolve relative to this directory. If None,
                uses the orchestrator's CWD (MR-Krabs repo).

        For each tier, calls the LLM up to max_retries_per_tier times.
        After each call, a Judge (LLM-powered) evaluates the output quality.
        If accepted, returns immediately. If rejected, feeds critique back
        as feedback for the next retry. If all retries exhausted, escalates
        to the next tier.

        CostTracker is observer-only -- tracks spend, never blocks.
        CircuitBreaker gates each tier call -- blocked tiers are skipped.

        Returns:
            dict with: task_id, success, output, tier_used, attempts_total,
            retries_per_tier, verdict, cost_summary, escalation_path,
            duration_seconds, tool_results
        """
        # Load the agent system prompt once (used across all tiers and fail-now)
        agent_system_prompt = self._get_agent_system_prompt(task_type)
        pi_system_prompt = self._get_pi_system_prompt(task_type)

        # R4: Keep prompt flow logger pointed at this task so if
        # auto-enabled on failure it writes to the right directory.
        self._prompt_flow_logger.task_id = task_id

        # ── Multi-pass detection ───────────────────────────
        # Dynamically sizes passes based on context window budget.
        # Queries the target LLM server for actual n_ctx, estimates
        # token requirements, and calculates files_per_pass.
        # Falls back to MAX_FILES_PER_PASS if server unreachable.
        #
        # The hardcoded MAX_FILES_PER_PASS is a ceiling — never exceed it.
        # The FLOOR_RATIO (50% of ceiling) is a safety floor — never go below.
        # The actual number comes from: (n_ctx - input_budget) / avg_file_budget.
        task_spec_str = str(context.get("task_spec", ""))
        if (task_type == "code" and task_spec_str
                and not context.get("_multi_pass_child")):
            file_refs = extract_file_refs(task_spec_str)
            if len(file_refs) > 1:  # only split multi-file tasks
                # ── Dynamic budget calculation ─────────────────────
                from src.core.token_budget import (
                    calculate_pass_capacity,
                    resolve_base_url,
                    query_context_window,
                )
                agent_sp = self._get_agent_system_prompt(task_type)
                rules = self._get_opencode_rules()
                tiers_list = tiers or ["l0-coder", "l1-coder", "l2-coder", "principal"]
                n_ctx = context.get("n_ctx_override")  # Principal-provided override
                base_url = None

                # Try to resolve the first tier's server context window
                if not n_ctx:
                    base_url = resolve_base_url(
                        tiers_list[0],
                        self.opencode_models,
                        self.pi_models,
                    )
                    if base_url:
                        n_ctx = query_context_window(base_url)

                if not n_ctx:
                    # Can't determine context window — escalate to Principal Agent.
                    # A hardcoded fallback (50 files) is wrong >90% of the time.
                    # The Principal can cross-reference server configs, /v1/models,
                    # and systemd unit files to provide an accurate n_ctx.
                    principal_context = {
                        "reason": "unknown_context_window",
                        "tier": tiers_list[0],
                        "opencode_model": self.opencode_models.get(
                            tiers_list[0].lower()
                        ),
                        "pi_model": self.pi_models.get(tiers_list[0].lower()),
                        "attempted_base_url": base_url,
                        "task_spec_preview": task_spec_str[:500],
                        "file_count": len(file_refs),
                        "help_text": (
                            "MR-Krabs cannot determine the context window for "
                            f"tier '{tiers_list[0]}' on the target LLM server.\n\n"
                            "To resolve: determine the n_ctx value (check server "
                            "config, /v1/models, systemd unit, or /slots endpoint), "
                            "then re-submit this task with "
                            "context['n_ctx_override'] = <value>."
                        ),
                    }
                    print(f"[PRINCIPAL] Cannot determine context window for "
                          f"tier '{tiers_list[0]}' — escalating to Principal Agent")
                    return {
                        "task_id": task_id,
                        "success": False,
                        "escalated_to_principal": True,
                        "escalation_reason": "unknown_context_window",
                        "tier_used": "Principal",
                        "output": None,
                        "escalation_context": principal_context,
                        "attempts_total": 0,
                        "retries_per_tier": {},
                        "cost_summary": self.cost_tracker.get_summary(),
                        "escalation_path": ["Principal"],
                        "duration_seconds": 0.0,
                        "message": (
                            "Context window could not be determined for "
                            f"tier '{tiers_list[0]}'. Provide "
                            "n_ctx_override in context to continue."
                        ),
                    }

                dynamic_limit = calculate_pass_capacity(
                    spec_text=task_spec_str,
                    system_prompt_text=agent_sp,
                    rules_text=rules,
                    n_ctx=n_ctx,
                    file_refs=file_refs,
                )
                override_tag = " (Principal override)" if context.get(
                    "n_ctx_override"
                ) else ""
                print(f"  Budget: {n_ctx}ctx → {dynamic_limit} files/pass "
                      f"(ceiling={MAX_FILES_PER_PASS}){override_tag}")

                if len(file_refs) > dynamic_limit or plan_first:
                    passes = split_into_passes(file_refs, max_files=dynamic_limit)
                    if len(passes) > 1:
                        print(f"Multi-pass: {len(file_refs)} files → "
                              f"{len(passes)} passes (max {dynamic_limit}/pass)")
                    return self._execute_multi_pass(
                        task_id=task_id,
                        original_spec=task_spec_str,
                        passes=passes,
                        file_refs=file_refs,
                        tiers=tiers,
                        max_retries_per_tier=max_retries_per_tier,
                        judge_model=judge_model,
                        project_root=project_root,
                        timeout_seconds=timeout_seconds,
                    )

        # Check for fail-now signal
        fail_now_tier = get_fail_now()
        if fail_now_tier:
            # Check mesh signal file
            check_mesh_fail_now()
            # Validate the tier exists
            if fail_now_tier not in get_models():
                # Fall through to closest available tier
                available = [t for t in tiers or ["L0-Coder", "L1-Coder", "L2-Coder", "Principal"] if t in get_models()]
                fail_now_tier = available[-1] if available else None
            
            if fail_now_tier:
                tier_config = get_models().get(fail_now_tier, {})
                # One-shot call — no retry, no judge
                result = self.call_llm_with_retry(
                    fail_now_tier, agent_system_prompt, str(context.get("task_spec", task_id)),
                    temperature=tier_config.get("temperature", 0.7),
                    timeout_seconds=timeout_seconds,
                )
                clear_fail_now()  # auto-clear
                
                if result["success"]:
                    return {
                        "task_id": task_id, "success": True,
                        "output": result["output"], "tier_used": fail_now_tier,
                        "attempts_total": 1, "fail_now": True,
                        "cost_summary": self.cost_tracker.get_summary(),
                        "duration_seconds": result.get("duration_seconds", 0),
                        "escalation_path": [fail_now_tier],
                        "retries_per_tier": {fail_now_tier: 1},
                    }
                else:
                    # Fail-now tier failed — try next available tier
                    # (graceful fallthrough, then clear)
                    pass
            
            clear_fail_now()
        
        tiers = tiers or ["L0-Coder", "L1-Coder", "L2-Coder", "Principal"]

        start_time = time.time()  # wall clock for os.path.getmtime() comparison
        start_mono = time.monotonic()  # monotonic for duration calculation
        attempts_total = 0
        retries_per_tier: dict[str, int] = {}
        escalation_path: list[str] = []
        best_output: dict[str, Any] = {}  # best output across all tiers for Principal handoff
        accumulated_files: dict[str, int] = {}  # path → bytes from completed tiers (R1 incremental pass-through)
        verdict = None  # initialized before retry loop; set by judge evaluation

        # ── Consecutive error tracking (Article Pillar 4) ─────────────────
        last_error_category: str | None = None
        consecutive_failures: int = 0
        MAX_CONSECUTIVE_FAILURES = 3
        escalated_by_consecutive_errors: bool = False
        any_truncation: bool = False  # true if any verdict cited truncation

        for tier in tiers:
            feedback = ""
            retries_per_tier[tier] = 0
            fail_up_aborted = False  # track if fail_up triggered this tier

            # Look up tier config (used by Principal check, circuit breaker, and retry loop)
            tier_config = get_models().get(tier, {})

            # --- Principal Agent check ---
            # Principal has no provider/model — it's the user's own agent.
            # When escalation reaches Principal, return full context so the
            # calling agent (Hermes, Claude Code, etc.) can take over.
            if tier_config.get("role") == "principal" or tier_config.get("roles") == ["principal"]:
                principal_context = {
                    "task": context.get("task_spec", task_id),
                    "tiers_attempted": list(escalation_path),
                    "retries_per_tier": dict(retries_per_tier),
                    "last_feedback": feedback,
                    "best_output": best_output,
                    "pipeline_health": self.monitor.check_health(),
                    "recent_actions": [
                        {
                            "role": a.role,
                            "tier": a.tier,
                            "action_type": a.action_type,
                            "anomalies": a.anomaly_flags,
                            "summary": a.summary,
                        }
                        for a in self.monitor.recent_actions(8)
                    ],
                }
                print(f"[PRINCIPAL] Escalating to Principal Agent — "
                      f"MR-Krabs tiers exhausted: {escalation_path}")
                self._run_self_improve_if_enabled(task_id)
                return {
                    "task_id": task_id,
                    "success": False,
                    "escalated_to_principal": True,
                    "tier_used": "Principal",
                    "output": None,
                    "escalation_context": principal_context,
                    "attempts_total": attempts_total,
                    "retries_per_tier": retries_per_tier,
                    "cost_summary": self.cost_tracker.get_summary(),
                    "escalation_path": escalation_path + ["Principal"],
                    "duration_seconds": time.monotonic() - start_mono,
                    "tool_results": None,
                    "truncated": any_truncation,
                    "message": (
                        "Task escalated to Principal Agent. MR-Krabs attempted "
                        f"{len(escalation_path)} tier(s) with {attempts_total} total "
                        "attempts and could not produce accepted output. See "
                        "escalation_context for full details."
                    ),
                }

            # --- Circuit breaker gate ---
            provider = tier_config.get("provider", "")
            model_name = tier_config.get("model", "")
            if provider and model_name:
                cb = self.circuit_breaker_registry.get(provider, model_name)
                if not cb.can_execute():
                    print(f"Skipping tier {tier} due to circuit breaker")
                    escalation_path.append(tier)
                    continue

            # --- FailUp check: abort this tier, bump one level ---
            check_mesh_fail_up()
            if is_fail_up_active():
                print(f"[FAIL_UP] Aborting tier {tier} — bumping up one level")
                clear_fail_up()
                escalation_path.append(tier)
                continue  # skip to next tier

            # --- Retry loop ---
            retry_num = 1
            provisional_bonus = False
            while retry_num <= max_retries_per_tier:
                # --- FailUp mid-retry check ---
                check_mesh_fail_up()
                if is_fail_up_active():
                    print(f"[FAIL_UP] Aborting tier {tier} mid-retry — bumping up one level")
                    clear_fail_up()
                    fail_up_aborted = True
                    retries_per_tier[tier] = retry_num - 1
                    break  # exit retry loop, go to next tier

                # ── Context compression (Article Pillar 2) ───────────────────────────
                # Assemble the prompt with compression: keep task spec verbatim,
                # summarize older judge feedback, compress accumulated files when >5.
                task_spec = str(context.get("task_spec", task_id))

                # Collect feedback history for this tier across retries
                if not hasattr(self, '_feedback_history'):
                    self._feedback_history: dict[str, list[str]] = {}
                tier_fb_key = f"{task_id}:{tier}"
                if tier_fb_key not in self._feedback_history:
                    self._feedback_history[tier_fb_key] = []
                if feedback and feedback not in self._feedback_history[tier_fb_key]:
                    self._feedback_history[tier_fb_key].append(feedback)

                feedback_history = self._feedback_history.get(tier_fb_key, [])

                # Model profile prepend
                model_key = tier_config.get("profile")
                prepend = get_prepend(model_key) if model_key else ""

                # Pass-through: only inject accumulated files on first attempt of a new tier
                acc_files = accumulated_files if retry_num == 1 and accumulated_files else None

                user_prompt = compress_history(
                    task_spec=task_spec,
                    accumulated_files=acc_files,
                    feedback_history=feedback_history,
                    prepend=prepend,
                )

                # ── Context fill observability ─────────────────────────────────────
                fill = estimate_context_fill(task_spec, acc_files, feedback_history)
                self.monitor.record_context_fill(tier, fill)
                if fill > 0.8:
                    print(f"  ⚠️  Context fill: {fill:.0%} — compression active")

                # Route through OpenCode (default), PI (fallback), or raw LLM
                has_opencode = bool(self.opencode_models.get(tier.lower()))
                has_pi = bool(self.pi_models.get(tier.lower()))

                # ── Fix-mode prompt selection (Gap 4) ────────────────────────
                # On retry with feedback, use the fix prompt (targeted, minimal changes).
                # On fresh attempt, use the build prompt.
                if feedback:
                    current_sp = self._get_agent_system_prompt("fix")
                    current_pi_sp = self._get_pi_system_prompt("fix")
                else:
                    current_sp = agent_system_prompt
                    current_pi_sp = pi_system_prompt

                if has_opencode:
                    result = self._execute_opencode_tier(
                        tier,
                        str(user_prompt),
                        system_prompt=current_sp,
                        retry_num=retry_num,
                        project_root=project_root,
                    )
                elif has_pi:
                    result = self._execute_pi_tier(
                        tier,
                        str(user_prompt),
                        system_prompt=current_pi_sp,
                        retry_num=retry_num,
                        project_root=project_root,
                    )
                else:
                    result = self.call_llm_with_retry(
                        tier, agent_system_prompt, str(user_prompt),
                        temperature=tier_config.get("temperature", 0.7),
                        timeout_seconds=timeout_seconds,
                    )

                attempts_total += 1
                retries_per_tier[tier] += 1
                retry_num += 1

                # ── Pipeline monitor: record coder output ──────────
                if has_opencode or has_pi:
                    self.monitor.record_coder_output(
                        tier=tier,
                        attempt=retries_per_tier[tier],
                        output_chars=len(result.get("output", "")),
                        files_written=len(result.get("written_paths", [])),
                        truncated=result.get("partial", False),
                        exit_code=result.get("exit_code"),
                    )

                if not result["success"]:
                    if has_opencode or has_pi:
                        backend = "OpenCode" if has_opencode else "PI"
                        error_msg = result.get('error', 'unknown')
                        stderr_tail = str(result.get('stderr', ''))[-200:] if result.get('stderr') else ''
                        print(f"Tier {tier} {backend} hard failure (attempt {retry_num}/{max_retries_per_tier}): {error_msg}")
                        if result.get("exit_code"):
                            print(f"Tier {tier} {backend} exited {result.get('exit_code', '?')} — {error_msg}")
                        if stderr_tail:
                            print(f"Tier {tier} {backend} stderr tail: {stderr_tail}")
                        # Don't escalate immediately — retry within this tier with coaching
                        # Only unrecoverable failures ({backend} not installed) skip retry
                        is_unrecoverable = error_msg in (
                            "OpenCode not installed", "PI not installed"
                        )
                        if retry_num < max_retries_per_tier and not is_unrecoverable:
                            feedback = (
                                f"{backend} PROCESS FAILURE (attempt {retry_num}): {error_msg}. "
                                "Your previous attempt produced no output or crashed. "
                                "Simplify the task — write fewer files at once, "
                                "reduce individual file sizes, or split into smaller sub-tasks. "
                                "Try again with a simpler approach."
                            )
                            continue  # retry within same tier
                        # Exhausted retries or unrecoverable — break to post-loop failure handler
                        break
                    else:
                        print(f"Tier {tier} HTTP failure: {result.get('error', 'unknown')}")
                        break

                # --- Tool execution ---
                if (has_opencode or has_pi) and "written_paths" in result:
                    # OpenCode/PI wrote files — read them back for judge evaluation
                    coder_paths = result.get("written_paths", [])
                    tool_result = {"results": [], "tools_executed": len(coder_paths), "all_succeeded": True}
                    for p in coder_paths:
                        try:
                            content = self.file_tools.file_read(p)
                            bytelen = len(content.get("content", ""))
                            tool_result["results"].append({
                                "tool": "file_write", "path": p,
                                "success": content.get("success", False),
                                "content": content.get("content", ""),
                                "bytes": bytelen,
                            })
                            # R1: track in accumulated_files for next tier's handoff
                            accumulated_files[p] = bytelen
                        except Exception:
                            tool_result["results"].append({"tool": "file_write", "path": p, "success": False})
                else:
                    tool_result = self.tool_executor.parse_and_execute_tools(result["output"])

                # --- Judge evaluation ---
                try:
                    task_text = context.get("task_spec", task_id)
                    # For plan tasks, prepend a planning indicator so detect_task_type
                    # correctly routes to PLAN_CRITERIA instead of CODE_CRITERIA
                    if task_type == "plan":
                        task_text = f"[PLANNING TASK] Decompose into subtasks: {task_text}"
                    
                    # Build evaluation output: include tool execution results
                    eval_output = result["output"]
                    if tool_result.get("results"):
                        import json as _json
                        eval_output += "\n\n## Tool Execution Results\n" + _json.dumps(tool_result["results"], indent=2)
                    
                    judge = Judge(model=judge_model)
                    eval_kwargs = {
                        "task": str(task_text),
                        "output": eval_output,
                    }
                    profile_key = tier_config.get("profile")
                    if profile_key:
                        eval_kwargs["model_profile_key"] = profile_key
                    task_spec_dict = context.get("spec")
                    if task_spec_dict:
                        eval_kwargs["spec"] = task_spec_dict
                    verdict = judge.evaluate(**eval_kwargs)
                except Exception as e:
                    # Judge unavailable — degrade gracefully, treat as rejection
                    verdict = Verdict(
                        accepted=False, provisional=False, score=0.0,
                        critique=f"Judge unavailable: {e}",
                        checks_passed=[], checks_failed=["judge_unavailable"],
                    )

                # ── Pipeline monitor: record judge verdict ─────────
                self.monitor.record_judge_verdict(
                    tier=tier,
                    attempt=retries_per_tier[tier],
                    score=verdict.score,
                    accepted=verdict.accepted,
                    provisional=verdict.provisional,
                )

                # ── Pipeline monitor: self-interrogation ───────────
                health = self.monitor.check_health()
                if health.severity.name in ("WARN", "ERROR"):
                    print(f"[MONITOR] {health.assessment}")
                    for rec in health.recommendations:
                        print(f"  → {rec}")
                if health.escalate_to_principal:
                    print(f"[MONITOR] ⛔ Pipeline health critical — "
                          f"escalating to Principal with diagnostics")
                    # Anomalies are surfaced in the Principal context

                # --- Cost tracking (observer only, never blocks) ---
                try:
                    from src.core.cost import TokenCount
                    tier_mod = model_name
                    tokens = TokenCount(
                        prompt_tokens=len(str(user_prompt)) // 4,
                        completion_tokens=len(result.get("output", "")) // 4,
                    )
                    self.cost_tracker.record(
                        task_id, tier, tier_mod, tokens,
                        result.get("duration_seconds", 0.0),
                    )
                except Exception:
                    pass  # cost tracking failure should never block execution

                # ── Checkpoint after every tier verdict ──────────────────────────
                self._write_checkpoint(
                    task_id=task_id,
                    escalation_path=escalation_path + [tier],
                    accumulated_files=accumulated_files,
                    retries_per_tier=retries_per_tier,
                    best_output=best_output,
                    cost_summary=self.cost_tracker.get_summary(),
                    attempts_total=attempts_total,
                    start_time=start_time,
                )

                # --- Verdict ---
                if verdict.accepted:
                    # Collect file contents for result
                    files = {}
                    for tr in tool_result.get("results", []):
                        if tr.get("success") and "content" in tr:
                            files[tr["path"]] = tr["content"]
                    
                    best_output = {
                        "tier": tier, "score": verdict.score,
                        "output": result["output"], "files": files,
                    }

                    duration_seconds = time.monotonic() - start_mono
                    self._clear_checkpoint(task_id)
                    self._run_self_improve_if_enabled(task_id)
                    return {
                        "task_id": task_id,
                        "success": True,
                        "output": result["output"],
                        "score": verdict.score,
                        "files": files,
                        "tier_used": tier,
                        "attempts_total": attempts_total,
                        "retries_per_tier": retries_per_tier,
                        "verdict": verdict,
                        "cost_summary": self.cost_tracker.get_summary(),
                        "escalation_path": escalation_path + [tier],
                        "duration_seconds": duration_seconds,
                        "tool_results": tool_result,
                    }

                if verdict.provisional:
                    # Provisional — grant one bonus retry for targeted fixes
                    if not provisional_bonus:
                        provisional_bonus = True
                        max_retries_per_tier += 1  # bonus round for polish
                    print(f"Tier {tier} provisional: {verdict.critique[:200]}")
                    feedback = (
                        "PROVISIONALLY ACCEPTED. Your code is substantially correct. "
                        "Apply ONLY these targeted corrections — do NOT rewrite working code:\n\n"
                        + verdict.critique
                    )
                    retry_num += 1
                    continue

                # Rejected — save feedback for next retry
                feedback = verdict.critique
                print(f"Tier {tier} retry {retry_num} rejected: {verdict.critique[:200]}")

                # R4: Auto-enable prompt flow debug on first rejection
                # so the user gets diagnostic dumps without manual env-var setup.
                if not self._prompt_flow_logger.enabled:
                    self._prompt_flow_logger.enabled = True
                    self._prompt_flow_logger.task_id = task_id
                    print(f"Prompt flow debug auto-enabled → "
                          f"~/.mrkrabs/debug/{task_id}/")

            # All retries exhausted for this tier (or fail_up aborted)
            # ── Clean up per-tier feedback history ──────────────────────
            tier_fb_key = f"{task_id}:{tier}"
            if hasattr(self, '_feedback_history'):
                self._feedback_history.pop(tier_fb_key, None)

            # ── Consecutive error tracking ──────────────────────────────────
            error_category = self._categorize_error(verdict)
            if error_category == "truncation":
                any_truncation = True
            if error_category == last_error_category:
                consecutive_failures += 1
            else:
                last_error_category = error_category
                consecutive_failures = 1

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"[CONSECUTIVE] {consecutive_failures} consecutive tier "
                      f"failures with '{error_category}' — skipping remaining "
                      f"tiers → Principal")
                escalation_path.append(tier)
                escalated_by_consecutive_errors = True
                break  # exit tier loop, fall through to Principal escalation

            if fail_up_aborted:
                # FailUp aborted intentionally — skip failure actions
                escalation_path.append(tier)
                continue  # move to next tier

            # Normal retry exhaustion — run failure action NOW (per-tier)
            escalation_path.append(tier)

            # ── Pipeline monitor: record escalation ─────────────
            next_tier_idx = tiers.index(tier) + 1 if tier in tiers else len(tiers)
            next_tier = tiers[next_tier_idx] if next_tier_idx < len(tiers) else "Principal"
            self.monitor.record_escalation(
                from_tier=tier,
                to_tier=next_tier,
                reason=f"All {retries_per_tier[tier]} retries exhausted",
            )

            failure_action = get_tier_failure_action(tier)

            if failure_action == FailureAction.LOG_ONLY:
                # Just log and continue to next tier
                print(f"Tier {tier} failed (log_only).")
                continue

            elif failure_action == FailureAction.NOTIFY_AND_ESCALATE:
                # Log spend, log failure, send notification, then continue to next tier
                print(f"[ESCALATE] Tier {tier} failed. Spend: ${self.cost_tracker.get_summary()}")
                self.notifier.send(
                    message=self._build_notification_message(
                        task_id, tier, self.cost_tracker.get_summary(), verdict, failure_action
                    ),
                    urgency="normal",
                    context={"task_id": task_id, "tier": tier}
                )

            elif failure_action == FailureAction.NOTIFY_AND_WAIT:
                # Write pending file, wait for human, send notification
                from src.core.human_gate import write_pending_file, wait_for_human

                write_pending_file(task_id, {
                    "tier": tier,
                    "attempts": retries_per_tier[tier],
                    "cost_summary": self.cost_tracker.get_summary(),
                    "verdict": verdict,  # last verdict
                })

                self.notifier.send(
                    message=self._build_notification_message(
                        task_id, tier, self.cost_tracker.get_summary(), verdict, failure_action
                    ),
                    urgency="high",
                    context={"task_id": task_id, "tier": tier}
                )

                confirmed, reason = wait_for_human(task_id)
                if not confirmed:
                    # Abort — stop entire escalation
                    duration_seconds = time.monotonic() - start_mono
                    return {
                        "task_id": task_id,
                        "success": False,
                        "output": None,
                        "tier_used": None,
                        "attempts_total": attempts_total,
                        "retries_per_tier": retries_per_tier,
                        "verdict": verdict,
                        "cost_summary": self.cost_tracker.get_summary(),
                        "escalation_path": escalation_path,
                        "duration_seconds": duration_seconds,
                        "tool_results": None,
                        "reason": reason,
                    }
                # Confirmed — continue to next tier

        # All tiers exhausted — total failure
        self._run_self_improve_if_enabled(task_id)
        return {
            "task_id": task_id,
            "success": False,
            "output": None,
            "tier_used": "Principal" if escalated_by_consecutive_errors else None,
            "escalated_to_principal": True if escalated_by_consecutive_errors else None,
            "attempts_total": attempts_total,
            "retries_per_tier": retries_per_tier,
            "verdict": None,
            "cost_summary": self.cost_tracker.get_summary(),
            "escalation_path": escalation_path,
            "duration_seconds": time.monotonic() - start_mono,
            "tool_results": None,
            "truncated": any_truncation,
            "pipeline_health": self.monitor.check_health(),
        }
