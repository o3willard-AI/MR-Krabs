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
    # ── Agent tiers ────────────────────────────────────────────────
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
