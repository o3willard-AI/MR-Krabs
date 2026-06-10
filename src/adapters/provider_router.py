"""Maps MR-Krabs tier names to provider adapter instances.

Each tier in MODELS maps to either:
- An OpenAI-compatible provider (openrouter, lmstudio, litellm) → OpenAICompatibleAdapter
- A custom provider with its own adapter class (future: anthropic, vertex, etc.)
- Principal tier → returns None (no LLM call)
"""

from typing import Dict, Optional

from .providers.base_provider import OpenAICompatibleAdapter
from .base_adapter import LiteLLMAdapter


class ProviderRouter:
    """Creates and caches provider adapter instances keyed on tier name."""

    def __init__(self):
        from src.core.model_config import get_models
        from src.core.config_loader import get_config

        self._tiers = get_models()
        self._adapters: Dict[str, LiteLLMAdapter] = {}
        # Load provider-level config for base_url fallback
        try:
            self._provider_cfgs = get_config().providers
        except Exception:
            self._provider_cfgs = {}

    def get_adapter(self, tier: str) -> Optional[LiteLLMAdapter]:
        """Get or create adapter for a tier. Returns None for Principal/non-LLM tiers."""
        if tier in self._adapters:
            return self._adapters[tier]

        config = self._tiers.get(tier, {})
        if config.get("role") == "principal" or not config:
            return None

        provider = config.get("provider", "")
        model = config.get("model", "")
        base_url = config.get("base_url", "")
        env_var = config.get("env_var", "")

        # Fall back to provider-level config for base_url and env_var
        if not base_url and provider in self._provider_cfgs:
            pcfg = self._provider_cfgs[provider]
            base_url = getattr(pcfg, "base_url", "") or ""
        if not env_var and provider in self._provider_cfgs:
            pcfg = self._provider_cfgs[provider]
            penv = getattr(pcfg, "api_key_env", None)
            if penv:
                env_var = penv

        if provider in ("openrouter", "lmstudio", "litellm"):
            adapter = OpenAICompatibleAdapter(
                config={"base_url": base_url, "api_key_env": env_var},
                name=f"{provider}-{model}",
            )
            adapter.provider_name = provider
            adapter.base_url = base_url
            adapter.default_model = model
            adapter.env_var = env_var
            adapter._base_url = base_url
            self._adapters[tier] = adapter
            return adapter

        # M11: Custom-provider adapters (non-OpenAI-compatible APIs)
        if provider == "anthropic":
            from .providers.anthropic import AnthropicAdapter
            adapter = AnthropicAdapter(config={"api_key_env": env_var}, name=f"{provider}-{model}")
            adapter.default_model = model
            self._adapters[tier] = adapter
            return adapter

        if provider == "vertex":
            from .providers.vertex import VertexAdapter
            adapter = VertexAdapter(config={"api_key_env": env_var}, name=f"{provider}-{model}")
            adapter.default_model = model
            self._adapters[tier] = adapter
            return adapter

        return None  # Unknown provider — caller handles
