# Story P3-3c: Kubernetes Operator Architecture Blueprint

**Priority:** P2 (Medium — future self-healing infrastructure, not a blocker)
**Estimate:** 4 days
**Phase:** Phase 3 — Week 7

---

## User Story

As a **platform architect** planning long-term MR-Krabs infrastructure,
I want a detailed operator architecture blueprint documenting self-healing, auto-scaling, and multi-tenancy patterns
So that when we're ready to build the operator, we have a clear, reviewed design — not a greenfield scramble.

---

## Acceptance Criteria

### AC1: Operator Architecture Document
- [ ] Produce `docs/operator/ARCHITECTURE.md` covering:
  - **Custom Resource Definitions (CRDs)**: proposed schema for `MrKrabsInstance`, `MrKrabsBudget`, `MrKrabsProvider`
  - **Controller reconciliation loops**: what triggers reconciliation, idempotency guarantees
  - **Auto-scaling strategy**: scale based on request queue depth + token throughput + budget headroom
  - **Self-healing**: circuit breaker integration → automatic provider rotation at K8s level
  - **Multi-tenancy**: namespace isolation, per-tenant budgets, cross-tenant fair scheduling
  - **State management**: vault master key lifecycle in K8s, backup/restore procedures
- [ ] Architecture decision records (ADRs) for 5+ key trade-offs

### AC2: CRD Schema Designs
- [ ] `MrKrabsInstance` CRD:
  ```yaml
  apiVersion: mrkrabs.dev/v1alpha1
  kind: MrKrabsInstance
  metadata:
    name: production-orchestrator
  spec:
    replicas: 3
    budget:
      daily: 50.00
      hardLimit: true
    providers:
      - name: openai
        apiKeySecretRef: openai-api-key
        priority: 1
      - name: anthropic
        apiKeySecretRef: anthropic-api-key
        priority: 2
    routing:
      strategy: smart
      circuitBreaker:
        failureThreshold: 5
    metrics:
      prometheusEnabled: true
  ```
- [ ] `MrKrabsBudget` CRD for budget lifecycle management
- [ ] Full OpenAPI v3 schema for each CRD (for `kubectl explain` support)

### AC3: Controller Reconciliation Design
- [ ] Reconciliation triggers:
  - CRD spec change (user update)
  - Pod failure / eviction
  - Provider health status change (from circuit breaker metrics)
  - Budget exhaustion event
  - Scheduled time (daily budget reset)
- [ ] Reconciliation guarantees:
  - Idempotent: running reconciliation twice produces same state
  - Eventual consistency: target state reached within 30s of trigger
  - Graceful degradation: if one provider unhealthy, operator routes around it automatically
- [ ] State machine diagram for `MrKrabsInstance` lifecycle: `Provisioning → Healthy → Degraded → Critical → Terminating`

### AC4: Auto-Scaling Algorithm Design
- [ ] Scale-up triggers (OR logic):
  - Request queue depth > 10 for 60s
  - Average token throughput > 80% of current capacity
  - P95 latency > 3× baseline
- [ ] Scale-down triggers (AND logic):
  - Request queue empty for 5 min
  - Token throughput < 20% of capacity
  - No active long-running tasks
- [ ] Cooldown: 3 min between scale events (prevents flapping)
- [ ] Max replicas bounded by `spec.budget.daily / estimated_cost_per_replica`
- [ ] Algorithm documented with pseudocode, not just prose

### AC5: Multi-Tenancy Design
- [ ] Namespace-per-tenant: `mrkrabs-team-a`, `mrkrabs-team-b`
- [ ] Per-tenant budgets enforced at operator level (not just application level)
- [ ] Cross-tenant fair scheduling:
  - If total demand exceeds capacity: weighted fair queuing by budget proportion
  - Tenant with 50% of budget gets 50% of throughput under contention
- [ ] Tenant isolation: one tenant's budget exhaustion doesn't affect others

### AC6: Implementation Staging Plan
- [ ] Phase 1 (post-blueprint): `MrKrabsInstance` CRD + basic reconciliation (deploy, health check, restart)
- [ ] Phase 2: Budget-aware auto-scaling
- [ ] Phase 3: Multi-tenancy + fair scheduling
- [ ] Phase 4: Provider rotation + circuit breaker integration
- [ ] Estimated total build: 20 days across 4 sprints
- [ ] Decision on framework: Kubebuilder vs. Operator SDK vs. Kopf (with rationale)

---

## Technical Notes

- Not implementing the operator yet — just the blueprint. Full implementation is a Phase 5+ item.
- Reference LiteLLM's proposed operator patterns, not their actual implementation (which may be incomplete)
- CRD versioning: `v1alpha1` for initial design, `v1beta1` after stabilization
- Consider `metacontroller` or `kopf` (Python) for faster iteration vs. Golang operators
- Budget lifecycle: daily reset at midnight UTC, configurable per CRD instance

---

## Definition of Done

- [ ] `docs/operator/ARCHITECTURE.md` committed with all 5 design sections
- [ ] CRD schemas documented with YAML examples
- [ ] State machine diagram (ASCII or Mermaid) for instance lifecycle
- [ ] Auto-scaling pseudocode documented
- [ ] Multi-tenancy design reviewed by at least one K8s-experienced engineer
- [ ] Framework recommendation with rationale (Kubebuilder vs. Kopf vs. Operator SDK)
- [ ] Implementation staging plan with estimated effort per phase
