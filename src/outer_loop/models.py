#!/usr/bin/env python3
"""Outer loop model profiles — which models handle decomposition, verification, learning.

Separate from the inner MR-Krabs models. These roles need different capabilities:
- Decomposer: structural analysis of large specs — needs big context, reasoning
- Verifier: contract checking, test running — lighter is fine
- Learner: failure → rule synthesis — needs analytical depth
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OuterLoopModel:
    """A model assigned to an outer loop role."""
    role: str
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 16384


# ── Fallback model profiles when no config exists ───────────────────────────
# Override by adding `outer_loop:` section to ~/.mrkrabs/config.yaml

DEFAULT_OUTER_LOOP_MODELS: dict[str, OuterLoopModel] = {
    "decomposer": OuterLoopModel(
        role="decomposer",
        provider="local-23",
        model="qwen3-coder-30b-q4",
        temperature=0.0,
        max_tokens=16384,
    ),
    "verifier": OuterLoopModel(
        role="verifier",
        provider="local-21",
        model="Qwen2.5-Coder-7B-Instruct-Q4_K_M",
        temperature=0.1,
        max_tokens=8192,
    ),
    "learner": OuterLoopModel(
        role="learner",
        provider="local-23",
        model="qwen3-coder-30b-q4",
        temperature=0.0,
        max_tokens=16384,
    ),
}


def get_outer_loop_models() -> dict[str, OuterLoopModel]:
    """Load outer loop model config from ~/.mrkrabs/config.yaml or fall back to defaults.

    Returns:
        Dict of role_name -> OuterLoopModel
    """
    try:
        from src.core.config_loader import get_config
        config = get_config()
        raw = getattr(config, "_raw", {})
        outer_loop_raw = raw.get("outer_loop", {})
        if outer_loop_raw:
            models = {}
            for role, mdata in outer_loop_raw.get("models", {}).items():
                if isinstance(mdata, dict):
                    models[role] = OuterLoopModel(
                        role=role,
                        provider=mdata.get("provider", ""),
                        model=mdata.get("model", ""),
                        temperature=float(mdata.get("temperature", 0.0)),
                        max_tokens=int(mdata.get("max_tokens", 16384)),
                    )
            if models:
                return models
    except Exception:
        pass

    return dict(DEFAULT_OUTER_LOOP_MODELS)
