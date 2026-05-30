"""DeepSeek provider adapter (OpenAI-compatible API)."""
from .base_provider import OpenAICompatibleAdapter, ModelInfo
from typing import List

class DeepSeekAdapter(OpenAICompatibleAdapter):
    provider_name = "deepseek"
    display_name = "DeepSeek"
    default_model = "deepseek-chat"
    env_var = "DEEPSEEK_API_KEY"
    base_url = "https://api.deepseek.com/v1"
    docs_url = "https://platform.deepseek.com/api-docs"

    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(name="deepseek-chat", context_window=65536, max_output_tokens=8192),
            ModelInfo(name="deepseek-reasoner", context_window=65536, max_output_tokens=8192,
                     capabilities=["reasoning"]),
        ]