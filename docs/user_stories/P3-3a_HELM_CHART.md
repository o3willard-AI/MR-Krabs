# Story P3-3a: Helm Chart for Kubernetes Deployment

**Priority:** P1 (High — enterprise adoption enabler)
**Estimate:** 5 days
**Phase:** Phase 3 — Weeks 6–7

---

## User Story

As a **platform engineer** deploying MR-Krabs to production,
I want a Helm chart that installs MR-Krabs on any Kubernetes cluster with a single command
So that I can deploy, upgrade, and rollback predictably without custom infrastructure scripts.

---

## Acceptance Criteria

### AC1: Helm Chart Structure
- [ ] Fork and adapt LiteLLM Helm chart into `charts/mrkrabs/`:
  ```
  charts/mrkrabs/
  ├── Chart.yaml              # name: mrkrabs, apiVersion: v2, type: application
  ├── values.yaml             # all configurable parameters with defaults + comments
  ├── values.schema.json      # JSON schema validation for values
  ├── templates/
  │   ├── _helpers.tpl        # template helper functions
  │   ├── deployment.yaml     # MCP server deployment
  │   ├── service.yaml        # MCP server service (ClusterIP default)
  │   ├── serviceaccount.yaml # RBAC service account
  │   ├── configmap.yaml      # MR-Krabs TOML config injected via ConfigMap
  │   ├── secret.yaml         # vault master key + provider API keys
  │   ├── hpa.yaml            # HorizontalPodAutoscaler (optional)
  │   ├── pdb.yaml            # PodDisruptionBudget (optional)
  │   ├── ingress.yaml        # Ingress for external /metrics access (optional)
  │   ├── servicemonitor.yaml # Prometheus ServiceMonitor (optional)
  │   └── NOTES.txt           # Post-install instructions
  └── README.md               # Chart documentation
  ```

### AC2: Production-Grade Defaults
- [ ] `values.yaml` sensible defaults:
  - `replicas: 2` — high availability by default
  - `image.repository: mrkrabs`, `image.tag: latest` (configurable)
  - `resources.requests: {cpu: 250m, memory: 512Mi}`, `limits: {cpu: 1000m, memory: 2Gi}`
  - `service.type: ClusterIP`, `service.port: 8000`
  - `metrics.service.port: 8001` — separate metrics port
  - `config.budget.daily_limit: 10.00` — default $10/day
  - `securityContext.runAsNonRoot: true`, `readOnlyRootFilesystem: true`
- [ ] All values documented with inline comments
- [ ] `values.schema.json` validates required fields and types

### AC3: Configuration Injection
- [ ] MR-Krabs TOML config generated from `values.yaml` via ConfigMap template
- [ ] Sensitive values (API keys, vault key) injected via Kubernetes Secret, mounted as env vars
- [ ] Config hot-reload: ConfigMap change triggers rolling restart via `checksum/config` annotation
- [ ] Support external secret providers: `externalSecrets.enabled: true` → references ExternalSecret CRD

### AC4: Installation & Upgrade Experience
- [ ] Single-command install:
  ```bash
  helm repo add mrkrabs https://charts.mrkrabs.dev
  helm install mrkrabs mrkrabs/mrkrabs \
    --set config.providers.openai.apiKey=$OPENAI_KEY \
    --set config.vault.masterKey=$VAULT_KEY
  ```
- [ ] `helm upgrade` preserves existing secrets, only updates ConfigMap
- [ ] `helm rollback` restores previous ConfigMap + deployment revision
- [ ] `helm test` runs integration smoke tests in-cluster
- [ ] Post-install NOTES.txt shows: health check URL, metrics URL, how to get logs

### AC5: Health & Readiness
- [ ] Deployment includes liveness probe: `GET /health` every 30s, timeout 5s
- [ ] Readiness probe: `GET /ready` — returns 200 only when vault initialized + adapters healthy
- [ ] Startup probe: `GET /health` — 60s initial delay, failure threshold 30 (generous cold start)
- [ ] PodDisruptionBudget: `minAvailable: 1` when replicas ≥ 2

### AC6: Documentation
- [ ] `charts/mrkrabs/README.md` auto-generated from `values.yaml` comments (helm-docs)
- [ ] `docs/deploy/k8s/INSTALL.md`: step-by-step install guide
  - Prerequisites (kubectl, helm 3.x, cluster ≥1.27)
  - Minimal config example
  - Production config example with all adapters enabled
  - Troubleshooting section (common issues + solutions)
- [ ] `docs/deploy/k8s/UPGRADE.md`: upgrade guide per version

---

## Technical Notes

- Helm `apiVersion: v2` (Helm 3 only — Helm 2 is EOL)
- Use named templates in `_helpers.tpl` for labels, selectors, image pull policy
- K8s minimum version: 1.27+ (matches LiteLLM's target)
- Image pull policy: `IfNotPresent` for tagged versions, `Always` for `latest`
- Namespace: create if not exists via `helm install --create-namespace -n mrkrabs`
- Test with `helm lint`, `helm template`, and `kubeconform` in CI

---

## Definition of Done

- [ ] `charts/mrkrabs/` committed with all templates
- [ ] `helm lint charts/mrkrabs` passes
- [ ] `helm template` generates valid K8s manifests
- [ ] `helm install` succeeds on test cluster, all pods healthy within 2 min
- [ ] `/health` and `/ready` endpoints respond correctly
- [ ] Prometheus ServiceMonitor discovers `/metrics` automatically
- [ ] `helm test` passes smoke tests
- [ ] `docs/deploy/k8s/INSTALL.md` and `UPGRADE.md` complete
