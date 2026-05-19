# MR-Krabs Kubernetes Operator — Architecture Blueprint

**Version:** 1.0 (Design Document)
**Status:** Blueprint — Not Implemented
**Target:** Post-Phase-5 production readiness

---

## Overview

The MR-Krabs Operator manages the full lifecycle of MR-Krabs instances on Kubernetes, providing self-healing, auto-scaling, multi-tenancy, and provider rotation at the infrastructure level. It extends the application-level intelligence (SmartRouter, CircuitBreaker, BudgetAlerter) into the orchestration layer.

**Design philosophy:** The operator handles infrastructure concerns (pod lifecycle, scaling, tenant isolation). Application logic (routing, cost calculation, tier escalation) remains inside MR-Krabs. The operator reads application-level signals (Prometheus metrics, health checks) and acts on them at the K8s level.

---

## 1. Custom Resource Definitions (CRDs)

### MrKrabsInstance

The primary CRD representing a deployed MR-Krabs orchestrator.

```yaml
apiVersion: mrkrabs.dev/v1alpha1
kind: MrKrabsInstance
metadata:
  name: production-orchestrator
  namespace: mrkrabs-prod
spec:
  replicas: 3
  image: mrkrabs:0.2.0
  budget:
    daily: 50.00
    hardLimit: true
    resetHour: 0  # UTC hour for daily reset
  providers:
    - name: openai
      apiKeySecretRef: openai-api-key
      priority: 1
      circuitBreaker:
        failureThreshold: 5
        resetTimeoutSeconds: 30
    - name: anthropic
      apiKeySecretRef: anthropic-api-key
      priority: 2
      circuitBreaker:
        failureThreshold: 3
        resetTimeoutSeconds: 60
    - name: deepseek
      apiKeySecretRef: deepseek-api-key
      priority: 3
  routing:
    strategy: smart
    smartWeights:
      cost: 0.5
      latency: 0.3
      capability: 0.2
  metrics:
    prometheusEnabled: true
    serviceMonitorEnabled: true
    scrapeInterval: 30s
  auth:
    bearerTokenEnabled: true
    tokenSecretRef: mrkrabs-bearer-token
  scaling:
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilization: 80
    queueDepthThreshold: 10
    cooldownSeconds: 180
  tenants:
    - name: team-a
      budgetShare: 0.6
      namespace: mrkrabs-team-a
    - name: team-b
      budgetShare: 0.4
      namespace: mrkrabs-team-b
status:
  phase: Healthy
  replicas: 3
  readyReplicas: 3
  budgetRemaining: 42.30
  activeProviders:
    - name: openai
      healthy: true
      circuitState: closed
    - name: anthropic
      healthy: true
      circuitState: closed
```

### MrKrabsBudget

Manages budget lifecycle independently of instances.

```yaml
apiVersion: mrkrabs.dev/v1alpha1
kind: MrKrabsBudget
metadata:
  name: production-budget
spec:
  dailyLimit: 50.00
  hardLimit: true
  resetHour: 0
  alertThresholds:
    warning: 20  # percent
    critical: 10
  rollover: false
status:
  remaining: 42.30
  spent: 7.70
  percentRemaining: 84.6
  level: normal
  lastReset: "2026-05-19T00:00:00Z"
```

### MrKrabsProvider

Tracks provider health and circuit breaker state at the operator level.

```yaml
apiVersion: mrkrabs.dev/v1alpha1
kind: MrKrabsProvider
metadata:
  name: openai
spec:
  name: openai
  baseURL: https://api.openai.com/v1
  healthCheck:
    enabled: true
    interval: 30s
    timeout: 5s
  circuitBreaker:
    failureThreshold: 5
    failureWindowSeconds: 60
    resetTimeoutSeconds: 30
status:
  healthy: true
  circuitState: closed
  consecutiveFailures: 0
  lastHealthCheck: "2026-05-19T22:00:00Z"
```

---

## 2. Controller Reconciliation Loops

