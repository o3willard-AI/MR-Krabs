"""Maps MR-Krabs tier names to provider adapter instances.

Each tier in MODELS maps to either:
- An OpenAI-compatible provider (openrouter, lmstudio) → OpenAICompatibleAdapter
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
        self._tiers = get_models()
        self._adapters: Dict[str, LiteLLMAdapter] = {}

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

        if provider in ("openrouter", "lmstudio"):
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

        return None  # Unknown provider — caller handles
