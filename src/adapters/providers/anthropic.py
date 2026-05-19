"""Anthropic provider adapter (custom Messages API)."""
from __future__ import annotations
import time
from typing import AsyncIterator, List, Optional
from .base_provider import BaseProviderAdapter, LLMResponse, ModelInfo

class AnthropicAdapter(BaseProviderAdapter):
    provider_name = "anthropic"
    display_name = "Anthropic"
    default_model = "claude-sonnet-4-20250514"
    env_var = "ANTHROPIC_API_KEY"
    docs_url = "https://docs.anthropic.com/en/api"

    def __init__(self, config=None, name: str = ""):
        super().__init__(config, name or "anthropic")
        self._base_url = "https://api.anthropic.com/v1"

    async def complete(self, messages, model=None, **kwargs):
        import aiohttp
        api_key = self._get_api_key()
        model = model or self.default_model
        
        # Anthropic uses a top-level system field, not a message
        system = None
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})
        
        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        if system:
            payload["system"] = system
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        start = time.monotonic()
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/messages", json=payload, headers=headers) as resp:
                data = await resp.json()
                latency = (time.monotonic() - start) * 1000
                
                if resp.status != 200:
                    error = data.get("error", {}).get("message", str(data))
                    raise Exception(f"Anthropic error {resp.status}: {error}")
                
                content_blocks = data.get("content", [])
                text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                
                return LLMResponse(
                    content=text,
                    model=data.get("model", model),
                    prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
                    completion_tokens=data.get("usage", {}).get("output_tokens", 0),
                    tokens_used=(data.get("usage", {}).get("input_tokens", 0) + 
                                data.get("usage", {}).get("output_tokens", 0)),
                    finish_reason=data.get("stop_reason", "stop"),
                    latency_ms=latency,
                    raw_response=data,
                )

    async def stream(self, messages, model=None, **kwargs):
        import aiohttp, json
        api_key = self._get_api_key()
        model = model or self.default_model
        
        system = None
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})
        
        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
        }
        if system:
            payload["system"] = system
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/messages", json=payload, headers=headers) as resp:
                async for line in resp.content:
                    text = line.decode().strip()
                    if text.startswith("data: "):
                        data_str = text[6:]
                        try:
                            event = json.loads(data_str)
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except Exception:
                            continue

    def list_models(self):
        return [
            ModelInfo(name="claude-sonnet-4-20250514", context_window=200000, max_output_tokens=8192),
            ModelInfo(name="claude-opus-4-20250514", context_window=200000, max_output_tokens=8192),
            ModelInfo(name="claude-haiku-3-5", context_window=200000, max_output_tokens=8192),
        ]

    def validate_config(self):
        return bool(self._get_api_key())

    def supports_feature(self, feature):
        return feature in {"streaming", "system_message", "vision", "function_calling"}