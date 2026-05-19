# MR-Krabs Helm Chart

Cost-optimized AI orchestrator with multi-tier LLM routing.

## Quick Install

```bash
helm install mrkrabs ./charts/mrkrabs \
  --set config.budget.dailyLimit=20.00 \
  --set config.routing.strategy=smart
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `replicaCount` | `2` | Number of pods |
| `image.repository` | `mrkrabs` | Container image |
| `image.tag` | `latest` | Image tag |
| `service.port` | `8000` | MCP server port |
| `service.metricsPort` | `8001` | Prometheus metrics port |
| `config.budget.dailyLimit` | `10.00` | Daily budget in USD |
| `config.routing.strategy` | `smart` | smart / cost_aware / latency_aware / round_robin |
| `config.features.enablePrometheusMetrics` | `true` | Expose /metrics |
| `config.features.enableLitellmRouter` | `false` | SmartRouter (Phase 2) |
| `config.features.enableBearerAuth` | `false` | Bearer token auth (Phase 3) |
| `resources.requests.cpu` | `250m` | CPU request |
| `resources.requests.memory` | `512Mi` | Memory request |

## Prerequisites

- Kubernetes 1.27+
- Helm 3.x
- Prometheus (optional, for metrics scraping)

## Exposing Metrics

```bash
# Port-forward the metrics endpoint
kubectl port-forward svc/mrkrabs 8001:8001

# Verify
curl http://localhost:8001/metrics
```

## Upgrade

```bash
helm upgrade mrkrabs ./charts/mrkrabs --set config.budget.dailyLimit=50.00
```

## Rollback

```bash
helm rollback mrkrabs
```
