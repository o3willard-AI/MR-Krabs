"""Groq provider adapter (OpenAI-compatible API)."""
from .base_provider import OpenAICompatibleAdapter, ModelInfo
from typing import List

class GroqAdapter(OpenAICompatibleAdapter):
    provider_name = "groq"
    display_name = "Groq"
    default_model = "llama-4-scout-17b-16e"
    env_var = "GROQ_API_KEY"
    base_url = "https://api.groq.com/openai/v1"
    docs_url = "https://console.groq.com/docs"

    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(name="llama-4-scout-17b-16e", context_window=131072, max_output_tokens=8192),
            ModelInfo(name="llama-4-maverick-17b-128e", context_window=131072, max_output_tokens=8192),
            ModelInfo(name="mixtral-8x7b-32768", context_window=32768, max_output_tokens=4096),
        ]