#!/usr/bin/env python3
"""Configuration loader using TOML format.

TOML is preferred over YAML because:
- No indentation sensitivity
- No type coercion surprises (NO -> false, 1.0 -> float)
- No security risks with yaml.load()
- Native Python support via tomllib (stdlib 3.11+)
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from src.core.cost import Budget, Decimal, FailureMode

CURRENT_CONFIG_VERSION = "1.0"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CURRENT_CONFIG_VERSION,
    "budget": {
        "daily_limit_usd": "10.00",
        "task_limit_usd": "1.00",
        "warning_threshold": "0.8",
        "failure_mode": "fail_open_with_alert",
        "emergency_cap_usd": "5.00",
        "emergency_call_limit": 10,
    },
    "providers": {
        "openrouter": {
            "api_key_env": "OPENROUTER_API_KEY",
            "base_url": "https://openrouter.ai/api/v1",
        },
    },
    "tiers": {
        "L0": {"models": ["qwen/qwen3.5-397b-a17b"], "max_retries": 3},
        "L1": {"models": ["x-ai/grok-4.1-fast"], "max_retries": 3},
        "L2": {"models": ["minimax/minimax-m2.7"], "max_retries": 2},
        "L3": {"models": ["anthropic/claude-sonnet-4.6"], "max_retries": 1},
    },
    "circuit_breaker": {
        "enabled": True,
        "failure_threshold": 0.5,
        "sample_size": 10,
        "cooldown_seconds": 60,
        "half_open_max": 3,
    },
    "context_simplification": {
        "enabled": False,
        "multipliers": [1.0, 0.7, 0.4],
    },
    "task_timeout_seconds": 300,
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from TOML file, merging with defaults.

    Args:
        config_path: Path to TOML config file. If None, searches for
            .cost_orchestrator.toml in current directory and home.

    Returns:
        Merged configuration dictionary (defaults + user overrides).

    Raises:
        ValueError: If config version is incompatible.
    """
    config = _deep_copy(DEFAULT_CONFIG)

    if config_path is None:
        config_path = _find_config()

    if config_path is not None and config_path.exists():
        with open(config_path, "rb") as f:
            user_config = tomllib.load(f)
        _validate_config_version(user_config)
        config = _deep_merge(config, user_config)

    return config


def _validate_config_version(user_config: dict[str, Any]) -> None:
    """Validate config version and raise if incompatible."""
    user_version = user_config.get("version", "1.0")
    if user_version != CURRENT_CONFIG_VERSION:
        raise ValueError(
            f"Config version mismatch: file has v{user_version}, "
            f"code expects v{CURRENT_CONFIG_VERSION}. "
            f"Run 'orchestrator config migrate' to upgrade."
        )


def _validate_config_version(user_config: dict[str, Any]) -> None:
    """Validate config version and raise if incompatible."""
    user_version = user_config.get("version", "1.0")
    if user_version != CURRENT_CONFIG_VERSION:
        raise ValueError(
            f"Config version mismatch: file has v{user_version}, "
            f"code expects v{CURRENT_CONFIG_VERSION}. "
            f"Run 'orchestrator config migrate' to upgrade."
        )


def config_to_budget(config: dict[str, Any]) -> Budget:
    """Convert config dict to Budget object."""
    budget_cfg = config.get("budget", {})
    return Budget(
        daily_limit_usd=Decimal(str(budget_cfg.get("daily_limit_usd", "10.00"))),
        task_limit_usd=Decimal(str(budget_cfg.get("task_limit_usd", "1.00"))),
        warning_threshold=Decimal(str(budget_cfg.get("warning_threshold", "0.8"))),
        failure_mode=FailureMode(budget_cfg.get("failure_mode", "fail_open_with_alert")),
        emergency_cap_usd=Decimal(str(budget_cfg.get("emergency_cap_usd", "5.00"))),
        emergency_call_limit=budget_cfg.get("emergency_call_limit", 10),
    )


def _find_config() -> Path | None:
    """Search for config file in common locations."""
    candidates = [
        Path.cwd() / ".cost_orchestrator.toml",
        Path.cwd() / "cost_orchestrator.toml",
        Path.home() / ".cost_orchestrator.toml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _deep_copy(d: dict) -> dict:
    """Deep copy a nested dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy(v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Override values take precedence."""
    result = _deep_copy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
