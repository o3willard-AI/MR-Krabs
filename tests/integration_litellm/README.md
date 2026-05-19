# Integration Test Harness for LiteLLM Adapters

This directory contains isolated integration tests for MR-Krabs LiteLLM fork adapters. Each phase validates specific adapter functionality using a mock core that provides controllable responses, vault data, budget tracking, and tier escalation logic.

## Directory Structure

```
tests/integration_litellm/
├── __init__.py               # empty
├── conftest.py               # shared fixtures: mock core, mock config
├── phase_0/
│   ├── __init__.py           # empty
│   └── test_harness.py       # harness self-tests (run first)
├── phase_1/
│   ├── __init__.py           # empty
│   ├── test_metrics.py       # placeholder — will be filled in Phase 1
│   └── test_cost_utils.py    # placeholder — will be filled in Phase 1
├── phase_2/
│   ├── __init__.py           # empty
│   ├── test_smart_router.py  # placeholder
│   └── test_circuit_breaker.py # placeholder
├── phase_3/
│   ├── __init__.py           # empty
│   └── test_helm.py          # placeholder
├── phase_4/
│   ├── __init__.py           # empty
│   └── test_providers.py     # placeholder
└── phase_5/
    ├── __init__.py           # empty
    ├── test_tracing.py       # placeholder
    └── test_cache.py         # placeholder
```

## Running Tests

### Run all integration tests:
```bash
cd /home/sblanken/workspace/MR-Krabs
python -m pytest tests/integration_litellm/ -v
```

### Run a specific phase:
```bash
# Phase 0 (harness self-tests) — REQUIRED GATE
python -m pytest tests/integration_litellm/phase_0/test_harness.py -v

# Phase 1 (metrics/cost utilities)
python -m pytest tests/integration_litellm/phase_1/ -v

# Phase 2 (smart router/circuit breaker)
python -m pytest tests/integration_litellm/phase_2/ -v

# etc...
```

### Skip external tests (tests requiring real API calls):
```bash
python -m pytest tests/integration_litellm/ -m "not external" -v
```

## How It Works

1. **Mock Core**: `conftest.py` provides `MockMrKrabsCore` that simulates MR-Krabs core behavior with controllable responses, errors, budget, and vault data.

2. **Feature Flags**: Each phase enables/disables specific features via config fixtures (e.g., `mock_config_with_metrics`, `mock_config_with_router`).

3. **Isolated Testing**: Tests don't require real LLM APIs — they use the mock core to simulate responses and track behavior.

4. **Phase Progression**:
   - Phase 0: Validates harness itself (must pass before proceeding)
   - Phases 1-5: Each phase validates adapters for that specific functionality

## Notes

- Each phase's tests test the corresponding phase's adapters when they are implemented.
- Placeholder tests (`test_placeholder`) in phases 1-5 are minimal tests that pass until actual adapter code is implemented.
- The harness self-tests in `phase_0/test_harness.py` are the gate for all future phases — they must pass before any integration test work proceeds.
