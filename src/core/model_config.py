#!/usr/bin/env python3
"""Model configuration — shared MODELS dict used by orchestrator and judge.

Best Practice: The Judge model should ALWAYS be a reasoning-specialized LLM.
Reasoning models (Claude Opus, DeepSeek R1, o1, o3) produce more calibrated
scores, more actionable critiques, and fewer hallucinated JSON responses
than general-purpose or small models. Never use a small local model for
judging — the Judge is the quality gate for the entire pipeline; its
reliability directly determines whether good code gets accepted and bad
code gets caught.

MR-Krabs uses a dedicated Judge model entry (not an agent tier) to make
this separation explicit in the configuration.
"""

from src.core.constants import LM_STUDIO_BASE_URL, OPENROUTER_BASE_URL

MODELS = {
    # ── Judge model (quality gate) ─────────────────────────────────
    # Always a reasoning model — never a small/cheap tier agent.
    "Judge": {
        "provider": "openrouter",
        "model": "deepseek/deepseek-r1",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.1,
        "tools": [],
        "role": "judge",
    },
    # ── Agent tiers (L0–L2) ─────────────────────────────────────────
    # Tiered escalation: L0 (local, free) → L1 (cheap cloud) → L2 (capable cloud)
    # → Principal Agent (the user's own agent — Hermes, Claude Code, etc.)
    #
    # L3 is available as an optional cloud tier that sits between L2 and Principal:
    #   ["L0-Coder", "L1-Coder", "L2-Coder", "L3-Coder", "Principal"]
    # By default L3 is unused — escalation jumps from L2 directly to Principal.
    "L0-Planner": {
        "provider": "openrouter",
        "model": "google/gemini-2.5-pro",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.0,
        "tools": ["file_read", "file_write"],
        "role": "planner",
        "max_tokens": 32768,
    },
    "L0-Reviewer": {
        "provider": "openrouter",
        "model": "google/gemini-2.5-flash",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.3,
        "tools": ["file_read"],
        "role": "reviewer",
    },
    "L0-Coder": {
        "provider": "openrouter",
        "model": "x-ai/grok-4.3",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.0,
        "tools": ["file_write", "file_read"],
        "role": "coder",
    },
    "L1-Coder": {
        "provider": "openrouter",
        "model": "google/gemini-2.5-flash",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.0,
        "tools": ["file_write", "file_read"],
        "role": "coder",
    },
    "L2-Coder": {
        "provider": "openrouter",
        "model": "anthropic/claude-haiku-4.5",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.0,
        "tools": ["file_write", "file_read"],
        "role": "coder",
    },
    # ── Principal Agent (top-level escalation) ─────────────────────
    # The Principal Agent is the user's own agent — Hermes, Claude Code,
    # Gemini CLI, opencode, or any other CLI coding agent the user interacts
    # with as their primary partner. MR-Krabs cannot "see" or manage the
    # Principal Agent's LLM — when escalation reaches this tier, control
    # returns to the calling agent with full escalation context.
    #
    # This has NO provider/model — the orchestrator detects "Principal"
    # and returns a structured escalation result instead of calling an LLM.
    "Principal": {
        "role": "principal",
    },
    # ── Local LM Studio models (12-16 GB GPU target) ─────────────
    # Small local models for budget-conscious coding. Each references
    # a ModelProfile in model_profiles.py for automated prompt enrichment
    # and judge-known-failure injection.
    # NOTE: Deepseek Coder V2 Lite (2.4B active, .17) was evaluated and
    # REJECTED — 12-0 sweep loss to Sushi across planner/orch/judge roles,
    # dangerously lenient judge calibration (0.9 for race conditions).
    "L0-Sushi": {
        "provider": "lmstudio",
        "model": "qwen3.5-9b-sushi-coder-rl",
        "env_var": "LM_STUDIO_URL",
        "base_url": "http://192.168.101.17:1234/v1",
        "temperature": 0.0,
        "tools": ["file_write", "file_read"],
        "role": "coder",
        "max_tokens": 4096,
        "profile": "sushi-9b",
        # LIMITATION: Cannot sustain multi-file builds — 394 lines max,
        # sub-75 lines/file. Viable as planner/orch/judge but not builder.
        # For build workloads, escalate to cloud tiers or Principal.
    },
    "L0-Sushi-Planner": {
        "provider": "lmstudio",
        "model": "qwen3.5-9b-sushi-coder-rl",
        "env_var": "LM_STUDIO_URL",
        "base_url": "http://192.168.101.17:1234/v1",
        "temperature": 0.0,
        "tools": ["file_read"],
        "role": "planner",
        "max_tokens": 4096,
        "profile": "sushi-9b",
    },
    "L0-Sushi-Judge": {
        "provider": "lmstudio",
        "model": "qwen3.5-9b-sushi-coder-rl",
        "env_var": "LM_STUDIO_URL",
        "base_url": "http://192.168.101.17:1234/v1",
        "temperature": 0.0,
        "tools": [],
        "role": "judge",
        "max_tokens": 2048,
        "profile": "sushi-9b",
        # Well-calibrated: 0.95 for correct code, 0.1 for SQL injection.
        # Prefer over small-model judges that are too lenient.
    },
    "L0-GPTOSS": {
        "provider": "lmstudio",
        "model": "gpt-oss-20b-claude-opus-sonnet-reasoning-i1",
        "env_var": "LM_STUDIO_URL",
        "base_url": "http://192.168.101.17:1234/v1",
        "temperature": 0.0,
        "tools": ["file_write", "file_read"],
        "role": "planner",
        "max_tokens": 8192,
        "profile": "gpt-oss-20b",
    },
    # ── Optional cloud tiers (insert before Principal) ────────────
    # Available but NOT in default escalation path.
    # To use: pass tiers=["L0-Coder", ..., "L3-Coder", "Principal"]
    "L3-Coder": {
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.7,
        "tools": ["file_read", "file_write"],
    },
    "L3-Architect": {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.6",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0.3,
        "tools": ["file_read"],
    },
}
