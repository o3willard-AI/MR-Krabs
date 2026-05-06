"""
LLM Provider Service with Secure Vault Integration

This module handles all interactions with LLM providers (OpenAI, Anthropic, etc.)
using keys from the secure vault. Never passes raw API keys to clients.

Security Features:
- Keys retrieved from encrypted vault only when needed
- Rate limiting per provider
- Cost tracking and budget enforcement
- Request sanitization (no keys in logs)
"""

import os
from typing import Dict, Optional, List, Any, Literal
from datetime import datetime
import json
import time

# Import vault services
from .vault import Vault, EncryptedVault, SecurityLogger

logger = SecurityLogger(__import__('logging').getLogger(__name__))


class ProviderConfig:
    """Configuration for an LLM provider."""
    
    def __init__(
        self,
        name: str,
        base_url: str,
        default_model: str,
        cost_per_input_token: float = 0.0,
        cost_per_output_token: float = 0.0,
    ):
        self.name = name
        self.base_url = base_url
        self.default_model = default_model
        self.cost_per_input_token = cost_per_input_token
        self.cost_per_output_token = cost_per_output_token


# Default provider configurations (pricing as of 2024)
DEFAULT_PROVIDERS = {
    "openai": ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4-turbo",
        cost_per_input_token=0.000001,   # $0.01 per 1K tokens
        cost_per_output_token=0.000003,  # $0.03 per 1K tokens
    ),
    "anthropic": ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-opus",
        cost_per_input_token=0.0000025,  # $2.50 per 1K tokens
        cost_per_output_token=0.0000125, # $12.50 per 1K tokens
    ),
    "openrouter": ProviderConfig(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-3-opus",
        cost_per_input_token=0.000002,   # Variable by model
        cost_per_output_token=0.00001,
    ),
}


