# Story P4-3: Cost-Aware Error Handling

**Priority**: P1 (High)
**Estimate**: 1 day
**Phase**: Week 4

## User Story

As a developer using MR-Krabs
I want error handling to be aware of cost and budget context
So that I can make smarter decisions about retrying vs. escalating vs. failing when errors occur

## Acceptance Criteria

### AC1: Error Classification by Cost Impact
- [ ] `ErrorClassifier` class exists in `src/classifiers/error_classifier.py`
- [ ] Classifies errors into categories: `RETRYABLE_LOW_COST`, `RETRYABLE_HIGH_COST`, `ESCALATE_IMMEDIATELY`, `STATIC_FAILURE`
- [ ] `classify_error()` method takes exception and returns `ErrorClassification` dataclass
- [ ] Classification considers: error type, message patterns, context, cost implications

### AC2: Budget-Aware Error Response Strategy
- [ ] `ErrorResponseStrategy` dataclass exists in `src/strategies/error_response.py`
- [ ] Strategy selection considers: error classification, current budget level, tier constraints
- [ ] `get_response_strategy()` method takes error classification and budget context
- [ ] Returns appropriate action: `retry_with_backoff`, `retry_with_escalation`, `immediate_escalation`, `fail_gracefully`
- [ ] Strategy includes parameters: max_retries, base_delay, jitter, escalate_after_retries

### AC3: Error-Specific Retry Configuration
- [ ] Retry configuration stored in `RetryConfig` dataclass in `src/config/retry.py`
- [ ] Supports: max_retries, base_delay, max_delay, exponential_backoff, jitter
- [ ] Different error types have different retry policies
- [ ] Budget status affects retry aggressiveness (conservative when budget is low)

### AC4: Error Recovery Metrics
- [ ] `ErrorMetrics` dataclass in `src/metrics/error_metrics.py`
- [ ] Tracks: total_errors, retries_attempted, escalations_triggered, recovery_success_rate
- [ ] Error metrics integrated with `ErrorClassifier` and `ErrorMetricsCollector`
- [ ] Error metrics included in `TaskMetrics` and overall cost report

### AC5: Integration with Existing Tier System
- [ ] Error escalation follows tier hierarchy (L0→L1→L2→L3)
- [ ] Budget awareness prevents expensive retries when budget is constrained
- [ ] Error response strategy respects per-task budget limits
- [ ] Failed recovery attempts trigger tier escalation if configured

## Technical Implementation

### Files to Create/Modify

1. **`src/classifiers/error_classifier.py`** (Create)
   - `ErrorClassification` dataclass: category, confidence, estimated_cost_impact, suggested_action
   - `ErrorClassifier` class with `classify_error()` method
   - Classification rules for common error types (API errors, timeouts, budget exceeded, etc.)

2. **`src/strategies/error_response.py`** (Create)
   - `ErrorResponseStrategy` dataclass: action, max_retries, base_delay, jitter, escalate_after_retries
   - `ErrorResponseStrategySelector` class with `get_response_strategy()` method
   - Budget-aware strategy selection logic

3. **`src/config/retry.py`** (Create)
   - `RetryConfig` dataclass: max_retries, base_delay, max_delay, exponential_backoff, jitter
   - Default retry configurations for different error categories
   - Budget-influenced retry configuration adjustment

4. **`src/metrics/error_metrics.py`** (Create)
   - `ErrorMetrics` dataclass: error_count, retry_count, escalation_count, recovery_rate, avg_recovery_time
   - `ErrorMetricsCollector` class for tracking error metrics
   - Integration with existing `MetricsCollector`

5. **`src/core/orchestrator.py`** (Modify)
   - Integrate error classification into task execution flow
   - Apply error response strategies in retry logic
   - Track error metrics during execution

6. **`src/core/tier_manager.py`** (Modify)
   - Support error-based tier escalation
   - Budget-aware tier selection during error recovery

7. **`src/__init__.py`** (Modify)
   - Export new classes and dataclasses
   - Update `ask()` API to use error-aware handling

### Testing Requirements

**Unit Tests:**
- `tests/unit/test_error_classifier_p4_3.py` - Test `ErrorClassifier` and `ErrorClassification`
- `tests/unit/test_error_response_strategies_p4_3.py` - Test strategy selection
- `tests/unit/test_retry_config_p4_3.py` - Test retry configuration
- `tests/unit/test_error_metrics_p4_3.py` - Test error metrics tracking
- `tests/unit/test_error_handling_integration_p4_3.py` - Integration tests

**Test Count Target**: ~25-30 tests total

**Verification Tests:**
- `tests/verify_p4_3_error_handling.py` - End-to-end verification script

### Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (25+ tests)
- [ ] Integration tests pass
- [ ] Code coverage >= 80% for new modules
- [ ] Error metrics integrated with existing metrics system
- [ ] Documentation updated (README, API docs)
- [ ] Example usage in README showing error handling scenarios

## Dependencies

- **P4-1**: Enhanced Cost Tracking (completed)
- **P4-2**: Budget-Aware Tier Management (completed)
- **Testing infrastructure** (existing from P1-12)

## Error Classification Categories

### `RETRYABLE_LOW_COST`
- Transient network errors (connection refused, timeout)
- Rate limiting errors (429) with retry-after header
- Temporary service unavailability (503)
- Characterized by: low estimated cost impact, high success rate on retry

### `RETRYABLE_HIGH_COST`
- Model context window exceeded
- Token limit errors
- Complex API errors that may succeed on retry
- Characterized by: moderate cost impact, variable success rate

### `ESCALATE_IMMEDIATELY`
- Budget exceeded errors
- Invalid API key / authentication failures
- Model not found / configuration errors
- Characterized by: high cost if retried, low success rate

### `STATIC_FAILURE`
- Invalid input format
- Prompt too long for model
- Unsupported model parameters
- Characterized by: zero success rate on retry, no value in retrying

## Budget-Aware Retry Policy

When budget is:
- **> 80% remaining**: Aggressive retries (max_retries=5, base_delay=1s)
- **50-80% remaining**: Moderate retries (max_retries=3, base_delay=2s)
- **< 50% remaining**: Conservative retries (max_retries=1, base_delay=5s)
- **< 20% remaining**: Minimal retries (max_retries=0, immediate escalation)

## Metrics to Track

```python
ErrorMetrics = {
    "error_count": int,           # Total errors encountered
    "retry_count": int,           # Total retries attempted
    "escalation_count": int,      # Times escalation was triggered
    "recovery_success_rate": float,  # % of errors recovered successfully
    "avg_recovery_time_seconds": float,  # Average time to recover from error
    "error_type_breakdown": dict, # Count by error category
    "budget_impact": float,       # Total cost from error recovery attempts
}
```

## Notes

- Error classification should be extensible - allow users to add custom rules
- Consider integration with observability tools (OpenTelemetry, Datadog) for future
- Error recovery metrics should be visible in CLI `stats` command
- Test error handling with various simulated error conditions
