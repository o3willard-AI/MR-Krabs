#!/usr/bin/env python3
"""Configuration loader — reads ~/.mrkrabs/config.yaml or auto-generates from legacy MODELS.

Phase A (this file):
  - Dataclasses for all config sections
  - load_config() — reads YAML, validates, falls back to legacy auto-gen
  - auto_generate_from_legacy() — converts the hardcoded MODELS dict into MrKrabsConfig
  - legacy_models() — backward-compat: converts MrKrabsConfig back to old MODELS dict format

Phase C (future):
  - MODELS dict removed from model_config.py
  - load_config() raises ConfigNotFoundError if no config file exists
  - Setup wizard prompts user's principal agent to define roles
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ── Dataclasses ───────────────────────────────────────────────────────────


class ConfigNotFoundError(Exception):
    """Raised when no config.yaml exists and no legacy models are available.

    The user's principal agent should walk them through defining roles
    and tiers. See docs/MODEL_CONFIG.md for examples.
    """

    def __init__(self):
        super().__init__(
            "No model configuration found.\n\n"
            "MR-Krabs does not ship with hardcoded models. Your principal\n"
            "agent should walk you through defining each pipeline role.\n\n"
            "Create ~/.mrkrabs/config.yaml, then run 'mrkrabs doctor' to\n"
            "validate connectivity.\n\n"
            "Examples: docs/MODEL_CONFIG.md\n"
        )


@dataclass
class ProviderConfig:
    """A model provider (OpenRouter, LiteLLM, direct LM Studio, etc.)."""

    name: str
    type: str = "openai_compatible"  # openai_compatible | none
    base_url: str = ""
    api_key_env: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 300

    @property
    def is_principal(self) -> bool:
        return self.type == "none"


@dataclass
class ModelConfig:
    """A model definition within the pipeline."""

    key: str  # "l0-coder", "judge", etc.
    provider: str  # references ProviderConfig.name
    model: str  # model ID on the provider
    temperature: float = 0.7
    max_tokens: int = 4096
    roles: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    profile: Optional[str] = None
    legacy_key: Optional[str] = None  # Original key from legacy MODELS dict (Phase A only)

    @property
    def is_principal(self) -> bool:
        return "principal" in self.roles


@dataclass
class WorkflowConfig:
    """An escalation chain for a task type."""

    name: str  # "code", "plan", "review"
    tiers: List[str] = field(default_factory=list)
    max_retries_per_tier: int = 3
    judge_model: str = "judge"


@dataclass
class BudgetConfig:
    """Budget-aware tier selection settings."""

    daily_limit_usd: Decimal = Decimal("10.00")
    budget_awareness: bool = False
    tier_thresholds: Dict[str, str] = field(default_factory=dict)


@dataclass
class KnownFailureConfig:
    """A known failure pattern for a model profile."""

    trigger: str = ""
    feedback: str = ""
    severity: str = "warning"


@dataclass
class ProfileConfig:
    """Model-specific enrichments: prepend prompts and known failures."""

    name: str
    prepend: str = ""
    known_failures: List[KnownFailureConfig] = field(default_factory=list)


@dataclass
class MrKrabsConfig:
    """Root configuration — single source of truth for all model definitions."""

    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    workflows: Dict[str, WorkflowConfig] = field(default_factory=dict)
    tier_failure_actions: Dict[str, str] = field(default_factory=dict)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    profiles: Dict[str, ProfileConfig] = field(default_factory=dict)
    pi_models: Dict[str, str] = field(default_factory=dict)
    pi_timeouts: Dict[str, int] = field(default_factory=dict)
    prompt_flow_debug: bool = False
    config_path: Optional[Path] = None

    # ── Lookup helpers ──────────────────────────────────────────────────

    def get_model(self, key: str) -> Optional[ModelConfig]:
        """Look up a model by key (tier name or model name)."""
        return self.models.get(key)

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Look up a provider by name."""
        return self.providers.get(name)

    def get_workflow(self, name: str) -> Optional[WorkflowConfig]:
        """Look up a workflow by name."""
        return self.workflows.get(name)

    def get_failure_action(self, tier: str) -> str:
        """Get failure action for a tier, defaulting to 'log_only'."""
        return self.tier_failure_actions.get(tier, "log_only")

    def models_for_role(self, role: str) -> List[str]:
        """List model keys that have the given role tag."""
        return [k for k, m in self.models.items() if role in m.roles]

    @property
    def available_roles(self) -> List[str]:
        """All unique roles across configured models."""
        roles: set[str] = set()
        for m in self.models.values():
            roles.update(m.roles)
        return sorted(roles)


