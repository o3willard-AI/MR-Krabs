"""Dynamic token-budget-aware pass sizing.

Replaces the hardcoded MAX_FILES_PER_PASS with context-window-aware
calculations. Queries the target LLM server for its actual n_ctx,
estimates token requirements for the spec + system prompts + output,
and determines how many files fit in a single pass.

Uses MAX_FILES_PER_PASS from task_splitter as a hard ceiling (never
exceed it regardless of budget), plus MAX_FILES_PER_PASS / 2 as a
safety floor (never go below).

When the server context window cannot be determined (query returns
None), the orchestrator escalates to the Principal Agent rather than
falling back to a hardcoded limit. The Principal provides an accurate
n_ctx via context['n_ctx_override'].

Flow:
  1. Query server at base_url/slots for n_ctx
  2. Estimate input tokens: spec + system prompt + rules + overhead
  3. Estimate output tokens per file based on type
  4. Calculate files_per_pass = (n_ctx - input_budget) / avg_file_budget
  5. Clamp to [floor, ceiling]
  6. If n_ctx unknown: escalate to Principal, not hardcoded fallback
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Optional

from src.core.task_splitter import MAX_FILES_PER_PASS

# ── Token estimation ─────────────────────────────────────────────────

# Rough heuristic: English prose ≈ 4 chars/token, code ≈ 3 chars/token.
# We use 3.5 as a middle ground for mixed content.
CHARS_PER_TOKEN = 3.5

# Estimated token overhead for agent conversation format
# (system prompt framing, tool definitions, conversation history scaffolding).
# OpenCode adds ~3K tokens per file (tool call + response + compaction scaffolding).
# At 32K ctx, 15K overhead is realistic.
AGENT_OVERHEAD_TOKENS = 15_000  # matches observed throughput at 32K

# Minimum floor as absolute file count — never go below this
# regardless of budget. With 32K context even 3-5 files is viable
# for large files like app.py.
FLOOR_FILES = 3

# Known context windows for cloud providers (tokens)
KNOWN_PROVIDER_WINDOWS: dict[str, int] = {
    "openrouter": 131_072,  # most OpenRouter models
    "deepseek": 131_072,
    "anthropic": 200_000,
    "openai": 128_000,
}


def estimate_tokens(text: str) -> int:
    """Rough token count estimate. Within ±20% for English text/code."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def estimate_file_output_tokens(filepath: str) -> int:
    """Estimate tokens needed for a file's generated content.

    Uses file extension as a size heuristic:
    - Python/JS: 2-4K tokens (dense code)
    - HTML: 1-2K tokens (markup)
    - CSS: 500-1K tokens (styling)
    - .txt/requirements: 100-500 tokens (small)
    - Tests: 1-2K tokens
    """
    ext = Path(filepath).suffix.lower()
    basename = Path(filepath).name.lower()

    if ext in (".py",):
        if "test" in basename:
            return 1_500  # test file
        return 3_000  # full Python module
    elif ext in (".js", ".ts"):
        return 2_500
    elif ext in (".html", ".jinja", ".jinja2"):
        return 1_500
    elif ext in (".css", ".scss", ".less"):
        return 800
    elif ext in (".md", ".rst"):
        return 2_000
    elif ext in (".txt",):
        return 200
    elif ext in (".json", ".yaml", ".yml", ".toml"):
        return 1_000
    elif ext in (".sh", ".bash"):
        return 1_500
    elif ext in (".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp"):
        return 3_000
    else:
        return 1_500  # unknown — assume moderate


# ── Server context window query ───────────────────────────────────────


def query_context_window(base_url: str, timeout: float = 5.0) -> Optional[int]:
    """Query a llama.cpp or OpenAI-compatible server for its context window.

    Tries /slots (llama.cpp-specific), falls back to known provider windows,
    returns None if unreachable.

    Args:
        base_url: Server base URL (e.g. "http://192.168.101.23:1234/v1")
        timeout: HTTP request timeout in seconds

    Returns:
        n_ctx value, or None if unreachable
    """
    # Normalize: strip trailing /v1 for llama.cpp slot query
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]

    # Try llama.cpp /slots endpoint
    try:
        url = f"{clean_url}/slots"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list) and len(data) > 0:
                n_ctx = data[0].get("n_ctx")
                if n_ctx and isinstance(n_ctx, int) and n_ctx > 0:
                    return n_ctx
    except Exception:
        pass

    # Try /props endpoint
    try:
        url = f"{clean_url}/props"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            n_ctx = data.get("default_generation_settings", {}).get("n_ctx")
            if n_ctx and isinstance(n_ctx, int) and n_ctx > 0:
                return n_ctx
    except Exception:
        pass

    # Check known cloud provider windows by hostname
    hostname = urlparse_hostname(clean_url)
    if hostname:
        for prefix, window in KNOWN_PROVIDER_WINDOWS.items():
            if prefix in hostname.lower():
                return window

    return None


