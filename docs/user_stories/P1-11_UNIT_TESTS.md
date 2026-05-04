# Story P1-11: Unit Tests >85% Coverage

**Priority**: P1 (High)  
**Estimate**: 3 days  
**Phase**: Week 7-8

---

## User Story

As a developer  
I want comprehensive unit tests with >85% code coverage  
So that I can trust the codebase and make changes safely

---

## Acceptance Criteria

### AC1: Test Coverage Threshold
- [ ] Overall coverage: >85%
- [ ] Core modules coverage: >90% (orchestrator.py, cost.py)
- [ ] CLI coverage: >80%
- [ ] Test files excluded from coverage calculation

### AC2: Test Structure
- [ ] `tests/unit/` - Unit tests for each module
- [ ] `tests/integration/` - Integration tests
- [ ] `tests/e2e/` - End-to-end tests
- [ ] `tests/benchmarks/` - Performance benchmarks

### AC3: Test Categories
- [ ] **Unit Tests**: Mock external dependencies, test single functions
- [ ] **Integration Tests**: Test module interactions (orchestrator + cost)
- [ ] **End-to-End Tests**: Real API calls (optional API key required)
- [ ] **Concurrency Tests**: Race condition verification
- [ ] **Performance Tests**: Benchmark overhead

### AC4: Test Quality
- [ ] Each test has single, clear purpose
- [ ] Tests are deterministic (no randomness)
- [ ] Tests are isolated (no shared state)
- [ ] Fast execution (<1 second per test)
- [ ] Meaningful assertions with clear error messages

### AC5: Continuous Integration
- [ ] GitHub Actions workflow runs tests on push/PR
- [ ] Fails build if coverage <85%
- [ ] Fails build if any test fails
- [ ] Coverage report uploaded as artifact

---

## Technical Implementation

### Files to Create

```
tests/
├── unit/
│   ├── test_cost.py           # CostTracker tests
│   ├── test_orchestrator.py   # LLMOrchestrator tests
│   ├── test_tier_manager.py   # TierManager tests
│   ├── test_config.py         # ConfigManager tests
│   └── test_exceptions.py     # Custom exceptions tests
├── integration/
│   ├── test_cost_integration.py
│   ├── test_auto_escalation.py
│   └── test_cli_integration.py
├── e2e/
│   └── test_full_workflow.py
├── benchmarks/
│   └── test_benchmarks.py
├── conftest.py               # Pytest fixtures
└── mocks/                    # Mock LLM responses
    ├── mock_responses.py
    └── mock_api.py
```

---

## Testing Requirements

### Critical Test Scenarios

1. **Budget Enforcement**
   - Reserve, finalize, release
   - Budget exceeded scenarios
   - Race conditions (concurrent requests)

2. **Escalation Logic**
   - Escalates on failure
   - Stops on success
   - Respects budget limits

3. **Cost Calculation**
   - Decimal accuracy
   - Token counting
   - Cost accumulation

4. **CLI Commands**
   - All commands execute
   - Exit codes correct
   - Output format correct

5. **Error Handling**
   - API errors caught
   - Timeout handling
   - Invalid config handling

---

## Out of Scope
- UI testing (no web UI in Phase 1)
- Load testing at scale (Phase 3)
- Security penetration testing

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Coverage >85%
- [ ] All tests pass
- [ ] CI/CD pipeline configured
- [ ] Tests run in <2 minutes total

---

## Tools to Use
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking
- `freezegun` - Time control for tests