# ── Default Paths ─────────────────────────────────────────────────────────

def _default_config_path() -> Path:
    """Return the default config path: ~/.mrkrabs/config.yaml.

    Can be overridden with the MRKRABS_CONFIG environment variable.
    """
    env_path = os.environ.get("MRKRABS_CONFIG")
    if env_path:
        return Path(env_path)
    return Path.home() / ".mrkrabs" / "config.yaml"


# ── YAML Loading ──────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file, returning empty dict if not found."""
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _apply_defaults(data: dict, defaults: dict) -> dict:
    """Apply defaults for missing keys (shallow, first level only)."""
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
    return data


# ── Parsing Functions ─────────────────────────────────────────────────────

def _parse_providers(raw: dict) -> Dict[str, ProviderConfig]:
    """Parse providers section from raw YAML dict."""
    providers: Dict[str, ProviderConfig] = {}
    for name, pdata in raw.items():
        if not isinstance(pdata, dict):
            continue
        providers[name] = ProviderConfig(
            name=name,
            type=pdata.get("type", "openai_compatible"),
            base_url=pdata.get("base_url", ""),
            api_key_env=pdata.get("api_key_env"),
            api_key=pdata.get("api_key"),
            timeout=int(pdata.get("timeout", 300)),
        )
    return providers


def _parse_models(raw: dict) -> Dict[str, ModelConfig]:
    """Parse models section from raw YAML dict."""
    models: Dict[str, ModelConfig] = {}
    for key, mdata in raw.items():
        if not isinstance(mdata, dict):
            continue
        models[key] = ModelConfig(
            key=key,
            provider=mdata.get("provider", ""),
            model=mdata.get("model", ""),
            temperature=float(mdata.get("temperature", 0.7)),
            max_tokens=int(mdata.get("max_tokens", 4096)),
            roles=list(mdata.get("roles", [])),
            tools=list(mdata.get("tools", [])),
            profile=mdata.get("profile"),
        )
    return models


def _parse_workflows(raw: dict) -> Dict[str, WorkflowConfig]:
    """Parse workflows section from raw YAML dict."""
    workflows: Dict[str, WorkflowConfig] = {}
    for name, wdata in raw.items():
        if not isinstance(wdata, dict):
            continue
        workflows[name] = WorkflowConfig(
            name=name,
            tiers=list(wdata.get("tiers", [])),
            max_retries_per_tier=int(wdata.get("max_retries_per_tier", 3)),
            judge_model=wdata.get("judge_model", "judge"),
        )
    return workflows


def _parse_budget(raw: dict) -> BudgetConfig:
    """Parse budget section from raw YAML dict."""
    if not raw:
        return BudgetConfig()
    return BudgetConfig(
        daily_limit_usd=Decimal(str(raw.get("daily_limit_usd", "10.00"))),
        budget_awareness=bool(raw.get("budget_awareness", False)),
        tier_thresholds={
            str(k): str(v)
            for k, v in raw.get("tier_thresholds", {}).items()
        },
    )


def _parse_profiles(raw: dict) -> Dict[str, ProfileConfig]:
    """Parse profiles section from raw YAML dict."""
    profiles: Dict[str, ProfileConfig] = {}
    for name, pdata in raw.items():
        if not isinstance(pdata, dict):
            continue
        failures = []
        for kf in pdata.get("known_failures", []):
            if isinstance(kf, dict):
                failures.append(KnownFailureConfig(
                    trigger=str(kf.get("trigger", "")),
                    feedback=str(kf.get("feedback", "")),
                    severity=str(kf.get("severity", "warning")),
                ))
        profiles[name] = ProfileConfig(
            name=name,
            prepend=str(pdata.get("prepend", "")),
            known_failures=failures,
        )
    return profiles


# ── Module-level cache ──────────────────────────────────────────────────────

_config_cache: Optional[MrKrabsConfig] = None


def get_config(reload: bool = False) -> MrKrabsConfig:
    """Get the cached config, loading it if not already loaded.

    Args:
        reload: If True, force a fresh load from disk/legacy.

    Returns:
        MrKrabsConfig — cached across calls within a process lifetime.
    """
    global _config_cache
    if _config_cache is None or reload:
        _config_cache = load_config()
    return _config_cache


