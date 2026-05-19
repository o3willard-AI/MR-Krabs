"""Prometheus metrics adapter for MR-Krabs.

Forked and adapted from LiteLLM's prometheus integration patterns.
Provides mrkrabs_* metrics exposed via FastAPI /metrics endpoint.
"""

import time
from typing import Dict, Optional
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

from ..adapters.base_adapter import LiteLLMAdapter, HealthStatus, AdapterInitError


# Standard latency buckets (seconds)
LATENCY_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)


class PrometheusMetricsAdapter(LiteLLMAdapter):
    """Prometheus metrics collection adapter for MR-Krabs.
    
    Exposes 7 core metrics via a dedicated /metrics HTTP endpoint.
    Integrates with the FastAPI MCP server for metric scraping.
    Implements cardinality guards and sensitive data filtering.
    """
    
    def __init__(self, config=None, name: str = "prometheus_metrics"):
        super().__init__(config or {}, name)
        self._registry: Optional[CollectorRegistry] = None
        self._http_server = None
        self._scrape_timestamps: Dict[str, float] = {}
        
        # Metric objects (initialized in initialize())
        self.requests_total = None
        self.request_duration = None
        self.cost_dollars_total = None
        self.errors_total = None
        self.tier_escalations_total = None
        self.vault_operations_total = None
        self.budget_remaining = None
    
    @property
    def enabled(self) -> bool:
        return self.get_config("enable_prometheus_metrics", default=True)
    
    def initialize(self) -> bool:
        """Set up Prometheus metrics registry and HTTP server."""
        from prometheus_client import start_http_server
        
        self._registry = CollectorRegistry()
        
        # Metric 1: Request counter
        self.requests_total = Counter(
            "mrkrabs_requests_total",
            "Total number of ask() requests processed",
            labelnames=["provider", "model", "tier", "status"],
            registry=self._registry,
        )
        
        # Metric 2: Request duration histogram
        self.request_duration = Histogram(
            "mrkrabs_request_duration_seconds",
            "Duration of ask() requests in seconds",
            labelnames=["provider", "model", "tier"],
            buckets=LATENCY_BUCKETS,
            registry=self._registry,
        )
        
        # Metric 3: Cost counter
        self.cost_dollars_total = Counter(
            "mrkrabs_cost_dollars_total",
            "Total cost in USD spent on LLM requests",
            labelnames=["provider", "model"],
            registry=self._registry,
        )
        
        # Metric 4: Error counter
        self.errors_total = Counter(
            "mrkrabs_errors_total",
            "Total number of errors from LLM requests",
            labelnames=["provider", "model", "error_type"],
            registry=self._registry,
        )
        
        # Metric 5: Tier escalation counter
        self.tier_escalations_total = Counter(
            "mrkrabs_tier_escalations_total",
            "Total number of tier escalations",
            labelnames=["from_tier", "to_tier"],
            registry=self._registry,
        )
        
        # Metric 6: Vault operations counter
        self.vault_operations_total = Counter(
            "mrkrabs_vault_operations_total",
            "Total number of vault read/write operations",
            labelnames=["operation"],
            registry=self._registry,
        )
        
        # Metric 7: Budget remaining gauge
        self.budget_remaining = Gauge(
            "mrkrabs_budget_remaining_dollars",
            "Current remaining budget in USD",
            registry=self._registry,
        )
        
        # Start Prometheus HTTP server on configured port
        port = self.get_config("prometheus_port", default=8001, litellm_default=8001)
        try:
            # Use prometheus_client's built-in HTTP server
            from prometheus_client import start_http_server
            start_http_server(port, registry=self._registry)
            self._initialized = True
            return True
        except Exception as e:
            raise AdapterInitError(f"Failed to start Prometheus HTTP server on port {port}: {e}")
    
    def health_check(self) -> HealthStatus:
        """Check if metrics collection is healthy."""
        if not self._registry:
            return HealthStatus.DOWN
        # Verify registry is functional by checking metrics exist
        try:
            metrics_text = generate_latest(self._registry)
            if not metrics_text:
                return HealthStatus.DEGRADED
            return HealthStatus.HEALTHY
        except Exception:
            return HealthStatus.DOWN
    
    def shutdown(self) -> None:
        """Cleanup. Prometheus HTTP server stops with process."""
        self._initialized = False
        self._registry = None
    
    # ---- Metric Recording Methods ----
    
    def _safe_labels(self, labels: Dict[str, str]) -> Dict[str, str]:
        """Filter labels: never include unbounded values (task IDs, prompt text).
        Also respect expose_provider_names config."""
        safe = {}
        for key, value in labels.items():
            # Cardinality guard: reject unbounded values
            if len(value) > 100:
                safe[key] = "truncated"
            elif key in ("task_id", "prompt", "input_text", "output_text"):
                safe[key] = "redacted"
            elif key == "provider" and not self.get_config("expose_provider_names", default=False):
                safe[key] = "hidden"
            else:
                safe[key] = value
        return safe
    
    def record_request(self, provider: str, model: str, tier: str, 
                       status: str = "success", duration_s: float = 0.0,
                       cost_usd: float = 0.0):
        """Record a completed ask() request."""
        labels = self._safe_labels({"provider": provider, "model": model, "tier": tier})
        self.requests_total.labels(**labels, status=status).inc()
        if duration_s > 0:
            self.request_duration.labels(**labels).observe(duration_s)
        if cost_usd > 0:
            cost_labels = self._safe_labels({"provider": provider, "model": model})
            self.cost_dollars_total.labels(**cost_labels).inc(cost_usd)
    
    def record_error(self, provider: str, model: str, error_type: str):
        """Record an error from an LLM request."""
        labels = self._safe_labels({"provider": provider, "model": model, "error_type": error_type})
        self.errors_total.labels(**labels).inc()
    
    def record_escalation(self, from_tier: str, to_tier: str):
        """Record a tier escalation."""
        self.tier_escalations_total.labels(from_tier=from_tier, to_tier=to_tier).inc()
    
    def record_vault_operation(self, operation: str):
        """Record a vault read or write."""
        self.vault_operations_total.labels(operation=operation).inc()
    
    def set_budget_remaining(self, amount_usd: float):
        """Set the current budget remaining gauge."""
        self.budget_remaining.set(amount_usd)
    
    def get_metrics_text(self) -> str:
        """Generate Prometheus text format metrics."""
        if not self._registry:
            return ""
        return generate_latest(self._registry).decode("utf-8")
