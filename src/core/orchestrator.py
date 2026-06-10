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

# Prompt flow debug logger (opt-in via MRKRABS_PROMPT_FLOW_DEBUG=1)
from src.core.prompt_flow_logger import PromptFlowLogger

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

        # PI coder backend — maps tier names to PI model specs from config.yaml
        try:
            from src.core.config_loader import load_config
            cfg = load_config()
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
            self.pi_models = {}
            self.pi_timeouts = {}
            self.workflows = {}
            self.protected_file_patterns = []

        # Prompt flow debug logger (no-op when disabled)
        debug_enabled = os.environ.get("MRKRABS_PROMPT_FLOW_DEBUG", "") == "1"
        self._prompt_flow_logger = PromptFlowLogger(
            task_id="__init__", enabled=debug_enabled
        )

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
        start_time = time.monotonic()
        effective_timeout = timeout_seconds or 300.0

        for attempt in range(MAX_RETRIES):
            elapsed = time.monotonic() - start_time
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
            "Write complete, production-quality code using standard library functions.\n"
            "Use open(), pathlib, and stdlib — do NOT reference tool functions.\n"
            "Read before writing, match existing conventions, handle edge cases.\n"
            "If ambiguous, ask. Verify your changes work.\n"
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

        start_time = time.monotonic()
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

        duration = time.monotonic() - start_time

        if proc.returncode != 0:
            if cleanup_sp:
                try:
                    os.unlink(cleanup_sp)
                except OSError:
                    pass
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

        output = "\n".join(output_parts).strip()
        if not output:
            # PI may have written files via tool calls without leaving a final
            # text summary — that's valid output, not an error.
            if written_paths:
                output = f"[Files written: {', '.join(written_paths)}]"
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

        # ── Pre-flight planning (plan_first) ───────────────────────────
        # B2/R5: Auto-trigger planner for oversized tasks.
        # PI's write tool has a content cap — tasks >3KB reliably cause
        # truncation or empty output at L0. Decompose automatically.
        if not plan_first and task_type == "code":
            task_spec_str = str(context.get("task_spec", ""))
            if len(task_spec_str) > 3000:
                print(f"Task size ({len(task_spec_str)} chars) exceeds L0 "
                      f"threshold (3000) — auto-enabling planner")
                plan_first = True

        if plan_first and task_type == "code":
            plan_wf = self.workflows.get("plan")
            plan_tiers = plan_wf.tiers if plan_wf else ["l0-planner", "principal"]
            plan_judge = plan_wf.judge_model if plan_wf else judge_model
            plan_retries = plan_wf.max_retries_per_tier if plan_wf else max_retries_per_tier
            plan_task = f"Decompose into subtasks: {str(context.get('task_spec', task_id))}"
            plan_context = {"task_spec": plan_task}
            print(f"Plan-first: decomposing task with {plan_tiers[0]} (judge={plan_judge})")
            plan_result = self.execute_with_judge(
                task_id=f"{task_id}-plan",
                context=plan_context,
                task_type="plan",
                tiers=plan_tiers,
                max_retries_per_tier=plan_retries,
                judge_model=plan_judge,
                project_root=project_root,
            )
            if not plan_result["success"]:
                return {
                    "task_id": task_id, "success": False,
                    "output": plan_result.get("output", ""),
                    "error": f"Plan decomposition failed: {plan_result.get('verdict', {}).get('critique', 'unknown')}",
                    "attempts_total": plan_result.get("attempts_total", 0),
                    "duration_seconds": plan_result.get("duration_seconds", 0),
                    "escalation_path": ["plan-failed"],
                }
            plan_tasks = self._split_plan_into_tasks(plan_result["output"])
            if plan_tasks and len(plan_tasks) > 1:
                print(f"Plan-first: executing {len(plan_tasks)} subtasks")
                results = []
                total_attempts = plan_result.get("attempts_total", 0)
                total_duration = plan_result.get("duration_seconds", 0)
                for i, subtask in enumerate(plan_tasks):
                    sub_id = f"{task_id}-sub{i+1}"
                    sub_context = {"task_spec": subtask}
                    print(f"  Subtask {i+1}/{len(plan_tasks)}: {subtask[:80]}...")
                    sub_result = self.execute_with_judge(
                        task_id=sub_id,
                        context=sub_context,
                        task_type="code",
                        tiers=tiers,
                        max_retries_per_tier=max_retries_per_tier,
                        judge_model=judge_model,
                        project_root=project_root,
                    )
                    results.append(sub_result)
                    total_attempts += sub_result.get("attempts_total", 0)
                    total_duration += sub_result.get("duration_seconds", 0)
                    if not sub_result["success"]:
                        return {
                            "task_id": task_id, "success": False,
                            "output": f"Subtask {i+1} failed: {sub_result.get('output', '')}",
                            "error": f"Subtask {i+1}/{len(plan_tasks)} failed",
                            "attempts_total": total_attempts,
                            "duration_seconds": total_duration,
                            "escalation_path": [f"subtask-{i+1}-failed"],
                            "subtask_results": results,
                        }
                combined_output = "\n\n".join(
                    f"--- Subtask {i+1} ---\n{r.get('output', '')}"
                    for i, r in enumerate(results)
                )
                return {
                    "task_id": task_id, "success": True,
                    "output": combined_output,
                    "tier_used": "planned-decomposition",
                    "attempts_total": total_attempts,
                    "duration_seconds": total_duration,
                    "escalation_path": ["planned-decomposition"],
                    "subtask_count": len(plan_tasks),
                    "subtask_results": results,
                }
            # If plan produced a single task, fall through to normal code execution
            # with the plan as coaching context
            if plan_tasks:
                context["task_spec"] = plan_tasks[0]
            print("Plan-first: single task — falling through to normal code execution")

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

        start_time = time.monotonic()
        attempts_total = 0
        retries_per_tier: dict[str, int] = {}
        escalation_path: list[str] = []
        best_output: dict[str, Any] = {}  # best output across all tiers for Principal handoff
        accumulated_files: dict[str, int] = {}  # path → bytes from completed tiers (R1 incremental pass-through)
        verdict = None  # initialized before retry loop; set by judge evaluation

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
                }
                print(f"[PRINCIPAL] Escalating to Principal Agent — "
                      f"MR-Krabs tiers exhausted: {escalation_path}")
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
                    "duration_seconds": time.monotonic() - start_time,
                    "tool_results": None,
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
            for retry_num in range(1, max_retries_per_tier + 1):
                # --- FailUp mid-retry check ---
                check_mesh_fail_up()
                if is_fail_up_active():
                    print(f"[FAIL_UP] Aborting tier {tier} mid-retry — bumping up one level")
                    clear_fail_up()
                    fail_up_aborted = True
                    retries_per_tier[tier] = retry_num - 1
                    break  # exit retry loop, go to next tier

                user_prompt = context.get("task_spec", task_id)

                # ── R1: Incremental pass-through ──────────────────────
                # On the first attempt of a new tier (not a retry within
                # the same tier), inject the list of files already
                # completed by previous tiers so the coder doesn't
                # rewrite them.
                if retry_num == 1 and accumulated_files:
                    done_list = "\n".join(
                        f"- {p} ({b} bytes) — COMPLETED, DO NOT REWRITE"
                        for p, b in sorted(accumulated_files.items())
                    )
                    user_prompt = (
                        f"## Files Already Completed by Previous Tiers\n\n"
                        f"The following files have already been written correctly. "
                        f"DO NOT modify or rewrite them. Focus ONLY on files "
                        f"NOT listed here.\n\n{done_list}\n\n"
                        f"## Task\n\n{user_prompt}"
                    )

                # ── Model profile: inject prepend prompt ──────────────
                model_key = tier_config.get("profile")
                if model_key:
                    prepend = get_prepend(model_key)
                    if prepend:
                        user_prompt = f"{prepend}\n\n{user_prompt}"

                if feedback:
                    user_prompt = (
                        f"{user_prompt}\n\n## Previous Attempt Feedback\n\n"
                        f"The prior output was rejected by the quality judge.\n"
                        f"Critique: {feedback}\n\nPlease fix these issues and try again."
                    )

                # Route through PI if this tier has a PI model mapping
                if self.pi_models.get(tier.lower()):
                    result = self._execute_pi_tier(
                        tier,
                        str(user_prompt),
                        system_prompt=pi_system_prompt,
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

                if not result["success"]:
                    if self.pi_models.get(tier.lower()):
                        error_msg = result.get('error', 'unknown')
                        stderr_tail = str(result.get('stderr', ''))[-200:] if result.get('stderr') else ''
                        print(f"Tier {tier} PI hard failure (attempt {retry_num}/{max_retries_per_tier}): {error_msg}")
                        if result.get("exit_code"):
                            print(f"Tier {tier} PI exited {result.get('exit_code', '?')} — {error_msg}")
                        if stderr_tail:
                            print(f"Tier {tier} PI stderr tail: {stderr_tail}")
                        # Don't escalate immediately — retry within this tier with coaching
                        # Only unrecoverable failures (PI not installed) skip retry
                        if retry_num < max_retries_per_tier and error_msg != "PI not installed":
                            feedback = (
                                f"PI PROCESS FAILURE (attempt {retry_num}): {error_msg}. "
                                "Your previous attempt produced no output or crashed. "
                                "Simplify the task — write fewer files at once, "
                                "reduce individual file sizes, or split into smaller sub-tasks. "
                                "Try again with a simpler approach."
                            )
                            continue  # retry within same tier
                        # Exhausted retries or unrecoverable — fall through to next tier
                    else:
                        print(f"Tier {tier} HTTP failure: {result.get('error', 'unknown')}")
                        break

                # --- Tool execution ---
                if self.pi_models.get(tier.lower()) and "written_paths" in result:
                    # PI wrote files — read them back for judge evaluation
                    pi_paths = result.get("written_paths", [])
                    tool_result = {"results": [], "tools_executed": len(pi_paths), "all_succeeded": True}
                    for p in pi_paths:
                        try:
                            content = self.file_tools.file_read(p)
                            bytelen = len(content.get("content", ""))
                            tool_result["results"].append({
                                "tool": "file_write", "path": p,
                                "success": content.get("success", False),
                                "content": content.get("content", "")[:2000],
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
                    verdict = judge.evaluate(**eval_kwargs)
                except Exception as e:
                    # Judge unavailable — degrade gracefully, treat as rejection
                    verdict = Verdict(
                        accepted=False, provisional=False, score=0.0,
                        critique=f"Judge unavailable: {e}",
                        checks_passed=[], checks_failed=["judge_unavailable"],
                    )

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
                    
                    duration_seconds = time.monotonic() - start_time
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
                    # Provisionally accepted — coder makes targeted corrections
                    # and returns for one final evaluation. Don't count against
                    # retry budget — this is a polish pass, not a rewrite.
                    print(f"Tier {tier} provisional: {verdict.critique[:200]}")
                    feedback = (
                        "PROVISIONALLY ACCEPTED. Your code is substantially correct. "
                        "Apply ONLY these targeted corrections — do NOT rewrite working code:\n\n"
                        + verdict.critique
                    )
                    # Don't decrement retries_per_tier — provisional is a free revision
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
            if fail_up_aborted:
                # FailUp aborted intentionally — skip failure actions
                escalation_path.append(tier)
                continue  # move to next tier

            # Normal retry exhaustion — run failure action NOW (per-tier)
            escalation_path.append(tier)
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
                    duration_seconds = time.monotonic() - start_time
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
        return {
            "task_id": task_id,
            "success": False,
            "output": None,
            "tier_used": None,
            "attempts_total": attempts_total,
            "retries_per_tier": retries_per_tier,
            "verdict": None,
            "cost_summary": self.cost_tracker.get_summary(),
            "escalation_path": escalation_path,
            "duration_seconds": time.monotonic() - start_time,
            "tool_results": None,
        }
