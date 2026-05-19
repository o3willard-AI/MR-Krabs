# Story P3-0c: Integration Test Harness

**Priority:** P1 (High — gates all future phase testing)
**Estimate:** 3 days
**Phase:** Phase 0 — Week 1

---

## User Story

As a **developer** integrating LiteLLM components,
I want an isolated integration test harness that validates each forked component independently
So that I can catch regressions early and prove each component works without touching the full MR-Krabs stack.

---

## Acceptance Criteria

### AC1: Isolated Test Environment
- [ ] Create `tests/integration_litellm/` directory structure:
  ```
  tests/integration_litellm/
  ├── conftest.py              # Shared fixtures: mock core, mock vault, mock config
  ├── phase_0/                 # Harness self-tests
  │   └── test_harness.py      # Verify harness works
  ├── phase_1/                 # Observability tests
  │   ├── test_metrics.py
  │   └── test_cost_utils.py
  ├── phase_2/                 # Routing tests
  │   ├── test_smart_router.py
  │   └── test_circuit_breaker.py
  ├── phase_3/                 # Deployment tests
  │   └── test_helm.py
  ├── phase_4/                 # Provider tests
  │   └── test_providers.py
  └── phase_5/                 # Advanced feature tests
      ├── test_tracing.py
      └── test_cache.py
  ```
- [ ] Each phase directory has its own `conftest.py` if phase-specific fixtures are needed
- [ ] Tests run with: `pytest tests/integration_litellm/phase_X/ -v`

### AC2: Mock Core for Isolation
- [ ] Implement `MockMrKrabsCore` in shared conftest:
  - Mock `ask()` that returns configurable responses
  - Mock vault that returns fake encrypted credentials
  - Mock tier manager with controllable escalation outcomes
  - Mock session manager with no-op persistence
- [ ] No real API keys or network calls in Phase 0–2 tests
- [ ] Phase 4 tests may use real provider sandbox keys (explicitly flagged with `@pytest.mark.external`)

### AC3: Harness Self-Validation
- [ ] `tests/integration_litellm/phase_0/test_harness.py`:
  - Verifies MockCore is importable and functional
  - Verifies adapter base class can be instantiated with mock config
  - Verifies registry accepts and retrieves mock adapters
  - Verifies feature flag toggles correctly enable/disable adapters
  - Smoke test: create a mock adapter → register → health_check → shutdown (no real deps)

### AC4: Test Coverage Targets
- [ ] Phase 0 harness self-tests: 95% coverage (enforced by `--cov-fail-under=95`)
- [ ] All subsequent phases documented with their coverage targets
- [ ] CI blocks merge if coverage drops below phase target
- [ ] Coverage report generated per-phase: `pytest --cov=src/adapters --cov-report=html`

### AC5: CI Integration Ready
- [ ] Tests discoverable by `pytest tests/integration_litellm/ -m "not external"` (default run)
- [ ] External tests gated behind `-m external` and require `LITELLM_TEST_API_KEY` env var
- [ ] Each phase testable independently: `pytest tests/integration_litellm/phase_2/`

---

## Technical Notes

- Use `pytest` fixtures with `scope="module"` for shared mock setup — avoid re-initializing mocks per test
- Mock config follows the TOML structure from P3-0b AC3
- External test marker registered in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  markers = ["external: tests requiring real API calls"]
  ```
- Do NOT mock `LiteLLMAdapter` — test real adapter implementations against mock core, not mock adapters

---

## Definition of Done

- [ ] Directory structure created and committed
- [ ] `MockMrKrabsCore` implemented and reusable across all phases
- [ ] Harness self-tests pass (`pytest tests/integration_litellm/phase_0/ -v --cov-fail-under=95`)
- [ ] CI workflow file created (see P3-0d)
- [ ] README in `tests/integration_litellm/` explaining how to run per-phase
