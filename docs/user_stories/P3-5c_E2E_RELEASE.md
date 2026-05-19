# Story P3-5c: End-to-End Integration & Release Preparation

**Priority:** P0 (Critical — final integration gate before release)
**Estimate:** 4 days
**Phase:** Phase 5 — Week 12

---

## User Story

As the **release manager** for MR-Krabs,
I want all LiteLLM integration components tested end-to-end with a comprehensive release checklist
So that I can confidently ship a production-ready release with all adapters working together.

---

## Acceptance Criteria

### AC1: End-to-End Integration Tests
- [ ] Create `tests/integration_litellm/e2e/` with full-stack tests:
  - `test_full_ask_flow.py`: `ask()` → SmartRouter → provider → response with cost + metrics
  - `test_multi_provider_failover.py`: simulate provider failure → circuit breaker → rotation
  - `test_budget_enforcement_e2e.py`: set $0.01 budget → verify blocked at limit
  - `test_metrics_e2e.py`: run 100 `ask()` calls → verify all Prometheus metrics populated
  - `test_helm_deployment.py`: `helm install` → health check → `helm test` → `helm uninstall`
  - `test_auth_flow.py`: authenticate → call `/ask` → verify 401 without token
  - `test_tracing_e2e.py`: run `ask()` with tracing → verify spans in Jaeger
  - `test_cache_e2e.py`: same prompt twice → second call hits cache
- [ ] All e2e tests pass with all feature flags enabled simultaneously
- [ ] Test matrix: run against at least 2 providers in CI (OpenAI + Anthropic, using GitHub Environments secrets)

### AC2: Performance Baseline & Regression Check
- [ ] Run performance benchmark script across all phases:
  ```bash
  mrkrabs benchmark --iterations 1000 --profile full_stack
  ```
- [ ] Measure and document:
  - `ask()` latency: P50, P95, P99 (ms)
  - Throughput: requests/second
  - Memory: RSS before/after 1000 requests
  - Cost accuracy: estimated vs actual variance
- [ ] Publish benchmark report at `docs/integration/PERFORMANCE_REPORT.md`
- [ ] Cumulative degradation must be <10% vs pre-integration baseline (per strategy doc goal)
- [ ] If any degradation exceeds budget: document why, get stakeholder sign-off

### AC3: Documentation Completeness Check
- [ ] Automated doc check: `mkdocs build -W` passes with zero warnings
- [ ] Documentation checklist:
  - [ ] `docs/integration/architecture.md` — updated with actual (not planned) architecture
  - [ ] `docs/integration/migration_guide.md` — how to upgrade existing MR-Krabs installs
  - [ ] `docs/integration/troubleshooting.md` — common issues + solutions from integration experience
  - [ ] `docs/providers/` — one page per provider (Anthropic, Vertex, Mistral, DeepSeek, Groq)
  - [ ] `docs/dashboards/` — all Grafana dashboard JSONs + README
  - [ ] `docs/deploy/k8s/INSTALL.md` — verified with fresh cluster install
  - [ ] `docs/operator/ARCHITECTURE.md` — reviewed and polished
  - [ ] `CHANGELOG.md` — comprehensive, one section per phase
- [ ] Every public API function has docstring
- [ ] Every configuration key documented in TOML with comments

### AC4: Backward Compatibility Verification
- [ ] Full MR-Krabs test suite (28 integration + 10 E2E) passes with ALL feature flags OFF
- [ ] Full MR-Krabs test suite passes with ALL feature flags ON
- [ ] `ask()` API signature unchanged — existing callers work without modification
- [ ] Config file backward compatibility: old config files load with warnings, not errors
- [ ] Migration path tested: install old MR-Krabs → run workload → upgrade → same workload succeeds

### AC5: Release Artifacts
- [ ] `pyproject.toml` updated:
  - Version bump (to whatever version this is)
  - Optional dependency groups: `pip install mrkrabs[metrics,helm,providers,cache,tracing]`
  - All new dependencies declared with version pins
- [ ] Helm chart published: `helm package charts/mrkrabs/` → `helm push` to chart repo
- [ ] Docker image built and pushed: `mrkrabs:{version}` with all adapters included
- [ ] GitHub Release drafted with:
  - Changelog linking to each story
  - Migration notes (breaking changes? TBD)
  - Quickstart for each feature group
  - Known limitations (e.g., semantic cache is beta, Vertex requires GCP account)

### AC6: Security Review
- [ ] All forked components pass `pip-audit` (zero HIGH/CRITICAL)
- [ ] No API keys, tokens, or secrets in any committed file
- [ ] GitHub secret scanning enabled on repo — zero findings
- [ ] Dependency licenses reviewed: all compatible with MR-Krabs license
- [ ] Threat model: what new attack surfaces does the integration introduce? Document in `docs/security/INTEGRATION_THREAT_MODEL.md`

### AC7: Stakeholder Sign-Off
- [ ] Demo each phase to stakeholders: working dashboards, live routing, provider failover
- [ ] Budget impact analysis: estimated cost to run full stack (all adapters) vs. pre-integration
- [ ] Maintenance commitment: who owns forked LiteLLM code going forward, update cadence
- [ ] Decision: merge to `main` or keep on `integration/litellm` branch for soak period

---

## Technical Notes

- Performance benchmarks run on dedicated CI runner (not shared) to avoid noisy neighbors
- e2e tests tagged `@pytest.mark.e2e` — run separately from unit/integration (they're slow)
- External provider tests require GitHub Environments secrets — CI must be configured before this story starts
- The "all flags ON" test is critical — validates that adapters don't interfere with each other
- Consider a 2-week soak period after merge before tagging a release

---

## Definition of Done

- [ ] All 8 e2e test scenarios pass
- [ ] Performance benchmark report published, degradation <10%
- [ ] `mkdocs build -W` passes
- [ ] All documentation items checked off
- [ ] Backward compatibility verified (old test suite + migration test)
- [ ] Release artifacts ready: PyPI package, Helm chart, Docker image
- [ ] Security review clean
- [ ] Stakeholder demo completed, sign-off obtained
- [ ] CHANGELOG.md updated with links to all stories
