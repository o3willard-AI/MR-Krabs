"""Phase 0: Harness self-validation tests.

Verify that the integration test infrastructure works correctly:
- MockCore is importable and functional
- Adapter base class can be instantiated with mock config
- Registry accepts and retrieves mock adapters
- Feature flag toggles correctly enable/disable adapters
"""

import pytest
from src.adapters import LiteLLMAdapter, AdapterRegistry, HealthStatus


class _MockTestAdapter(LiteLLMAdapter):
    """Minimal concrete adapter for harness testing."""

    def __init__(self, config=None, name="harness_test"):
        super().__init__(config or {}, name)
        self._healthy = True
        self._initialized = False

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._healthy else HealthStatus.DOWN

    def shutdown(self) -> None:
        self._initialized = False


class TestHarnessMockCore:
    """Verify MockMrKrabsCore works correctly."""

    def test_mock_core_returns_default_response(self, mock_core):
        result = mock_core.ask("test task")
        assert result["success"] is True
        assert "output" in result
        assert "cost" in result
        assert result["tier_used"] == "L0-Coder"

    def test_mock_core_queued_response(self, mock_core):
        mock_core.queue_ask_response({
            "output": "custom", 
            "cost": 0.05, 
            "success": True, 
            "tier_used": "L1-Coder", 
            "attempts": 2
        })
        result = mock_core.ask("anything")
        assert result["output"] == "custom"
        assert result["cost"] == 0.05

    def test_mock_core_queued_error(self, mock_core):
        mock_core.queue_ask_error(ValueError("test error"))
        with pytest.raises(ValueError, match="test error"):
            mock_core.ask("anything")

    def test_mock_core_tracks_call_count(self, mock_core):
        mock_core.ask("first")
        mock_core.ask("second")
        assert mock_core._call_count == 2

    def test_mock_core_vault(self, mock_core):
        mock_core.set_vault_entry("/test/key", "secret_value")
        assert mock_core.get_vault("/test/key") == "secret_value"
        assert mock_core.get_vault("/nonexistent") is None

    def test_mock_core_budget(self, mock_core):
        assert mock_core.get_budget_remaining() == 10.00
        mock_core.set_budget(3.50)
        assert mock_core.get_budget_remaining() == 3.50


class TestHarnessAdapterBase:
    """Verify adapter base class works with mock config."""

    def test_adapter_instantiation_with_mock_config(self, mock_config):
        adapter = _MockTestAdapter(config=mock_config)
        assert adapter.name == "harness_test"
        assert adapter.enabled is True

    def test_adapter_lifecycle(self, mock_config):
        adapter = _MockTestAdapter(config=mock_config)
        assert not adapter.initialized
        assert adapter.initialize() is True
        assert adapter.initialized
        assert adapter.health_check() == HealthStatus.HEALTHY
        adapter.shutdown()
        assert not adapter.initialized

    def test_adapter_get_config(self, mock_config):
        adapter = _MockTestAdapter(config=mock_config)
        assert adapter.get_config("prometheus_port") == 8001
        assert adapter.get_config("nonexistent", default=42) == 42

    def test_adapter_config_priority(self, mock_config):
        """MR-Krabs config > litellm_default > env var > default"""
        adapter = _MockTestAdapter(config={"key": "config_value"})
        result = adapter.get_config(
            "key", 
            default="fallback", 
            litellm_default="litellm_val"
        )
        assert result == "config_value"


class TestHarnessRegistry:
    """Verify adapter registry works in test context."""

    def test_registry_register_and_retrieve(self, mock_config):
        registry = AdapterRegistry()
        adapter = _MockTestAdapter(config=mock_config, name="test1")
        registry.register(adapter)
        assert registry.get("test1") is adapter

    def test_registry_health_check_all(self, mock_config):
        registry = AdapterRegistry()
        registry.register(_MockTestAdapter(config=mock_config, name="a"))
        registry.register(_MockTestAdapter(config=mock_config, name="b"))
        results = registry.health_check_all()
        assert results["a"] == HealthStatus.HEALTHY
        assert results["b"] == HealthStatus.HEALTHY

    def test_registry_initialize_all(self, mock_config):
        registry = AdapterRegistry()
        adapter = _MockTestAdapter(config=mock_config, name="test")
        registry.register(adapter)
        results = registry.initialize_all()
        assert results["test"] is True
        assert adapter.initialized


class TestHarnessFeatureFlags:
    """Verify feature flag toggles work correctly."""

    def test_all_flags_disabled_by_default(self, mock_config):
        """All feature flags should be OFF in the default mock config."""
        assert mock_config["enable_prometheus_metrics"] is False
        assert mock_config["enable_litellm_router"] is False
        assert mock_config["enable_helm_deployment"] is False
        assert mock_config["enable_bearer_auth"] is False
        assert mock_config["enable_tracing"] is False
        assert mock_config["enable_cache"] is False

    def test_config_with_metrics_enabled(self, mock_config_with_metrics):
        assert mock_config_with_metrics["enable_prometheus_metrics"] is True

    def test_config_with_router_enabled(self, mock_config_with_router):
        assert mock_config_with_router["enable_litellm_router"] is True
        assert mock_config_with_router["router_strategy"] == "smart"
