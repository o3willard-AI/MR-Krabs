"""Phase 1: Prometheus metrics adapter tests."""

import pytest
from unittest.mock import patch, MagicMock
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge, generate_latest

from src.adapters import AdapterRegistry, HealthStatus


# Import the adapter (will be created by this task)
# If import fails, tests will show what's missing
try:
    from src.metrics.prometheus_adapter import PrometheusMetricsAdapter, LATENCY_BUCKETS
    PROMETHEUS_AVAILABLE = True
except ImportError as e:
    PROMETHEUS_AVAILABLE = False
    IMPORT_ERROR = str(e)


@pytest.fixture
def adapter(mock_config):
    """Create a PrometheusMetricsAdapter for testing."""
    config = mock_config.copy()
    config["enable_prometheus_metrics"] = True
    config["prometheus_port"] = 18001  # Use high port to avoid conflicts
    # Don't call initialize() — tests use the registry directly
    adapter = PrometheusMetricsAdapter(config=config)
    # Manually set up registry without starting HTTP server
    adapter._registry = CollectorRegistry()
    from prometheus_client import Counter, Histogram, Gauge
    adapter.requests_total = Counter("test_mrkrabs_requests_total", "test", ["provider", "model", "tier", "status"], registry=adapter._registry)
    adapter.request_duration = Histogram("test_mrkrabs_request_duration", "test", ["provider", "model", "tier"], registry=adapter._registry)
    adapter.cost_dollars_total = Counter("test_mrkrabs_cost_total", "test", ["provider", "model"], registry=adapter._registry)
    adapter.errors_total = Counter("test_mrkrabs_errors_total", "test", ["provider", "model", "error_type"], registry=adapter._registry)
    adapter.tier_escalations_total = Counter("test_mrkrabs_escalations", "test", ["from_tier", "to_tier"], registry=adapter._registry)
    adapter.vault_operations_total = Counter("test_mrkrabs_vault_ops", "test", ["operation"], registry=adapter._registry)
    adapter.budget_remaining = Gauge("test_mrkrabs_budget", "test", registry=adapter._registry)
    adapter._initialized = True
    return adapter


class TestPrometheusMetricsAdapter:
    """Core adapter lifecycle tests."""
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason=f"Prometheus adapter not available: {IMPORT_ERROR if not PROMETHEUS_AVAILABLE else ''}")
    def test_adapter_initialization(self, mock_config):
        """Adapter should initialize with proper config."""
        config = mock_config.copy()
        config["enable_prometheus_metrics"] = True
        adapter = PrometheusMetricsAdapter(config=config)
        assert adapter.name == "prometheus_metrics"
        assert adapter.enabled is True
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason=f"Prometheus adapter not available: {IMPORT_ERROR if not PROMETHEUS_AVAILABLE else ''}")
    def test_adapter_disabled_when_flag_off(self, mock_config):
        config = mock_config.copy()
        config["enable_prometheus_metrics"] = False
        adapter = PrometheusMetricsAdapter(config=config)
        assert adapter.enabled is False
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_record_request_increments_counter(self, adapter):
        adapter.record_request("openai", "gpt-4o", "L1", status="success", duration_s=1.5, cost_usd=0.05)
        metrics_text = adapter.get_metrics_text()
        assert "test_mrkrabs_requests_total" in metrics_text
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_record_error_increments_counter(self, adapter):
        adapter.record_error("openai", "gpt-4o", "timeout")
        metrics_text = adapter.get_metrics_text()
        assert "test_mrkrabs_errors_total" in metrics_text
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_record_escalation(self, adapter):
        adapter.record_escalation("L0", "L1")
        metrics_text = adapter.get_metrics_text()
        assert "test_mrkrabs_escalations" in metrics_text
        assert 'from_tier="L0"' in metrics_text
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_record_vault_operation(self, adapter):
        adapter.record_vault_operation("read")
        adapter.record_vault_operation("write")
        metrics_text = adapter.get_metrics_text()
        assert "test_mrkrabs_vault_ops" in metrics_text
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_set_budget_remaining(self, adapter):
        adapter.set_budget_remaining(7.50)
        metrics_text = adapter.get_metrics_text()
        assert "7.5" in metrics_text
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_get_metrics_text_is_valid_prometheus_format(self, adapter):
        adapter.record_request("test", "model", "L0")
        text = adapter.get_metrics_text()
        assert text  # Not empty
        # Prometheus format: lines starting with # HELP, # TYPE, or metric_name{
        for line in text.split("\n"):
            if line and not line.startswith("#"):
                # Named metrics have {labels}, unlabeled metrics (like budget gauge) are just name+value
                assert "{" in line or " " in line
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_health_check_healthy(self, adapter):
        status = adapter.health_check()
        assert status == HealthStatus.HEALTHY
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_health_check_down_when_no_registry(self, mock_config):
        adapter = PrometheusMetricsAdapter(config=mock_config)
        adapter._registry = None
        assert adapter.health_check() == HealthStatus.DOWN
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_safe_labels_hides_provider_by_default(self, adapter):
        labels = adapter._safe_labels({"provider": "openai", "model": "gpt-4o"})
        assert labels["provider"] == "hidden"  # Default: don't expose
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_safe_labels_exposes_provider_when_configured(self, mock_config):
        config = mock_config.copy()
        config["expose_provider_names"] = True
        adapter = PrometheusMetricsAdapter(config=config)
        labels = adapter._safe_labels({"provider": "openai", "model": "gpt-4o"})
        assert labels["provider"] == "openai"
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_safe_labels_truncates_long_values(self, adapter):
        labels = adapter._safe_labels({"model": "a" * 200})
        assert labels["model"] == "truncated"
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_safe_labels_redacts_task_ids(self, adapter):
        labels = adapter._safe_labels({"task_id": "secret-task-123"})
        assert labels["task_id"] == "redacted"


class TestMetricsLatencyBuckets:
    """Verify latency bucket configuration."""
    
    def test_latency_buckets_are_sorted(self):
        assert LATENCY_BUCKETS == tuple(sorted(LATENCY_BUCKETS))
    
    def test_latency_buckets_cover_reasonable_range(self):
        assert LATENCY_BUCKETS[0] == 0.1
        assert LATENCY_BUCKETS[-1] == 60.0


class TestMetricsRegistryIntegration:
    """Verify adapter works with the AdapterRegistry."""
    
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus adapter not available")
    def test_adapter_registers_in_registry(self, mock_config):
        registry = AdapterRegistry()
        adapter = PrometheusMetricsAdapter(config=mock_config)
        registry.register(adapter)
        assert registry.get("prometheus_metrics") is adapter
