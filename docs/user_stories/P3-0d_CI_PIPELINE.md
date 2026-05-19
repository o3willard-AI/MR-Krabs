# Story P3-0d: CI/CD Pipeline for LiteLLM Integration

**Priority:** P0 (Critical — enforces quality gates from day one)
**Estimate:** 2 days
**Phase:** Phase 0 — Week 1

---

## User Story

As a **developer** integrating LiteLLM components,
I want an automated CI pipeline that runs integration tests, coverage checks, and security scans on every push
So that regressions are caught immediately and quality gates are enforced without manual oversight.

---

## Acceptance Criteria

### AC1: GitHub Actions Workflow — Integration Tests
- [ ] Create `.github/workflows/integration-litellm.yml`:
  ```yaml
  name: LiteLLM Integration
  on:
    push:
      paths:
        - 'src/adapters/**'
        - 'src/metrics/**'
        - 'tests/integration_litellm/**'
    pull_request:
      paths:
        - 'src/adapters/**'
        - 'src/metrics/**'
        - 'tests/integration_litellm/**'
  ```
- [ ] Workflow runs on `ubuntu-latest`, Python 3.11+
- [ ] Phase 0 tests run first (gating job — if it fails, nothing else runs)
- [ ] Phase 1–2 tests run in parallel after Phase 0 passes
- [ ] Each phase produces its own coverage report artifact

### AC2: Quality Gates
- [ ] Coverage gate per phase enforced in CI:
  - Phase 0: `--cov-fail-under=95`
  - Phase 1: `--cov-fail-under=85`
  - Phase 2: `--cov-fail-under=90`
  - Phase 3: `--cov-fail-under=80`
- [ ] PR status check blocks merge if any phase fails
- [ ] Coverage diff comment on PR: "Phase 1 coverage: 87% (+2.1% vs main)"

### AC3: Security Scanning
- [ ] Add `pip-audit` step to CI workflow:
  - Runs on every push to integration branches
  - Fails build on any HIGH or CRITICAL vulnerability
  - Outputs audit report as CI artifact
- [ ] Add dependency hash verification:
  - `pip-compile --generate-hashes` runs on schedule (weekly)
  - PR opened automatically if hashes change
- [ ] Secret scanning: ensure no API key patterns in committed code (GitHub secret scanning enabled on repo)

### AC4: Performance Regression Detection
- [ ] Add performance baseline test (Phase 0 only):
  - Measure `ask()` round-trip time (100 iterations, mock responses)
  - Store baseline in CI artifacts
- [ ] Per-phase performance gate:
  - Measure same benchmark after each phase implementation
  - Fail if degradation > 5% per phase (cumulative < 30% by Phase 5)
  - Results published as PR comment

### AC5: Existing Test Suite Protection
- [ ] Full MR-Krabs test suite (28 integration + 10 E2E) runs on every push
- [ ] Must pass with all LiteLLM feature flags OFF
- [ ] Any breakage in existing tests blocks merge regardless of integration test status

---

## Technical Notes

- Use `actions/setup-python@v5` for Python setup
- Cache pip dependencies: `actions/cache@v4` with key based on `pyproject.toml` hash
- Use `concurrency` group to cancel redundant CI runs on same PR
- Phase 4+ external tests use GitHub Environments secrets, not repo secrets
- Schedule weekly dependency audit: `0 6 * * 1` (Monday 6 AM UTC)

---

## Definition of Done

- [ ] `.github/workflows/integration-litellm.yml` committed and triggered
- [ ] Phase 0 CI job passes (green check on this PR)
- [ ] Coverage report uploaded as artifact
- [ ] Security scan step runs without errors
- [ ] Full MR-Krabs test suite passes in same CI run
- [ ] PR comment template for coverage/perf diff ready
