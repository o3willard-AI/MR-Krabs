"""
Metrics collection for MR-Krabs.
"""

from .error_metrics import ErrorMetrics, ErrorMetricsCollector

# Only import PrometheusMetricsAdapter when needed to avoid dependency issues
def get_prometheus_adapter():
    try:
        from .prometheus_adapter import PrometheusMetricsAdapter, LATENCY_BUCKETS
        return PrometheusMetricsAdapter, LATENCY_BUCKETS
    except ImportError:
        # Return None if prometheus_client is not available
        return None, None

__all__ = [
    "ErrorMetrics",
    "ErrorMetricsCollector",
]
