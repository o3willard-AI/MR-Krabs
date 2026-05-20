#!/usr/bin/env python3
"""Model configuration — shared MODELS dict used by orchestrator and judge.

Best Practice: The Judge model should ALWAYS be a reasoning-specialized LLM.
Reasoning models (Claude Opus, Sonnet, GPT-4, o1) produce more calibrated
scores, more actionable critiques, and fewer hallucinated JSON responses
than general-purpose or small models. Never use a small local model for
judging — the Judge is the quality gate for the entire pipeline; its
reliability directly determines whether good code gets accepted and bad
code gets caught.

MR-Krabs uses a dedicated Judge model entry (not an agent tier) to make
this separation explicit in the configuration.
"""

MODELS = {
    # ── Judge model (quality gate) ─────────────────────────────────
    # Always a reasoning model — never a small/cheap tier agent.
    "Judge": {
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
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
    # ── Optional cloud tiers (insert before Principal) ────────────
    # Available but NOT in default escalation path.
    # To use: pass tiers=["L0-Coder", ..., "L3-Coder", "Principal"]
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
