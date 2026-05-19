import pytest
from src.adapters.base_adapter import (
    LiteLLMAdapter, HealthStatus, AdapterNotFound,
    AdapterError, AdapterInitError, AdapterHealthError, AdapterConfigError
)
from src.adapters.registry import AdapterRegistry


class MockAdapter(LiteLLMAdapter):
    """Concrete adapter for testing."""
    def __init__(self, config=None, name="mock"):
        super().__init__(config or {}, name)
        self._healthy = True
    
    def initialize(self) -> bool:
        self._initialized = True
        return True
    
    def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._healthy else HealthStatus.DOWN
    
    def shutdown(self) -> None:
        self._initialized = False


class TestLiteLLMAdapter:
    def test_adapter_name_defaults_to_class_name(self):
        adapter = MockAdapter()
        assert adapter.name == "mock"
    
    def test_adapter_custom_name(self):
        adapter = MockAdapter(name="test_adapter")
        assert adapter.name == "test_adapter"
    
    def test_adapter_not_initialized_by_default(self):
        adapter = MockAdapter()
        assert not adapter.initialized
    
    def test_adapter_initialized_after_initialize(self):
        adapter = MockAdapter()
        result = adapter.initialize()
        assert result is True
        assert adapter.initialized
    
    def test_adapter_shutdown(self):
        adapter = MockAdapter()
        adapter.initialize()
        adapter.shutdown()
        assert not adapter.initialized
    
    def test_adapter_enabled_by_default(self):
        adapter = MockAdapter()
        assert adapter.enabled is True
    
    def test_get_config_from_config_dict(self):
        adapter = MockAdapter(config={"key": "value"})
        assert adapter.get_config("key") == "value"
    
    def test_get_config_fallback_to_default(self):
        adapter = MockAdapter(config={})
        assert adapter.get_config("missing", default="fallback") == "fallback"
    
    def test_get_config_litellm_default_priority(self):
        adapter = MockAdapter(config={})
        assert adapter.get_config("key", litellm_default="litellm_val") == "litellm_val"
    
    def test_get_config_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "env_value")
        adapter = MockAdapter(config={})
        assert adapter.get_config("key", env_var="TEST_VAR") == "env_value"
    
    def test_get_config_priority_order(self):
        """Config > LiteLLM default > env var > fallback default"""
        import os
        adapter = MockAdapter(config={"key": "config_val"})
        os.environ["TEST_VAR"] = "env_value"
        result = adapter.get_config(
            "key", 
            default="fallback", 
            litellm_default="litellm_val", 
            env_var="TEST_VAR"
        )
        assert result == "config_val"  # Config wins over everything


class TestHealthStatus:
    def test_health_status_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.DOWN.value == "down"


class TestAdapterRegistry:
    def test_register_and_get_adapter(self):
        registry = AdapterRegistry()
        adapter = MockAdapter(name="test")
        registry.register(adapter)
        assert registry.get("test") is adapter
    
    def test_get_missing_adapter_raises(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterNotFound):
            registry.get("nonexistent")
    
    def test_get_all_adapters(self):
        # Create fresh instance to avoid singleton pollution from other tests
        from importlib import reload
        import src.adapters.registry as registry_module
        reload(registry_module)
        from src.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        a1 = MockAdapter(name="a1")
        a2 = MockAdapter(name="a2")
        registry.register(a1)
        registry.register(a2)
        all_adapters = registry.get_all()
        assert len(all_adapters) == 2
    
    def test_health_check_all(self):
        registry = AdapterRegistry()
        adapter = MockAdapter(name="test")
        registry.register(adapter)
        results = registry.health_check_all()
        assert results["test"] == HealthStatus.HEALTHY
    
    def test_initialize_all(self):
        registry = AdapterRegistry()
        adapter = MockAdapter(name="test")
        registry.register(adapter)
        results = registry.initialize_all()
        assert results["test"] is True
        assert adapter.initialized
    
    def test_shutdown_all(self):
        registry = AdapterRegistry()
        adapter = MockAdapter(name="test")
        registry.register(adapter)
        registry.initialize_all()
        registry.shutdown_all()
        assert not adapter.initialized
