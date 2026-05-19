"""Mistral AI provider adapter."""
from __future__ import annotations
import time
from typing import AsyncIterator, List, Optional
from .base_provider import BaseProviderAdapter, LLMResponse, ModelInfo

class MistralAdapter(BaseProviderAdapter):
    provider_name = "mistral"
    display_name = "Mistral AI"
    default_model = "mistral-small-latest"
    env_var = "MISTRAL_API_KEY"
    docs_url = "https://docs.mistral.ai/api/"

    def __init__(self, config=None, name=""):
        super().__init__(config, name or "mistral")
        self._base_url = "https://api.mistral.ai/v1"

    async def complete(self, messages, model=None, **kwargs):
        import aiohttp
        api_key = self._get_api_key()
        model = model or self.default_model
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        start = time.monotonic()
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/chat/completions", json=payload, headers=headers) as resp:
                data = await resp.json()
                latency = (time.monotonic() - start) * 1000
                
                if resp.status != 200:
                    error = data.get("error", {}).get("message", str(data))
                    raise Exception(f"Mistral error {resp.status}: {error}")
                
                choice = data["choices"][0]
                usage = data.get("usage", {})
                
                return LLMResponse(
                    content=choice["message"]["content"],
                    model=data.get("model", model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    tokens_used=usage.get("total_tokens", 0),
                    finish_reason=choice.get("finish_reason", "stop"),
                    latency_ms=latency,
                    raw_response=data,
                )

    async def stream(self, messages, model=None, **kwargs):
        import aiohttp, json
        api_key = self._get_api_key()
        model = model or self.default_model
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/chat/completions", json=payload, headers=headers) as resp:
                async for line in resp.content:
                    text = line.decode().strip()
                    if text.startswith("data: "):
                        data_str = text[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except Exception:
                            continue

    def list_models(self):
        return [
            ModelInfo(name="mistral-large-latest", context_window=131072, max_output_tokens=8192),
            ModelInfo(name="mistral-medium-latest", context_window=131072, max_output_tokens=8192),
            ModelInfo(name="mistral-small-latest", context_window=32768, max_output_tokens=4096),
        ]

    def validate_config(self):
        return bool(self._get_api_key())