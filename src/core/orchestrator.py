#!/usr/bin/env python3
"""Multi-Tier LLM Orchestrator - Core Implementation"""

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import warnings

from src.core.circuit_breaker import CircuitBreakerRegistry
from src.core.cost import CostTracker, TokenCount
from src.core.judge import Judge, Verdict
from src.core.model_config import MODELS
from src.core.failure_action import FailureAction
from src.core.tier_config import get_tier_failure_action, get_tier_max_retries
from src.core.fail_now import get_fail_now, clear_fail_now, is_fail_now_active, check_mesh_fail_now
from src.core.fail_now import is_fail_up_active, clear_fail_up, check_mesh_fail_up
from src.core.model_profiles import get_prepend, get_known_failures

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2
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

    def get_api_key(self, tier: str) -> str | None:
        """Get API key for specified tier."""
        config = MODELS.get(tier, {})
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
            # Read max_tokens from tier config, default to 4096
            tier_cfg = self.provider_router._tiers.get(tier, {})
            max_tok = tier_cfg.get("max_tokens", 4096)
            response = adapter.call_sync(messages, temperature=temperature, max_tokens=max_tok)
            content = response.content

            # Phase 3: store in cache
            if self.cache.enabled:
                self.cache._store.set(cache_key, {"content": content})

            return content
        except Exception as e:
            raise Exception(f"Adapter call failed for tier {tier}: {e}")

    # Legacy raw-HTTP callers removed (Phase 2 — adapter wiring).
    # _call_openrouter and _call_lmstudio replaced by ProviderRouter +
    # OpenAICompatibleAdapter.  See src/adapters/providers/base_provider.py.

    def _get_agent_system_prompt(self, task_type: str = "code") -> str:
        """Load the agent system prompt template for the task type.

        Loads docs/workflow/templates/{task_type}-system-prompt.md.
        Falls back to a concise inline prompt if the template file is missing.
        """
        template_path = self.workflow_dir / "templates" / f"{task_type}-system-prompt.md"
        if template_path.exists():
            return template_path.read_text()
        # Fallback: minimal but functional prompt
        return (
            "You are an expert software developer.\n"
            "Use file_read(\"path\") and file_write(\"path\", \"\"\"content\"\"\") tools.\n"
            "Read before writing, match existing conventions, write complete code.\n"
            "If ambiguous, ask. Handle edge cases. Verify your changes work.\n"
        )

    def _build_system_prompt(self, tier: str, template: str) -> str:
        """Extract system prompt from template."""
        lines = template.split("\n")
        system_lines = []
        for line in lines:
            if line.startswith("# ROLE:"):
                system_lines.append(line)
            elif line.startswith("##"):
                break
            else:
                system_lines.append(line)
        return "\n".join(system_lines)

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

    def execute_with_judge(
        self,
        task_id: str,
        context: dict[str, Any],
        task_type: str = "code",
        tiers: list[str] | None = None,
        max_retries_per_tier: int = 3,
        judge_model: str = "Judge",
        timeout_seconds: float = 300,
    ) -> dict[str, Any]:
        """Execute a task using Judge-based retry/escalation logic.

        Args:
            task_type: "code" or "plan" — determines which agent system
                prompt template and judge evaluation criteria to use.

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

        # Check for fail-now signal
        fail_now_tier = get_fail_now()
        if fail_now_tier:
            # Check mesh signal file
            check_mesh_fail_now()
            # Validate the tier exists
            if fail_now_tier not in MODELS:
                # Fall through to closest available tier
                available = [t for t in tiers or ["L0-Coder", "L1-Coder", "L2-Coder", "Principal"] if t in MODELS]
                fail_now_tier = available[-1] if available else None
            
            if fail_now_tier:
                tier_config = MODELS.get(fail_now_tier, {})
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

        for tier in tiers:
            feedback = ""
            retries_per_tier[tier] = 0
            fail_up_aborted = False  # track if fail_up triggered this tier

            # Look up tier config (used by Principal check, circuit breaker, and retry loop)
            tier_config = MODELS.get(tier, {})

            # --- Principal Agent check ---
            # Principal has no provider/model — it's the user's own agent.
            # When escalation reaches Principal, return full context so the
            # calling agent (Hermes, Claude Code, etc.) can take over.
            if tier_config.get("role") == "principal":
                principal_context = {
                    "task": context.get("task_spec", task_id),
                    "tiers_attempted": list(escalation_path),
                    "retries_per_tier": dict(retries_per_tier),
                    "last_feedback": feedback,
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

                result = self.call_llm_with_retry(
                    tier, agent_system_prompt, str(user_prompt),
                    temperature=tier_config.get("temperature", 0.7),
                    timeout_seconds=timeout_seconds,
                )

                attempts_total += 1
                retries_per_tier[tier] += 1

                if not result["success"]:
                    # HTTP/network failure — skip remaining retries for this tier
                    print(f"Tier {tier} HTTP failure: {result.get('error', 'unknown')}")
                    break

                # --- Tool execution ---
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
                        accepted=False, score=0.0,
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
                    duration_seconds = time.monotonic() - start_time
                    return {
                        "task_id": task_id,
                        "success": True,
                        "output": result["output"],
                        "tier_used": tier,
                        "attempts_total": attempts_total,
                        "retries_per_tier": retries_per_tier,
                        "verdict": verdict,
                        "cost_summary": self.cost_tracker.get_summary(),
                        "escalation_path": escalation_path + [tier],
                        "duration_seconds": duration_seconds,
                        "tool_results": tool_result,
                    }

                # Rejected — save feedback for next retry
                feedback = verdict.critique
                print(f"Tier {tier} retry {retry_num} rejected: {verdict.critique}")

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
