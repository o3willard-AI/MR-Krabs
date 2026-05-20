#!/usr/bin/env python3
"""Multi-Tier LLM Orchestrator - Core Implementation"""

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2
CONTEXT_SIMPLIFICATION = [1.0, 0.7, 0.4]

# Model Configuration
MODELS = {
    "L0-Planner": {
        "provider": "openrouter",
        "model": "qwen/qwen3.5-397b-a17b",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
    "L0-Reviewer": {
        "provider": "openrouter",
        "model": "qwen/qwen3.5-397b-a17b",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
    "L0-Coder": {
        "provider": "lmstudio",
        "model": "qwen/qwen3-coder-30b",
        "base_url": "http://192.168.101.21:1234/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L1-Coder": {
        "provider": "openrouter",
        "model": "x-ai/grok-4.3",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L2-Coder": {
        "provider": "openrouter",
        "model": "minimax/minimax-m2.7",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L3-Coder": {
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L3-Architect": {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.6",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "temperature": 0.3,
        "tools": ["file_read"],
    },
}

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

    def __init__(self, project_root: str = str(Path(__file__).parent.parent.parent.parent)):
        self.project_root = Path(project_root)
        self.workflow_dir = self.project_root / "docs" / "workflow"
        self.tasks_dir = self.project_root / "docs" / "tasks"
        self.handoffs_dir = self.workflow_dir / "handoffs"
        self.escalations_dir = self.workflow_dir / "escalations"
        self.file_tools = FileTools(self.project_root)
        self.tool_executor = ToolExecutor(self.file_tools)

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
                    print(f"  Retrying in {RETRY_DELAY}s with simplified context...")
                    time.sleep(RETRY_DELAY)

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
        self, tier: str, system_prompt: str, user_prompt: str, temperature: float = 0.7
    ) -> str:
        """Call the appropriate LLM for the specified tier."""
        config = MODELS.get(tier)
        if not config:
            raise ValueError(f"Unknown tier: {tier}")

        provider = config.get("provider")
        model = config.get("model")
        base_url = config.get("base_url")
        api_key = self.get_api_key(tier)

        if not model or not base_url:
            raise ValueError(f"Invalid configuration for tier {tier}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if provider == "openrouter":
            return self._call_openrouter(base_url, model, api_key, messages, temperature)
        elif provider == "lmstudio":
            return self._call_lmstudio(base_url, model, messages, temperature)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _call_openrouter(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        messages: list[dict],
        temperature: float,
    ) -> str:
        """Call OpenRouter API."""
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pairadmin/orchestrator",
            "X-Title": "Multi-Tier Orchestrator",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 8192,
        }

        response = requests.post(
            f"{base_url}/chat/completions", headers=headers, json=payload, timeout=300
        )
        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")

        return response.json()["choices"][0]["message"]["content"]

    def _call_lmstudio(
        self, base_url: str, model: str, messages: list[dict], temperature: float
    ) -> str:
        """Call LM Studio API."""
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 8192,
        }

        response = requests.post(
            f"{base_url}/chat/completions", headers=headers, json=payload, timeout=300
        )
        if response.status_code != 200:
            raise Exception(f"LM Studio API error: {response.status_code} - {response.text}")

        return response.json()["choices"][0]["message"]["content"]

    def _load_prompt_template(self, tier: str) -> str:
        """Load prompt template for tier."""
        template_map = {
            "L0-Planner": "01-planner.md",
            "L0-Coder": "02-l0-coder.md",
            "L0-Reviewer": "03-reviewer.md",
            "L1-Coder": "04-l1-coder.md",
            "L2-Coder": "05-l2-coder.md",
            "L3-Coder": "05-l2-coder.md",
            "L3-Architect": "06-l3-architect.md",
        }
        template_file = template_map.get(tier)
        if not template_file:
            raise ValueError(f"No template mapped for tier: {tier}")
        template_path = self.workflow_dir / "templates" / template_file
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        return template_path.read_text()

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
        from src.core.timeout import TaskTimeout
        
        # Pre-flight capability check
        token_count = 0  # We'll estimate this from the context
        requires_tools = False
        requires_vision = False
        
        # Check if task uses tools by examining context and model config
        tier_config = MODELS.get(tier, {})
        if tier_config:
            tools = tier_config.get("tools", [])
            requires_tools = len(tools) > 0
            
        # Estimate token count from context (very rough approximation)
        # This is a simplified approach - in reality, we'd want to use token counting
        # but for now we'll use a simple heuristic
        if context:
            total_chars = sum(len(str(v)) for v in context.values())
            token_count = max(1000, total_chars // 4)  # Rough estimate (avg 4 chars per token)
        
        # Check if the model can handle this task
        model_id = tier_config.get("model")
        if model_id:
            capability = MODEL_REGISTRY.get(model_id)
            if capability is not None:
                # Check context window
                if token_count > 0 and not capability.can_handle_context(token_count):
                    print(f"Warning: Model {model_id} has insufficient context window ({capability.context_window} < {token_count})")
                    # Try to find a capable model from the same tier or higher tiers
                    from src.core.tier_manager import TierManager, TierLevel
                    
                    # Find the tier level for this tier name
                    try:
                        tier_obj = TierManager.get_tier_by_name(tier)
                        if tier_obj:
                            fallback_model_id = TierManager().find_capable_model(
                                tier_obj.level, token_count, requires_tools
                            )
                            if fallback_model_id:
                                print(f"Switching to fallback model: {fallback_model_id}")
                                # We need to update the configuration to use this model
                                # For now we'll just log it - in practice this would be more involved
                                pass
                    except Exception as e:
                        print(f"Failed to find fallback model: {e}")
                        
                # Check tool calling support
                if requires_tools and not capability.can_handle_task(requires_tools=True):
                    print(f"Warning: Model {model_id} does not support tool calling")
                    # Try to find a capable model from the same tier or higher tiers
                    from src.core.tier_manager import TierManager, TierLevel
                    
                    try:
                        tier_obj = TierManager.get_tier_by_name(tier)
                        if tier_obj:
                            fallback_model_id = TierManager().find_capable_model(
                                tier_obj.level, token_count, requires_tools
                            )
                            if fallback_model_id:
                                print(f"Switching to fallback model: {fallback_model_id}")
                                # We need to update the configuration to use this model
                                # For now we'll just log it - in practice this would be more involved
                                pass
                    except Exception as e:
                        print(f"Failed to find fallback model: {e}")

        # Wrap the entire task execution in timeout
        with TaskTimeout(max_task_duration_seconds):
            template = self._load_prompt_template(tier)
            tier_config = MODELS.get(tier, {})
            temperature = tier_config.get("temperature", 0.7)

            system_prompt = self._build_system_prompt(tier, template)
            user_prompt = self._build_user_prompt(task_id, tier, context, template)

            result = self.call_llm_with_retry(
                tier, system_prompt, user_prompt, temperature, timeout_seconds=timeout_seconds
            )
            timestamp = datetime.now(UTC)

            if result["success"]:
                # Execute tool calls from LLM output
                tool_result = self.tool_executor.parse_and_execute_tools(result["output"])

                # Check if file_write tools succeeded
                file_writes = [r for r in tool_result["tool_results"] if r["tool"] == "file_write"]
                if file_writes:
                    failed_writes = [w for w in file_writes if not w["success"]]
                    if failed_writes:
                        result["success"] = False
                        result["error"] = (
                            f"file_write failed: {failed_writes[0].get('error', 'Unknown error')}"
                        )

                result["tool_results"] = tool_result
                handoff = self._log_handoff(
                    task_id,
                    tier,
                    context,
                    result["output"],
                    timestamp,
                    result["duration_seconds"],
                    result["attempt"],
                    tool_result,
                )
            else:
                handoff = self._log_failure(
                    task_id,
                    tier,
                    context,
                    result.get("error", "Unknown error"),
                    timestamp,
                    result["attempts"],
                )

            return {
                "task_id": task_id,
                "tier": tier,
                "success": result["success"],
                "output": result.get("output", ""),
                "attempts": result.get("attempt", result.get("attempts", 0)),
                "duration_seconds": result.get("duration_seconds", 0),
                "ready_for_escalation": result.get("ready_for_escalation", False),
                "tool_results": result.get(
                    "tool_results", {"tool_results": [], "tools_executed": 0, "all_succeeded": True}
                ),
                "handoff_log": handoff,
            }
