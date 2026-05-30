from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """Adapter health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class AdapterError(Exception):
    """Base exception for all adapter errors."""
    pass


class AdapterInitError(AdapterError):
    """Raised when adapter initialization fails."""
    pass


class AdapterHealthError(AdapterError):
    """Raised when adapter health check fails."""
    pass


class AdapterConfigError(AdapterError):
    """Raised when adapter configuration is invalid."""
    pass


class AdapterNotFound(AdapterError):
    """Raised when a requested adapter is not found in the registry."""
    pass


class LiteLLMAdapter(ABC):
    """
    Base adapter for all LiteLLM-forked components.
    
    Every forked component (metrics, routing, caching, etc.) inherits from this class.
    Provides a consistent lifecycle, configuration contract, and error boundary.
    """
    
    def __init__(self, config: Any, name: str = "") -> None:
        """
        Args:
            config: MR-Krabs typed configuration object.
            name: Human-readable adapter identifier.
        """
        self._config = config
        self._name = name or self.__class__.__name__
        self._initialized = False
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def enabled(self) -> bool:
        """Whether this adapter is enabled via feature flags. Override per adapter."""
        return True
    
    @property
    def initialized(self) -> bool:
        return self._initialized
    
    @abstractmethod
    def initialize(self) -> bool:
        """Setup the adapter. Return True on success. Called once at startup."""
        ...
    
    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Check if the adapter is functioning correctly."""
        ...
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources. Called on graceful shutdown."""
        ...
    
    def get_config(
        self,
        key: str,
        default: Any = None,
        litellm_default: Any = None,
        env_var: str | None = None
    ) -> Any:
        """
        Config resolution with proper priority order:
        1. MR-Krabs config section (highest priority)
        2. LiteLLM default value
        3. Environment variable fallback (lowest priority)
        
        Args:
            key: Config key to look up.
            default: Ultimate fallback value.
            litellm_default: LiteLLM's default value for this setting.
            env_var: Optional environment variable name for fallback.
        """
        import os
        # Priority 1: MR-Krabs config
        value = self._config.get(key)
        if value is not None:
            return value
        # Priority 2: LiteLLM default
        if litellm_default is not None:
            return litellm_default
        # Priority 3: Environment variable
        if env_var and env_var in os.environ:
            return os.environ[env_var]
        return default