def urlparse_hostname(url: str) -> Optional[str]:
    """Extract hostname from a URL string without importing urllib.parse."""
    match = re.search(r"://([^/:]+)", url)
    return match.group(1) if match else None


# ── Budget calculation ────────────────────────────────────────────────


def calculate_pass_capacity(
    spec_text: str,
    system_prompt_text: str,
    rules_text: str,
    n_ctx: int,
    file_refs: list,
    overhead_tokens: int = AGENT_OVERHEAD_TOKENS,
) -> int:
    """Calculate how many files fit in one pass given context constraints.

    Args:
        spec_text: The task specification
        system_prompt_text: Agent system prompt
        rules_text: Coding rules (OpenCode -f attachment or PI append)
        n_ctx: Server context window in tokens
        file_refs: File references (FileRef list or path strings)
        overhead_tokens: Agent conversation overhead

    Returns:
        Recommended files per pass (clamped to [floor, MAX_FILES_PER_PASS])
    """
    # Input budget: spec + prompts + overhead
    input_tokens = (
        estimate_tokens(spec_text)
        + estimate_tokens(system_prompt_text)
        + estimate_tokens(rules_text)
        + overhead_tokens
    )

    # Output budget: remaining context minus 40% safety margin
    # (20% was too optimistic — models truncate with even moderate files)
    available = int((n_ctx - input_tokens) * 0.6)
    if available <= 0:
        # Spec already fills context — absolute minimum floor
        return FLOOR_FILES

    # Average output per file
    total_estimated = sum(
        estimate_file_output_tokens(
            f.path if hasattr(f, "path") else str(f)
        )
        for f in file_refs
    )
    avg_per_file = max(1, total_estimated // max(1, len(file_refs)))

    # How many files fit?
    capacity = max(1, available // avg_per_file)

    # Clamp
    floor = FLOOR_FILES
    ceiling = MAX_FILES_PER_PASS

    return max(floor, min(capacity, ceiling))


def resolve_base_url(
    tier: str,
    opencode_models: dict[str, str],
    pi_models: dict[str, str],
) -> Optional[str]:
    """Resolve the base URL for a tier's model server.

    Tries OpenCode first (default), then PI (fallback).
    Returns None if neither is configured.
    """
    import subprocess

    model_spec = opencode_models.get(tier.lower())
    if model_spec:
        # OpenCode model — parse provider from spec
        # Try running opencode providers to get base URL
        # Or resolve from ~/.config/opencode/opencode.json
        return _resolve_opencode_base_url(model_spec)

    model_spec = pi_models.get(tier.lower())
    if model_spec:
        return _resolve_pi_base_url(model_spec)

    return None


def _resolve_opencode_base_url(model_spec: str) -> Optional[str]:
    """Resolve OpenCode provider spec to a base URL."""
    provider = model_spec.split("/")[0] if "/" in model_spec else model_spec
    # Check known local providers from opencode.json
    if provider.startswith("local"):
        # Try common local ports
        for port in ("1234", "8080"):
            url = f"http://127.0.0.1:{port}"
            if query_context_window(url):
                return url
        # Try .23 and .21
        for host in ("192.168.101.23", "192.168.101.21"):
            url = f"http://{host}:1234"
            if query_context_window(url):
                return url

    # Check known cloud providers
    if provider in KNOWN_PROVIDER_WINDOWS:
        return provider  # caller will use known window

    # Try reading opencode.json for the provider's baseURL
    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
        prov = config.get("provider", {}).get(provider, {})
        opts = prov.get("options", {})
        return opts.get("baseURL", opts.get("base_url"))
    except Exception:
        pass

    return None


def _resolve_pi_base_url(model_spec: str) -> Optional[str]:
    """Resolve PI model spec to a base URL."""
    provider = model_spec.split("/")[0] if "/" in model_spec else model_spec
    config_path = Path.home() / ".pi" / "agent" / "models.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
        prov = config.get("providers", {}).get(provider, {})
        return prov.get("baseUrl", prov.get("base_url"))
    except Exception:
        pass
    return None
