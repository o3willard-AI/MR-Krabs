# MCP Server Test Plan

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: In Progress

---

## Current Test Coverage Status

### Summary
- **Total Tests**: 214 (207 pass + 7 fail)
- **Pass Rate**: 96.7% (after fixes)
- **Coverage Goal**: 85%+ for core MCP modules

### Test Files Overview

| File | Purpose | Status | Count |
|------|---------|--------|-------|
| `test_server.py` | Server endpoints & health checks | ✅ Passing | 26 |
| `test_mcp_cost_tools.py` | Cost estimation, budget check, tracking | ✅ Passing | 34 |
| `test_budget_enforcer.py` | Budget enforcement logic | ⚠️ 2 failing | 28 |
| `test_session_manager.py` | Session lifecycle management | ⚠️ 5 failing | 35 |
| `test_exports.py` | CSV/JSON export functionality | ❌ Not implemented | - |
| `test_mcp_integration.py` | End-to-end integration tests | ✅ Passing | 12 |
| `test_mcp_crew_analytics.py` | CrewAI + analytics integration | ✅ Passing | 8 |
| `test_mcp_load.py` | Concurrent session load testing | ❌ Not implemented | - |

---

## Immediate Fixes Required (7 failing tests)

### Bug #1: BudgetEnforcer Default Values Not Set
**File**: `tests/mcp/test_budget_enforcer.py::TestBudgetEnforcerInit::test_default_values`  
**Issue**: `budget_limit` is `None` instead of `10.0`  
**Root Cause**: `__init__` not setting default properly

### Bug #2: Zero Budget Division Error
**File**: `tests/mcp/test_budget_enforcer.py::TestEdgeCases::test_zero_budget`  
**Issue**: `ZeroDivisionError` when budget_limit is 0  
**Root Cause**: No guard against zero division in percentage calculation

### Bug #3: Session ID Length Mismatch
**File**: `tests/mcp/test_session_manager.py::TestSessionManager::test_create_session_default`  
**Issue**: Session ID is 16 chars, test expects 17  
**Root Cause**: Either test expectation or generation logic wrong

### Bugs #4-7: Session Expiration Logic Not Working
**Files**: 
- `test_session_expiration`
- `test_session_auto_cleanup_on_access`
- `test_list_sessions_filters_expired`
- `test_cleanup_expired`

**Issue**: Sessions not expiring when they should  
**Root Cause**: Time comparison or cleanup logic broken

---

## Test Implementation Plan

### Phase 1: Fix Existing Failures (2 hours)
**Goal**: Get all tests passing

**Tasks:**
1. ✅ Fix `BudgetEnforcer.__init__` default values
2. ✅ Add zero budget guard in percentage calculation
3. ✅ Fix session ID length or test expectation
4. ✅ Debug and fix session expiration logic
5. ✅ Verify all 214 tests pass

---

### Phase 2: Complete Export Tests (2 hours)
**Goal**: Test CSV/JSON export functionality

**File to Create**: `tests/mcp/test_exports_complete.py`

**Test Cases:**
```python
class TestExportCSV:
    def test_export_csv_creates_file()
    def test_export_csv_has_correct_columns()
    def test_export_csv_filters_by_period()
    def test_export_csv_handles_empty_data()
    def test_export_csv_with_session_filter()

class TestExportJSON:
    def test_export_json_returns_dict()
    def test_export_json_has_metadata()
    def test_export_json_includes_records()
    def test_export_json_period_validation()
```

---

### Phase 3: Load Testing (2 hours)
**Goal**: Verify concurrent session handling

**File to Create**: `tests/mcp/test_load_concurrent.py`

**Test Cases:**
```python
class TestConcurrentSessions:
    def test_10_concurrent_sessions()
    def test_50_concurrent_budget_checks()
    def test_session_cleanup_under_load()
    def test_no_race_conditions_in_budget_tracking()

class TestStress:
    def test_rapid_session_create_close()
    def test_memory_does_not_leak()
```

---

### Phase 4: Integration Tests Expansion (2 hours)
**Goal**: End-to-end workflows with real scenarios

**File to Update**: `tests/mcp/test_mcp_integration.py`

**Add Test Cases:**
```python
def test_full_crew_workflow_with_budget_enforcement()
def test_cost_tracking_across_multiple_sessions()
def test_analytics_after_crew_execution()
def test_export_contains_crew_costs()
```

---

### Phase 5: Edge Cases & Error Handling (2 hours)
**Goal**: Comprehensive error path coverage

**Test Scenarios:**
- Invalid JSON requests
- Missing required fields
- Budget exceeded in all modes
- Session not found errors
- Rate limiting triggers
- Authentication failures (when enabled)

---

## Test Coverage Goals by Module

| Module | Target Coverage | Current | Actions Needed |
|--------|----------------|---------|----------------|
| `src/mcp/server.py` | 85% | ~74% | Add error handling tests |
| `src/mcp/session_manager.py` | 90% | ~65% | Fix expiration, add edge cases |
| `src/mcp/budget_enforcer.py` | 95% | ~80% | Fix defaults, zero budget case |
| `src/mcp/cost_tools.py` | 90% | ~88% | Add more model pricing tests |
| `src/mcp/crew_tools.py` | 85% | ~82% | Add CrewAI failure scenarios |
| `src/mcp/analytics_tools.py` | 85% | ~75% | Complete export functionality tests |

---

## Running Tests

### Full Test Suite
```bash
cd /home/sblanken/working/code/MR-Krabs
PYTHONPATH=/home/sblanken/working/code/MR-Krabs:$PYTHONPATH pytest tests/mcp/ -v
```

### Specific File
```bash
PYTHONPATH=/home/sblanken/working/code/MR-Krabs:$PYTHONPATH pytest tests/mcp/test_server.py -v
```

### With Coverage Report
```bash
PYTHONPATH=/home/sblanken/working/code/MR-Krabs:$PYTHONPATH pytest tests/mcp/ --cov=src.mcp --cov-report=term-missing
```

### Quick Smoke Test
```bash
PYTHONPATH=/home/sblanken/working/code/MR-Krabs:$PYTHONPATH pytest tests/mcp/test_server.py::TestHealthEndpoints -v
```

---

## Test Environment Setup

### Required Environment Variables
```bash
export PYTHONPATH=/home/sblanken/working/code/MR-Krabs:$PYTHONPATH
export OPENROUTER_API_KEY=test_key_for_testing  # If testing real API calls
```

### Dependencies
```bash
pip install pytest pytest-cov pytest-asyncio httpx crewai
```

---

## Next Steps

1. **Immediate**: Fix 7 failing tests (Phase 1)
2. **Today**: Complete export tests (Phase 2)
3. **This Week**: Load testing + integration expansion (Phases 3-4)
4. **Ongoing**: Maintain >85% coverage on all PRs

---

**Last Updated**: May 7, 2026  
**Test Count**: 214 (target: 250+)
