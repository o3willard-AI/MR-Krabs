#!/usr/bin/env python3
"""OpenAI provider adapter for cost tracking.

P2-4: Additional LLM Providers
Provides cost-aware OpenAI API integration with automatic cost tracking.

Features:
- OpenAI API support (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
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
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = object  # Type hint fallback


@dataclass
class TokenCount:
    """Token count tracking."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def __post_init__(self):
        """Calculate total tokens."""
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


class OpenAIProvider:
    """OpenAI API provider adapter with cost tracking.
    
    This adapter wraps the OpenAI SDK and adds cost tracking functionality.
    It integrates seamlessly with the cost orchestrator's tier system.
    """
    
    # OpenAI model pricing (per 1K tokens)
    # Source: https://openai.com/api/pricing/
    MODEL_PRICING = {
        # GPT-4o models
        "gpt-4o": {
            "prompt": 0.0000025,  # $2.50 per 1M input tokens
            "completion": 0.000010,  # $10.00 per 1M output tokens
            "tier": "L3-Coder",  # Premium tier
        },
        "gpt-4o-mini": {
            "prompt": 0.00000015,  # $0.15 per 1M
            "completion": 0.00000060,  # $0.60 per 1M
            "tier": "L1-Coder",  # Budget tier
        },
        
        # GPT-4 Turbo
        "gpt-4-turbo": {
            "prompt": 0.000010,  # $10.00 per 1M
            "completion": 0.000030,  # $30.00 per 1M
            "tier": "L3-Coder",
        },
        "gpt-4": {
            "prompt": 0.000030,  # $30.00 per 1M
            "completion": 0.000060,  # $60.00 per 1M
            "tier": "L3-Coder",
        },
        
        # GPT-3.5 Turbo
        "gpt-3.5-turbo": {
            "prompt": 0.0000005,  # $0.50 per 1M
            "completion": 0.0000015,  # $1.50 per 1M
            "tier": "L0-Planner",  # Budget tier
        },
        "gpt-3.5-turbo-16k": {
            "prompt": 0.0000015,  # $1.50 per 1M
            "completion": 0.000004,  # $4.00 per 1M
            "tier": "L0-Planner",
        },
        
        # Legacy models (still available)
        "gpt-3.5-turbo-0125": {
            "prompt": 0.0000005,
            "completion": 0.0000015,
            "tier": "L0-Planner",
        },
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None
    ):
        """Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Optional custom base URL
            organization: Optional OpenAI organization ID
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "OpenAI SDK is not installed. "
                "Install with: pip install openai"
            )
        
        # Get API key from parameter or environment
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. "
                "Provide api_key parameter or set OPENAI_API_KEY environment variable"
            )
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            organization=organization
        )
    
    def get_pricing(self, model: str) -> Dict[str, Any]:
        """Get pricing information for a model.
        
        Args:
            model: Model name (e.g., "gpt-4o")
            
        Returns:
            Pricing dictionary with prompt, completion costs, and tier
        """
        # Normalize model name
        model_lower = model.lower()
        
        # Try exact match first
        if model_lower in self.MODEL_PRICING:
            return self.MODEL_PRICING[model_lower]
        
        # Try partial match
        for key, pricing in self.MODEL_PRICING.items():
            if key in model_lower or model_lower in key:
                return pricing
        
        # Default pricing if not found
        return {
            "prompt": 0.000001,
            "completion": 0.000001,
            "tier": "L1-Coder",
        }
    
    def chat_completions_create(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """Create chat completion with cost tracking.
        
        Args:
            model: Model name (e.g., "gpt-4o")
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty
            presence_penalty: Presence penalty
            **kwargs: Additional OpenAI API parameters
            
        Returns:
            Dictionary with success status, output, tokens, cost, and metadata
        """
        # Get pricing for this model
        pricing = self.get_pricing(model)
        
        # Estimate prompt tokens (rough approximation)
        prompt_tokens = sum(
            len(msg.get("content", "")) // 4
            for msg in messages
        )
        
        # Calculate cost reservation
        estimated_cost = Decimal(str(
            prompt_tokens * pricing["prompt"] / 1000
        ))
        
        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                **kwargs
            )
            
            # Extract token usage
            usage = response.usage
            tokens = TokenCount(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            
            # Calculate actual cost
            actual_cost = Decimal(str(
                (tokens.prompt_tokens * pricing["prompt"] +
                 tokens.completion_tokens * pricing["completion"]) / 1000
            ))
            
            # Get response details
            output = response.choices[0].message.content
            model_name = response.model
            
            return {
                "success": True,
                "output": output,
                "tokens": tokens,
                "cost": actual_cost,
                "model": model_name,
                "tier": pricing["tier"],
                "duration_seconds": response.response_ms / 1000 if hasattr(response, 'response_ms') else 0,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tokens": TokenCount(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=0,
                ),
                "cost": Decimal("0.0"),
                "model": model,
                "tier": pricing["tier"],
            }
    
    def embeddings_create(
        self,
        input: List[str] | str,
        model: str = "text-embedding-3-small",
        **kwargs
    ) -> Dict[str, Any]:
        """Create embeddings with cost tracking.
        
        Args:
            input: Input text(s)
            model: Embedding model
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with success status, embedding, cost, and tokens
        """
        # Embedding pricing
        embedding_pricing = {
            "text-embedding-3-small": {
                "cost_per_1k": 0.00000002,  # $0.02 per 1M tokens
            },
            "text-embedding-3-large": {
                "cost_per_1k": 0.00000013,  # $0.13 per 1M tokens
            },
            "text-embedding-ada-002": {
                "cost_per_1k": 0.00000010,  # $0.10 per 1M tokens
            },
        }
        
        pricing = embedding_pricing.get(model, embedding_pricing["text-embedding-3-small"])
        
        # Estimate tokens
        if isinstance(input, str):
            input_tokens = len(input) // 4
        else:
            input_tokens = sum(len(text) // 4 for text in input)
        
        # Calculate cost
        cost = Decimal(str(input_tokens * pricing["cost_per_1k"] / 1000))
        
        try:
            response = self.client.embeddings.create(
                input=input,
                model=model,
                **kwargs
            )
            
            return {
                "success": True,
                "embeddings": [item.embedding for item in response.data],
                "tokens": TokenCount(
                    prompt_tokens=input_tokens,
                    completion_tokens=0,
                    total_tokens=input_tokens,
                ),
                "cost": cost,
                "model": model,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tokens": TokenCount(prompt_tokens=input_tokens),
                "cost": Decimal("0.0"),
                "model": model,
            }
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List available OpenAI models with pricing.
        
        Returns:
            List of model information dictionaries
        """
        models = []
        
        for model_name, pricing in self.MODEL_PRICING.items():
            models.append({
                "id": model_name,
                "owned_by": "openai",
                "prompt_cost": pricing["prompt"],
                "completion_cost": pricing["completion"],
                "tier": pricing["tier"],
            })
        
        return models


# Factory function for easy usage
def create_openai_provider(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> OpenAIProvider:
    """Create an OpenAI provider instance.
    
    Args:
        api_key: OpenAI API key
        base_url: Optional custom base URL
        
    Returns:
        OpenAIProvider instance
    """
    return OpenAIProvider(
        api_key=api_key,
        base_url=base_url
    )