### State Machine

```
                  ┌─────────────┐
                  │ Provisioning│ ← Initial creation
                  └──────┬──────┘
                         │ Pods running, health checks pass
                         ▼
                  ┌─────────────┐
          ┌───────│   Healthy   │───────┐
          │       └──────┬──────┘       │
          │              │              │
     Provider        Budget          Pod failure
     unhealthy       < 20%           or eviction
          │              │              │
          ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Degraded │   │ Degraded │   │ Degraded │
   └────┬─────┘   └────┬─────┘   └────┬─────┘
        │              │              │
    All providers  Budget = 0    CrashLoopBackOff
    unhealthy                        > 5 min
        │              │              │
        ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Critical │   │ Critical │   │ Critical │
   └──────────┘   └──────────┘   └──────────┘
        │              │              │
        └──────────────┼──────────────┘
                       │ Manual deletion
                       ▼
                ┌─────────────┐
                │ Terminating │
                └─────────────┘
```

### Reconciliation Triggers

| Trigger | Detection | Action |
|---------|-----------|--------|
| CRD spec change | Kubernetes watch | Reconcile deployment, config, secrets |
| Pod failure | Pod status != Running | Restart pod, scale up if needed |
| Provider unhealthy | Health check probe fails | Rotate to next provider, update status |
| Budget exhausted | Prometheus gauge = 0 | Block new requests, notify |
| Budget reset | Schedule (midnight UTC) | Reset budget counter, unblock |
| Manual scale | `kubectl scale` or CRD update | Adjust replicas |

### Idempotency Guarantees

- Reconciliation is idempotent: running twice produces identical state
- Compare desired (CRD spec) vs actual (cluster state) — only apply deltas
- No partial updates: all changes within a reconciliation cycle are atomic
- If reconciliation fails, retry with exponential backoff (1s → 2s → 4s → ... → 60s max)

---

## 3. Auto-Scaling Strategy

### Scale-Up Triggers (OR logic)

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Request queue depth | > 10 for 60s | Backpressure building |
| Token throughput | > 80% of current capacity | Nearing compute limits |
| P95 latency | > 3× baseline | Performance degradation |

### Scale-Down Triggers (AND logic)

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Request queue | Empty for 5 min | No demand |
| Token throughput | < 20% of capacity | Over-provisioned |
| Active long-running tasks | Zero | No work in flight |

### Constraints

```
maxReplicas = min(
    spec.scaling.maxReplicas,        # Configurable cap
    floor(spec.budget.daily / 0.50)  # Budget constraint (~$0.50/pod/hr)
)

minReplicas = spec.scaling.minReplicas  # Default: 2 for HA
```

### Cooldown

- 180 seconds between any scale event (prevents flapping)
- Scale-up cooldown independent of scale-down cooldown
- Override via annotation: `mrkrabs.dev/bypass-cooldown: "true"`

---

## 4. Self-Healing

### Provider Rotation

When a provider's health check fails:
1. Operator reads `MrKrabsInstance.status.activeProviders`
2. Identifies unhealthy provider
3. Updates MR-Krabs ConfigMap to deprioritize unhealthy provider
4. Triggers rolling restart (respects PDB)
5. Circuit breaker integrates at K8s level: if provider stays unhealthy, don't try again for `resetTimeoutSeconds`

### Pod Recovery

- CrashLoopBackOff detected → restart pod, increment counter
- After 5 restarts in 10 min → scale up to maintain capacity, mark pod for investigation
- Node failure → Kubernetes scheduler handles rescheduling
- PDB ensures `minAvailable` pods always running

### Budget Protection

- Budget < critical threshold (10%): operator scales down to `minReplicas`
- Budget exhausted: operator scales to 0 (preserves config/secrets, resumes on budget reset)

---

## 5. Multi-Tenancy Design

### Namespace-per-Tenant

