#!/usr/bin/env python3
"""Anthropic provider adapter for cost tracking.

P2-4: Additional LLM Providers
Provides cost-aware Anthropic API integration with automatic cost tracking.

Features:
- Anthropic API support (Claude 3 family)
- Accurate pricing configuration
- Token usage tracking
- Integration with existing tier system
- Budget enforcement
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import anthropic
    from anthropic import Anthropic
    from anthropic.types import Message, Usage
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = object  # Type hint fallback


@dataclass
class TokenCount:
    """Token count tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def __post_init__(self):
        """Calculate total tokens."""
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


class AnthropicProvider:
    """Anthropic API provider adapter with cost tracking.
    
    This adapter wraps the Anthropic SDK and adds cost tracking functionality.
    It integrates seamlessly with the cost orchestrator's tier system.
    """
    
    # Claude model pricing (per 1K tokens)
    # Source: https://www.anthropic.com/pricing
    MODEL_PRICING = {
        # Claude 3.5 Sonnet
        "claude-3-5-sonnet-latest": {
            "prompt": 0.000003,  # $3.00 per 1M input tokens
            "completion": 0.000015,  # $15.00 per 1M output tokens
            "tier": "L2-Coder",  # High-quality tier
        },
        "claude-3-5-sonnet-20241022": {
            "prompt": 0.000003,
            "completion": 0.000015,
            "tier": "L2-Coder",
        },
        
        # Claude 3 Opus
        "claude-3-opus-latest": {
            "prompt": 0.000015,  # $15.00 per 1M
            "completion": 0.000075,  # $75.00 per 1M
            "tier": "L3-Coder",  # Premium tier
        },
        "claude-3-opus-20240229": {
            "prompt": 0.000015,
            "completion": 0.000075,
            "tier": "L3-Coder",
        },
        
        # Claude 3 Sonnet
        "claude-3-sonnet-latest": {
            "prompt": 0.000003,  # $3.00 per 1M
            "completion": 0.000015,  # $15.00 per 1M
            "tier": "L1-Coder",  # Balanced tier
        },
        "claude-3-sonnet-20240229": {
            "prompt": 0.000003,
            "completion": 0.000015,
            "tier": "L1-Coder",
        },
        
        # Claude 3 Haiku
        "claude-3-haiku-latest": {
            "prompt": 0.00000025,  # $0.25 per 1M
            "completion": 0.00000125,  # $1.25 per 1M
            "tier": "L0-Planner",  # Budget tier
        },
        "claude-3-haiku-20240307": {
            "prompt": 0.00000025,
            "completion": 0.00000125,
            "tier": "L0-Planner",
        },
        
        # Claude 2 (legacy)
        "claude-2.1": {
            "prompt": 0.000008,
            "completion": 0.000024,
            "tier": "L1-Coder",
        },
        "claude-2.0": {
            "prompt": 0.000008,
            "completion": 0.000024,
            "tier": "L1-Coder",
        },
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None
    ):
        """Initialize Anthropic provider.
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: Optional custom base URL
            organization: Optional organization ID
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "Anthropic SDK is not installed. "
                "Install with: pip install anthropic"
            )
        
        # Get API key from parameter or environment
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. "
                "Provide api_key parameter or set ANTHROPIC_API_KEY environment variable"
            )
        
        # Initialize Anthropic client (organization parameter may not be available in newer versions)
        try:
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=base_url,
                organization=organization
            )
        except TypeError:
            # organization parameter not supported, use without it
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=base_url
            )
    
    def get_pricing(self, model: str) -> Dict[str, Any]:
        """Get pricing information for a model.
        
        Args:
            model: Model name (e.g., "claude-3-5-sonnet-latest")
            
        Returns:
            Pricing dictionary with input, output costs, and tier
        """
        # Normalize model name
        model_lower = model.lower()
        
        # Try exact match first
        if model_lower in self.MODEL_PRICING:
            return self.MODEL_PRICING[model_lower]
        
        # Try partial match (remove "-latest" suffix if present)
        base_model = model_lower.replace("-latest", "")
        if base_model in self.MODEL_PRICING:
            return self.MODEL_PRICING[base_model]
        
        # Try substring match
        for key, pricing in self.MODEL_PRICING.items():
            key_base = key.lower().replace("-latest", "")
            if key_base in model_lower or model_lower in key_base:
                return pricing
        
        # Default pricing if not found
        return {
            "prompt": 0.000001,
            "completion": 0.000001,
            "tier": "L1-Coder",
        }
    
    def messages_create(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 5,
        stop_sequences: Optional[List[str]] = None,
        system: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Create message with cost tracking.
        
        Args:
            model: Model name (e.g., "claude-3-5-sonnet-latest")
            messages: List of message dictionaries with role and content
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            stop_sequences: Optional stop sequences
            system: Optional system message
            stream: Whether to stream the response
            **kwargs: Additional Anthropic API parameters
            
        Returns:
            Dictionary with success status, output, tokens, cost, and metadata
        """
        # Get pricing for this model
        pricing = self.get_pricing(model)
        
        # Estimate input tokens (rough approximation)
        input_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                input_tokens += len(content) // 4
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        input_tokens += len(item.get("text", "")) // 4
        
        try:
            # Prepare message parameters
            params = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
            }
            
            if system:
                params["system"] = system
            
            if stop_sequences:
                params["stop_sequences"] = stop_sequences
            
            # Call Anthropic API (non-streaming)
            if stream:
                # Streaming mode (simplified - just returns first chunk)
                response = self.client.messages.create(stream=True, **params)
                full_content = ""
                for chunk in response:
                    if chunk.type == "content_block_delta":
                        full_content += chunk.delta.text
                
                output = full_content
                tokens = TokenCount(
                    input_tokens=input_tokens,
                    output_tokens=len(full_content) // 4,
                )
            else:
                # Non-streaming mode
                response = self.client.messages.create(**params)
                
                output = response.content[0].text if response.content else ""
                
                # Extract token usage
                usage = response.usage
                tokens = TokenCount(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.input_tokens + usage.output_tokens,
                )
            
            # Calculate actual cost
            actual_cost = Decimal(str(
                (tokens.input_tokens * pricing["prompt"] +
                 tokens.output_tokens * pricing["completion"]) / 1000
            ))
            
            return {
                "success": True,
                "output": output,
                "tokens": tokens,
                "cost": actual_cost,
                "model": response.model,
                "tier": pricing["tier"],
                "duration_seconds": 0,  # Anthropic doesn't provide duration
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tokens": TokenCount(input_tokens=input_tokens),
                "cost": Decimal("0.0"),
                "model": model,
                "tier": pricing["tier"],
            }
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List available Anthropic models with pricing.
        
        Returns:
            List of model information dictionaries
        """
        models = []
        
        for model_name, pricing in self.MODEL_PRICING.items():
            models.append({
                "id": model_name,
                "owned_by": "anthropic",
                "input_cost": pricing["prompt"],
                "output_cost": pricing["completion"],
                "tier": pricing["tier"],
            })
        
        return models


# Factory function for easy usage
def create_anthropic_provider(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> AnthropicProvider:
    """Create an Anthropic provider instance.
    
    Args:
        api_key: Anthropic API key
        base_url: Optional custom base URL
        
    Returns:
        AnthropicProvider instance
    """
    return AnthropicProvider(
        api_key=api_key,
        base_url=base_url
    )