def reset_config_cache() -> None:
    """Clear the config cache (useful for testing)."""
    global _config_cache
    _config_cache = None


# ── Main Loader ───────────────────────────────────────────────────────────


def load_config(path: Optional[str] = None) -> MrKrabsConfig:
    """Load configuration from a YAML file, or auto-generate from legacy MODELS.

    Priority:
      1. Explicit path argument
      2. ~/.mrkrabs/config.yaml
      3. Auto-generate from the hardcoded MODELS dict (legacy compat)

    Returns:
        MrKrabsConfig — validated, ready to use.
    """
    config_path = Path(path) if path else _default_config_path()
    raw = _load_yaml(config_path)

    if not raw:
        # No config file found — auto-generate from legacy MODELS
        config = _auto_generate_from_legacy()
        if not config.models and not config.providers:
            raise ConfigNotFoundError()
        return config

    # Parse each section from YAML
    providers = _parse_providers(raw.get("providers", {}))
    models = _parse_models(raw.get("models", {}))
    workflows = _parse_workflows(raw.get("workflows", {}))
    budget = _parse_budget(raw.get("budget", {}))
    profiles = _parse_profiles(raw.get("profiles", {}))
    tier_failure_actions = raw.get("tier_failure_actions", {})
    pi_models = raw.get("pi_models", {})
    pi_timeouts = raw.get("pi_timeouts", {})
    prompt_flow_debug = raw.get("prompt_flow_debug", False)

    # Validate: every model's provider must be defined
    for key, model in models.items():
        if model.provider and model.provider not in providers and not model.is_principal:
            raise ValueError(
                f"Model '{key}' references provider '{model.provider}' "
                f"which is not defined in the providers section."
            )

    # Validate: workflow tiers must reference defined models
    for wf_name, wf in workflows.items():
        for tier in wf.tiers:
            if tier not in models and tier != "principal":
                raise ValueError(
                    f"Workflow '{wf_name}' references tier '{tier}' "
                    f"which is not defined in the models section."
                )

    return MrKrabsConfig(
        providers=providers,
        models=models,
        workflows=workflows,
        tier_failure_actions=tier_failure_actions,
        budget=budget,
        profiles=profiles,
        pi_models=pi_models,
        pi_timeouts=pi_timeouts,
        prompt_flow_debug=prompt_flow_debug,
        config_path=config_path,
    )


# ── Legacy Auto-Generation ────────────────────────────────────────────────


def _auto_generate_from_legacy() -> MrKrabsConfig:
    """Raise ConfigNotFoundError — legacy MODELS have been removed in Phase D.

    Previously auto-generated from _LEGACY_MODELS in model_config.py.
    In Phase D, all models must come from ~/.mrkrabs/config.yaml.
    """
    raise ConfigNotFoundError()


def _infer_role(entry: dict, key: str) -> str:
    """Infer a model's role from its legacy MODELS entry.

    Priority: explicit 'role' field → key name pattern → 'coder' default.
    Examples: "L0-Planner" → "planner", "L3-Architect" → "architect",
              "Judge" → "judge", "L3-Coder" → "coder"
    """
    if "role" in entry:
        return entry["role"]

    # Infer from key name
    key_lower = key.lower()
    if "architect" in key_lower:
        return "architect"
    if "planner" in key_lower:
        return "planner"
    if "reviewer" in key_lower:
        return "reviewer"
    if "judge" in key_lower:
        return "judge"
    if "coder" in key_lower:
        return "coder"

    return "coder"


# ── Legacy Auto-Gen Helpers ──────────────────────────────────────────────


def _infer_provider_name(entry: dict, base_url: str, model_key: str) -> str:
    """Infer a provider name from a MODELS entry."""
    provider = entry.get("provider", "")

    # Known patterns
    if "openrouter" in base_url:
        return "openrouter"
    if "1234" in base_url and provider == "lmstudio":
        # LM Studio — extract host from URL for unique naming
        host = base_url.split("//")[1].split(":")[0] if "//" in base_url else ""
        # Use last octet for short name
        octet = host.split(".")[-1] if host else ""
        return f"lmstudio_{octet}" if octet else "lmstudio"
    if "vast.ai" in base_url:
        return "vast_ai"

    # Fallback: use provider field
    return provider or "unknown"


