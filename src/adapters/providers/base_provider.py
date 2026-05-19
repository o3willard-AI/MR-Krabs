"""Base provider adapter and OpenAI-compatible adapter.

Inspired by LiteLLM's adapter patterns but adapted for MR-Krabs.
Provides the foundation for all LLM provider integrations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional

from ..base_adapter import LiteLLMAdapter


@dataclass
class LLMResponse:
    """Standardized LLM response across all providers."""
    content: str
    model: str
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: Decimal = Decimal("0")
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    input_per_1k: Decimal = Decimal("0")
    output_per_1k: Decimal = Decimal("0")
    capabilities: List[str] = field(default_factory=list)
    status: str = "available"


@dataclass
class CostEstimate:
    """Estimated cost for a request."""
    min_cost: Decimal = Decimal("0")
    max_cost: Decimal = Decimal("0")
    expected_cost: Decimal = Decimal("0")
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class BaseProviderAdapter(LiteLLMAdapter, ABC):
    """Standard interface for all LLM provider integrations.
    
    Every provider adapter inherits from this class.
    Provides the contract for completion, streaming, model listing,
    token counting, and cost estimation.
    """
    
    # Subclasses must set these class variables
    provider_name: str = ""
    display_name: str = ""
    default_model: str = ""
    env_var: str = ""
    docs_url: str = ""
    
    def __init__(self, config=None, name: str = ""):
        super().__init__(config or {}, name or self.__class__.provider_name)
        self._api_key: Optional[str] = None
    
    def _get_api_key(self) -> str:
        """Get API key from config, env var, or vault."""
        import os
        if self._api_key:
            return self._api_key
        if self.env_var and self.env_var in os.environ:
            return os.environ[self.env_var]
        return self.get_config("api_key", default="", env_var=self.env_var)
    
    @abstractmethod
    async def complete(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs) -> LLMResponse:
        """Send a completion request to the provider."""
        ...
    
    @abstractmethod
    async def stream(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """Stream a completion from the provider."""
        ...
    
    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """List available models for this provider."""
        ...
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate that the adapter is properly configured."""
        ...
    
    def supports_feature(self, feature: str) -> bool:
        """Check if provider supports a feature: vision, function_calling, json_mode, streaming, system_message."""
        return False
    
    def token_count(self, messages: List[Dict[str, str]]) -> int:
        """Estimate token count. Override for accurate provider-specific counting."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4  # Rough estimate: ~4 chars per token
        return total
    
    def cost_estimate(self, model: str, token_count: int) -> CostEstimate:
        """Estimate cost for a request. Override per provider."""
        return CostEstimate(model=model, input_tokens=token_count)
    
    def initialize(self) -> bool:
        self._initialized = True
        return True
    
    def health_check(self):
        from ..base_adapter import HealthStatus
        return HealthStatus.HEALTHY if self._initialized else HealthStatus.DOWN
    
    def shutdown(self) -> None:
        self._initialized = False


class OpenAICompatibleAdapter(BaseProviderAdapter):
    """Base class for any provider with an OpenAI-compatible chat completions API.
    
    Subclass and set: provider_name, base_url, default_model, env_var.
    Most providers (~70 of 80+) use this path without custom code.
    """
    
    base_url: str = ""
    
    def __init__(self, config=None, name: str = ""):
        super().__init__(config, name)
        self._base_url = self.base_url or self.get_config("base_url", default="")
    
    async def complete(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs) -> LLMResponse:
        import aiohttp, time, os
        
        model = model or self.default_model
        api_key = self._get_api_key()
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
        }
        
        start = time.monotonic()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                latency = (time.monotonic() - start) * 1000
                
                if resp.status != 200:
                    error_msg = data.get("error", {}).get("message", str(data))
                    raise Exception(f"Provider error {resp.status}: {error_msg}")
                
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
    
    async def stream(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        import aiohttp
        
        model = model or self.default_model
        api_key = self._get_api_key()
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                async for line in resp.content:
                    text = line.decode("utf-8").strip()
                    if text.startswith("data: "):
                        data_str = text[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except Exception:
                            continue
    
    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(name=self.default_model),
        ]
    
    def validate_config(self) -> bool:
        return bool(self._base_url)
    
    def supports_feature(self, feature: str) -> bool:
        supported = {"streaming", "system_message"}
        return feature in supported