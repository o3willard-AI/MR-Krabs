#!/usr/bin/env python3
"""Model configuration — shared MODELS dict used by orchestrator and judge."""

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