```
mrkrabs-team-a/
├── MrKrabsInstance (team-a-orchestrator)
├── Secret (team-a-api-keys)
└── Service (team-a-mrkrabs)

mrkrabs-team-b/
├── MrKrabsInstance (team-b-orchestrator)
├── Secret (team-b-api-keys)
└── Service (team-b-mrkrabs)
```

### Per-Tenant Budget Enforcement

- Each tenant has a `budgetShare` of the total budget
- Budget enforced at operator level: tenant can't exceed their share
- Tenant budget exhaustion does NOT affect other tenants

### Cross-Tenant Fair Scheduling

Under contention (total demand > capacity):

```
tenant_throughput = total_capacity × (tenant.budgetShare / sum(all budgetShares))
```

Example: Team A (60%) gets 60% of throughput, Team B (40%) gets 40%.

### Tenant Isolation Guarantees

- Separate namespaces → no cross-tenant pod communication
- Separate secrets → no API key leakage
- Separate metrics → no cost data mixing
- NetworkPolicy: deny all cross-namespace traffic by default

---

## 6. Implementation Staging Plan

### Phase 1: Basic CRD + Reconciliation (Week 1-2)

- `MrKrabsInstance` CRD
- Controller: reconcile deployment, service, configmap
- Health check → restart unhealthy pods
- Estimated: 8 days

### Phase 2: Budget-Aware Auto-Scaling (Week 3-4)

- `MrKrabsBudget` CRD
- Prometheus metrics scraping for scale triggers
- HPA integration with custom metrics
- Budget-constrained max replicas
- Estimated: 7 days

### Phase 3: Multi-Tenancy (Week 5-6)

- Namespace-per-tenant provisioning
- Per-tenant budget enforcement
- Cross-tenant fair scheduling
- Tenant CRD for self-service
- Estimated: 8 days

### Phase 4: Provider Rotation + Circuit Breaker (Week 7-8)

- `MrKrabsProvider` CRD
- Provider health checks
- Automatic ConfigMap rotation
- Operator-level circuit breaker
- Estimated: 7 days

**Total estimated build:** 30 days across 4 two-week sprints.

---

## 7. Framework Recommendation

### Recommendation: Kopf (Python)

| Factor | Kopf | Kubebuilder (Go) | Winner |
|--------|------|-------------------|--------|
| Language match | Python (same as MR-Krabs) | Go | Kopf |
| Team familiarity | Python devs | Requires Go expertise | Kopf |
| Development speed | Fast (declarative, no codegen) | Slower (codegen, boilerplate) | Kopf |
| Performance | Adequate for control plane | Higher throughput | Tie |
| Ecosystem | Growing, kopf-extra plugins | Mature, extensive | Kubebuilder |
| MR-Krabs integration | Direct import of MR-Krabs libs | Requires API translation | Kopf |

**Rationale:** MR-Krabs is a Python project. Using Kopf allows the operator to directly import `src/adapters/`, `src/metrics/`, and `src/core/` for health checking, cost calculation, and circuit breaker logic — no translation layer needed. Kopf's declarative handler pattern (`@kopf.on.create`, `@kopf.on.update`, `@kopf.on.field`) maps cleanly to reconciliation triggers.

**Trade-off:** Kopf operators have higher baseline resource usage than Go operators (~50MB vs ~10MB). For a control plane managing 10-50 MR-Krabs instances, this is acceptable.

**Fallback:** If operator performance becomes a bottleneck at scale (>500 instances), migrate hot-path reconciliation to Kubebuilder while keeping CRD definitions and business logic in Python.

---

## 8. Open Questions / TBD

1. **State persistence**: Where does operator state live? CRD status subresources? Separate ConfigMap? etcd directly?
2. **Backup/restore**: How to backup budget state, provider health history, tenant configs?
3. **OIDC integration**: Should tenant authentication use OIDC or MR-Krabs' own Bearer tokens?
4. **Metrics aggregation**: Single Prometheus per cluster, or per-tenant Prometheus instances?
5. **Operator upgrade strategy**: Rolling update of operator itself — how to handle in-flight reconciliations?