def _normalize_model_key(key: str) -> str:
    """Normalize a legacy MODELS key to lowercase-hyphenated config style.

    Examples:
        "L0-Coder" → "l0-coder"
        "L0-Planner" → "l0-planner"
        "Judge" → "judge"
        "L0-Sushi-Planner" → "l0-sushi-planner"
        "Principal" → "principal"
    """
    # Special cases
    if key == "Judge":
        return "judge"
    if key == "Principal":
        return "principal"
    # General case: lowercase, replace spaces with hyphens
    return key.lower().replace(" ", "-")


def _extract_tier_number(key: str) -> int:
    """Extract tier number from a model key: l0-coder → 0, l2-planner → 2."""
    match = re.match(r"l(\d+)", key.lower())
    return int(match.group(1)) if match else 0


def _tier_sort_key(key: str) -> int:
    """Sort key: l0 before l1 before l2. Non-tier keys sort last."""
    return _extract_tier_number(key)


def _build_role_hierarchy(models: Dict[str, ModelConfig]) -> Dict[str, List[str]]:
    """Group model keys by their primary role.

    Returns dict mapping role → list of model keys (sorted by tier).
    """
    hierarchy: Dict[str, List[str]] = {}
    for key, model in models.items():
        if model.is_principal:
            continue
        for role in model.roles:
            if role == "principal":
                continue
            if role not in hierarchy:
                hierarchy[role] = []
            if key not in hierarchy[role]:
                hierarchy[role].append(key)
    return hierarchy


def _auto_generate_profiles() -> Dict[str, ProfileConfig]:
    """Auto-generate ProfileConfig entries from model_profiles.py PROFILES."""
    try:
        from src.core.model_profiles import PROFILES, KnownFailure
    except ImportError:
        return {}

    result: Dict[str, ProfileConfig] = {}
    for key, profile in PROFILES.items():
        failures = []
        for kf in profile.known_failures:
            failures.append(KnownFailureConfig(
                trigger=kf.trigger,
                feedback=kf.feedback,
                severity=kf.severity,
            ))
        result[key] = ProfileConfig(
            name=key,
            prepend=profile.prompt_prepend,
            known_failures=failures,
        )
    return result


def _legacy_key(norm_key: str) -> str:
    """Reverse-normalize a config key to legacy MODELS format.

    Examples:
        "l0-coder" → "L0-Coder"
        "l0-sushi-planner" → "L0-Sushi-Planner"
        "judge" → "Judge"
        "principal" → "Principal"
        "l3-architect" → "L3-Architect"
    """
    if norm_key == "judge":
        return "Judge"
    if norm_key == "principal":
        return "Principal"

    parts = norm_key.split("-")
    result = []
    for p in parts:
        if p.startswith("l") and len(p) >= 2 and p[1:].isdigit():
            result.append(p.upper())  # L0, L1, L2, L3
        else:
            result.append(p[0].upper() + p[1:] if p else "")  # Coder, Planner
    return "-".join(result)


# ── Backward-Compat Wrapper ───────────────────────────────────────────────


def legacy_models(config: Optional[MrKrabsConfig] = None) -> Dict[str, Dict[str, Any]]:
    """Convert MrKrabsConfig back to the old MODELS dict format.

    This is the Phase A backward-compat bridge. All existing code that
    does MODELS.get(tier, {}) can call this function instead.

    Args:
        config: Optional MrKrabsConfig. If None, calls load_config().

    Returns:
        Dict in the old MODELS format: {tier_name: {provider, model, base_url, ...}}
    """
    if config is None:
        config = load_config()

    result: Dict[str, Dict[str, Any]] = {}
    for key, model in config.models.items():
        provider = config.providers.get(model.provider)
        legacy_key = model.legacy_key or _legacy_key(key)
        entry: Dict[str, Any] = {
            "provider": model.provider,
            "model": model.model,
            "base_url": provider.base_url if provider else "",
            "env_var": provider.api_key_env if provider else None,
            "api_key_env": provider.api_key_env if provider else None,  # new key
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
            "tools": model.tools,
            "role": model.roles[0] if model.roles else "coder",
            "profile": model.profile,
        }
        result[legacy_key] = entry
        # Also register under the normalized key so case-insensitive lookups work
        # (e.g. judge_model="judge" in workflow config can find "Judge" in models)
        if key != legacy_key:
            result[key] = entry
    return result
