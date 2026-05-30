from typing import Dict, List

from .base_adapter import LiteLLMAdapter, AdapterNotFound, HealthStatus


class AdapterRegistry:
    """
    Singleton registry for all LiteLLM adapters.
    Supports registration, lookup, and bulk health checks.
    """
    
    _instance: "AdapterRegistry | None" = None
    _adapters: Dict[str, LiteLLMAdapter]
    
    def __new__(cls) -> "AdapterRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
        return cls._instance
    
    def register(self, adapter: LiteLLMAdapter) -> None:
        """Register an adapter. Idempotent — no duplicates."""
        self._adapters[adapter.name] = adapter
    
    def get(self, name: str) -> LiteLLMAdapter:
        """Get an adapter by name. Raises AdapterNotFound if missing."""
        if name not in self._adapters:
            raise AdapterNotFound(f"Adapter '{name}' not found in registry")
        return self._adapters[name]
    
    def get_all(self) -> List[LiteLLMAdapter]:
        """Return all registered adapters."""
        return list(self._adapters.values())
    
    def health_check_all(self) -> Dict[str, HealthStatus]:
        """Check health of all registered adapters."""
        return {name: adapter.health_check() for name, adapter in self._adapters.items()}
    
    def initialize_all(self) -> Dict[str, bool]:
        """Initialize all adapters that are enabled. Returns success map."""
        results = {}
        for name, adapter in self._adapters.items():
            if adapter.enabled:
                try:
                    results[name] = adapter.initialize()
                except Exception as e:
                    results[name] = False
            else:
                results[name] = True  # Disabled adapters count as "initialized"
        return results
    
    def shutdown_all(self) -> None:
        """Shutdown all initialized adapters."""
        for adapter in self._adapters.values():
            if adapter.initialized:
                try:
                    adapter.shutdown()
                except Exception:
                    pass  # Best-effort shutdown