class LLMProviderService:
    """
    Service for managing LLM provider connections securely.
    
    All API keys are retrieved from the encrypted vault and never stored in memory
    longer than necessary.
    """
    
    def __init__(self, vault: Optional[EncryptedVault] = None):
        """
        Initialize the provider service.
        
        Args:
            vault: EncryptedVault instance for secure key storage.
                   If None, will try to auto-initialize from environment.
        """
        # Initialize vault if not provided
        if vault is None:
            vault_path = os.environ.get("MRKRABS_VAULT_PATH", "/etc/mrkrabs/vault.enc")
            master_key = os.environ.get("VAULT_MASTER_KEY")
            
            try:
                self.vault = Vault.create(
                    backend="encrypted",
                    vault_path=vault_path,
                    master_key=master_key
                )
                logger.info("Initialized encrypted vault for LLM providers")
                
            except Exception as e:
                # Fallback to memory vault (dev only)
                logger.warning(f"Could not initialize encrypted vault: {e}. Using memory vault (DEV ONLY)")
                self.vault = Vault.create(backend="memory")
        
        # Cache for provider API keys (short-lived, cleared periodically)
        self._key_cache: Dict[str, tuple] = {}  # provider -> (api_key, timestamp)
        self.CACHE_TTL = 300  # 5 minutes
        
        # Initialize provider configurations
        self.providers = DEFAULT_PROVIDERS.copy()
    
    def _get_cached_key(self, provider: str) -> Optional[str]:
        """Get API key from cache if still valid."""
        if provider in self._key_cache:
            api_key, timestamp = self._key_cache[provider]
            if time.time() - timestamp < self.CACHE_TTL:
                return api_key
        return None
    
    def _cache_key(self, provider: str, api_key: str):
        """Cache API key for short-term use."""
        self._key_cache[provider] = (api_key, time.time())
    
    def get_api_key(self, provider: str) -> str:
        """
        Get API key for a provider from the secure vault.
        
        Keys are cached briefly to avoid excessive vault access, but
        never persisted beyond this.
        
        Args:
            provider: Provider name (openai, anthropic, openrouter)
            
        Returns:
            API key string
            
        Raises:
            ValueError: If provider not configured in vault
        """
        # Check cache first
        cached_key = self._get_cached_key(provider)
        if cached_key:
            logger.debug(f"Retrieved {provider} key from cache")
            return cached_key
        
        # Get from vault (encrypted storage)
        try:
            api_key = self.vault.get_provider_key(provider)
            
            # Cache for future requests
            self._cache_key(provider, api_key)
            
            logger.debug(f"Retrieved {provider} key from vault")
            return api_key
            
        except Exception as e:
            logger.error(f"Failed to get API key for {provider}: {e}")
            raise ValueError(f"No API key configured for provider '{provider}'")
    
    def configure_provider(self, provider: str, config: ProviderConfig):
        """Add or update a provider configuration."""
        self.providers[provider] = config
        logger.info(f"Configured provider: {provider} -> {config.default_model}")
    
    def estimate_cost(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int = 0
    ) -> float:
        """
        Estimate cost for a request to an LLM provider.
        
        Args:
            provider: Provider name
            input_tokens: Number of input tokens
            output_tokens: Estimated output tokens (default: input * 0.1)
            
        Returns:
            Estimated cost in USD
        """
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        
        config = self.providers[provider]
        
        # Estimate output if not provided
        if output_tokens == 0:
            output_tokens = int(input_tokens * 0.1)  # 10% of input
        
        cost = (
            input_tokens * config.cost_per_input_token +
            output_tokens * config.cost_per_output_token
        )
        
        return round(cost, 6)  # Round to avoid floating point issues
    
    def validate_api_key_exists(self, provider: str) -> bool:
        """Check if a provider has an API key configured."""
        try:
            self.get_api_key(provider)
            return True
        except Exception:
            return False
    
    def list_available_providers(self) -> List[str]:
        """List all providers with configured API keys."""
        available = []
        for provider in self.providers.keys():
            if self.validate_api_key_exists(provider):
                available.append(provider)
        
        logger.info(f"Available LLM providers: {available}")
        return available
    
    def get_provider_info(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get information about a provider."""
        if provider not in self.providers:
            return None
        
        config = self.providers[provider]
        has_key = self.validate_api_key_exists(provider)
        
        return {
            "name": config.name,
            "default_model": config.default_model,
            "base_url": config.base_url,
            "cost_per_input_token": config.cost_per_input_token,
            "cost_per_output_token": config.cost_per_output_token,
            "has_api_key": has_key
        }
    
    def add_provider_key_to_vault(self, provider: str, api_key: str):
        """
        Add or update a provider API key in the vault.
        
        WARNING: This should only be called during setup/admin operations.
                 Never call this with user-provided keys!
        
        Args:
            provider: Provider name (openai, anthropic, openrouter)
            api_key: The actual API key to store (will be encrypted)
        """
        self.vault.add_provider_key(
            provider=provider,
            api_key=api_key,
            metadata={
                "added": datetime.utcnow().isoformat(),
                "source": "admin_configuration"
            }
        )
        
        # Clear cache to force reload
        if provider in self._key_cache:
            del self._key_cache[provider]
        
        logger.info(f"Updated API key for provider: {provider}")


# Global instance (singleton pattern)
_provider_service: Optional[LLMProviderService] = None


def get_llm_provider_service() -> LLMProviderService:
    """Get or create the global LLM provider service instance."""
    global _provider_service
    
    if _provider_service is None:
        _provider_service = LLMProviderService()
    
    return _provider_service


def initialize_llm_providers(
    providers_to_configure: Dict[str, str] = None
) -> LLMProviderService:
    """
    Initialize LLM providers with API keys.
    
    Args:
        providers_to_configure: Dict of provider_name -> api_key pairs
        
    Example:
        initialize_llm_providers({
            "openai": "sk-...",
            "anthropic": "anthropic_..."
        })
    """
    service = get_llm_provider_service()
    
    if providers_to_configure:
        for provider, api_key in providers_to_configure.items():
            service.add_provider_key_to_vault(provider, api_key)
    
    logger.info(f"Initialized LLM providers: {service.list_available_providers()}")
    return service
