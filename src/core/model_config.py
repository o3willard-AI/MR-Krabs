#!/usr/bin/env python3
"""Model configuration — loaded from ~/.mrkrabs/config.yaml at runtime.

Phase D: No hardcoded models. MODELS is empty. All model definitions
come from ~/.mrkrabs/config.yaml. If no config exists, ConfigNotFoundError
is raised with setup instructions.
"""

# ── MODELS: permanently empty ───────────────────────────────────────
# All models are defined in ~/.mrkrabs/config.yaml.
# No model assumptions are baked into the repo.
MODELS: dict = {}


def get_models() -> dict:
    """Backward-compat wrapper — returns MODELS in legacy dict format.

    Loads from ~/.mrkrabs/config.yaml. Raises ConfigNotFoundError
    if no config exists.

    Results are cached within the process lifetime.

    Returns:
        Dict in legacy MODELS format: {tier_name: {provider, model, ...}}
    """
    from src.core.config_loader import legacy_models, get_config
    return legacy_models(get_config())
