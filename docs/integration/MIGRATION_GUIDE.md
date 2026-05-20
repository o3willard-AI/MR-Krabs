# MR-Krabs LiteLLM Integration — Migration Guide

## For Existing MR-Krabs Users

The LiteLLM integration is fully backward compatible. All new features are opt-in via feature flags.

### Upgrading

```bash
pip install --upgrade mrkrabs
```

Your existing config and code continue working unchanged — all feature flags default to OFF.

### Enabling Features

Add to your `mrkrabs.toml` or environment:

```toml
[features]
enable_prometheus_metrics = true    # Phase 1: /metrics endpoint
enable_litellm_router = true        # Phase 2: smart multi-provider routing
enable_bearer_auth = true           # Phase 3: Bearer token auth
enable_tracing = true               # Phase 5: distributed tracing
enable_cache = true                 # Phase 5: LLM response caching
```

Or via environment:
```bash
export MRKRABS_ENABLE_PROMETHEUS_METRICS=true
export MRKRABS_ENABLE_LITELLM_ROUTER=true
```

### New Providers

Five new providers available without code changes:

```python
# Use via ask()
from cost_orchestrator import ask

result = ask("Write a function", provider="anthropic")
result = ask("Write a function", provider="deepseek")
result = ask("Write a function", provider="mistral")
```

### Kubernetes Deployment

```bash
helm repo add mrkrabs https://charts.mrkrabs.dev
helm install mrkrabs mrkrabs/mrkrabs \
  --set config.features.enablePrometheusMetrics=true \
  --set config.features.enableLitellmRouter=true
```

### Rollback

To return to pre-integration behavior, set all feature flags to false:

```toml
[features]
enable_prometheus_metrics = false
enable_litellm_router = false
enable_bearer_auth = false
enable_tracing = false
enable_cache = false
```

Or uninstall and reinstall the version without LiteLLM integration.