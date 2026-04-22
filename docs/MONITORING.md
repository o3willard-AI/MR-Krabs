# Production Monitoring Strategy

**Status**: Future / Production-Ready
**Created**: 2026-04-03
**Applies to**: Server-mode deployment (see FUTURE_SERVER_MODE.md)

---

## Key Performance Indicators (KPIs)

| KPI | Metric Name | Alert Threshold | Critical Threshold |
|-----|-------------|-----------------|-------------------|
| Overhead p99 | `orchestrator.overhead.p99_ms` | >100ms | >200ms |
| DB write latency | `orchestrator.db.write_latency_ms` | >50ms | >200ms |
| Budget check latency | `orchestrator.budget.check_latency_ms` | >10ms | >50ms |
| Circuit breaker lock wait | `orchestrator.circuit_breaker.lock_wait_ms` | >5ms | >20ms |
| Memory RSS | `orchestrator.memory.rss_mb` | >500MB | >1000MB |
| Pending spend count | `orchestrator.budget.pending_spend_count` | >100 | >500 |
| Escalation duration | `orchestrator.escalation.duration_seconds` | >30s | >120s |
| OTel export queue size | `orchestrator.otel.export_queue_size` | >1000 | >5000 |

## Instrumentation Points

### Overhead p99
```python
import time
from src.core.metrics import MetricsCollector

start = time.perf_counter()
result = orchestrator.execute_task(task_id, tier, context)
duration_ms = (time.perf_counter() - start) * 1000
metrics.record_histogram("orchestrator.overhead", duration_ms)
```

### Budget Check Latency
```python
start = time.perf_counter()
tracker.reserve_budget(scope, estimated_cost)
latency_ms = (time.perf_counter() - start) * 1000
metrics.record_histogram("orchestrator.budget.check_latency", latency_ms)
```

### Memory RSS
```python
import resource
rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
metrics.record_gauge("orchestrator.memory.rss", rss_mb)
```

### Pending Spend Count
```python
metrics.record_gauge("orchestrator.budget.pending_spend_count", len(tracker._reservations))
```

## Grafana Dashboard Panels

### 1. Overhead p99 (Time Series)
```json
{
  "title": "Orchestrator Overhead p99",
  "type": "timeseries",
  "targets": [
    {
      "expr": "histogram_quantile(0.99, rate(orchestrator_overhead_bucket[5m]))",
      "legendFormat": "p99"
    }
  ],
  "thresholds": [
    {"value": 100, "color": "yellow"},
    {"value": 200, "color": "red"}
  ]
}
```

### 2. Budget Health (Gauge)
```json
{
  "title": "Budget Remaining %",
  "type": "gauge",
  "targets": [
    {
      "expr": "orchestrator_budget_remaining / orchestrator_budget_limit * 100"
    }
  ]
}
```

### 3. Escalation Rate (Time Series)
```json
{
  "title": "Escalations per Minute",
  "type": "timeseries",
  "targets": [
    {
      "expr": "rate(orchestrator_escalations_total[5m]) * 60"
    }
  ]
}
```

### 4. Circuit Breaker State (Stat)
```json
{
  "title": "Open Circuit Breakers",
  "type": "stat",
  "targets": [
    {
      "expr": "sum(orchestrator_circuit_breaker_state == 1)"
    }
  ]
}
```

### 5. Memory Usage (Time Series)
```json
{
  "title": "Memory RSS (MB)",
  "type": "timeseries",
  "targets": [
    {
      "expr": "orchestrator_memory_rss"
    }
  ]
}
```

### 6. Pending Spends (Time Series)
```json
{
  "title": "Pending Budget Reservations",
  "type": "timeseries",
  "targets": [
    {
      "expr": "orchestrator_budget_pending_spend_count"
    }
  ]
}
```

### 7. Task Success Rate (Time Series)
```json
{
  "title": "Task Success Rate",
  "type": "timeseries",
  "targets": [
    {
      "expr": "rate(orchestrator_tasks_success_total[5m]) / rate(orchestrator_tasks_total[5m]) * 100"
    }
  ]
}
```

### 8. Cost per Hour (Time Series)
```json
{
  "title": "Cost per Hour (USD)",
  "type": "timeseries",
  "targets": [
    {
      "expr": "rate(orchestrator_cost_total[1h]) * 3600"
    }
  ]
}
```

## Profiling Strategy

### Development
- Use `pyinstrument` for call-tree profiling: `pyinstrument -m src.cli.main run "test"`
- Use `memory_profiler` for memory profiling: `mprof run -M python -m src.cli.main run "test"`

### CI
- Run benchmark suite on every PR (`tests/benchmarks/test_benchmarks.py`)
- Fail if any benchmark regresses by >10%
- Track benchmark history over time

### Production
- Use `py-spy` for sampling profiler in production: `py-spy record --pid <pid> --output profile.svg`
- Enable OTel tracing with 10% sampling rate
- Set up alerting on all KPI thresholds

### Load Testing
- Run before each release with `locust` or `k6`
- Target: 1000 concurrent tasks, <100ms overhead p99, no budget overruns
- Record results in `docs/benchmarks/`
