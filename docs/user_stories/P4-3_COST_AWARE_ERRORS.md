# P4-3: Cost-Aware Error Handling

## Overview
Implement intelligent error handling that considers cost implications when deciding how to respond to API errors. Different errors have different cost-recovery strategies.

## Background
Currently, error handling is generic - certain errors trigger retries, others fail immediately. However, this doesn't consider:
- Cost of retrying vs. failing vs. escalating
- Whether the error is transient or permanent
- Budget implications of retry failures
- Opportunity cost of waiting for retries

## User Story
**As a** developer using the orchestrator  
**I want** error handling that considers cost implications  
**So that** I get optimal recovery strategies without unnecessary cost waste

## Acceptance Criteria

### AC1: Error Cost Classification
- [ ] Errors classified by cost recovery potential:
  - **Transient**: Retry immediately (network timeout, rate limit)
  - **Recoverable**: Retry with backoff (model busy, temporary error)
  - **Permanent**: Fail fast (invalid config, auth error)
  - **Escalatable**: Fail and escalate tier (model not supported)
- [ ] Default classification table documented

### AC2: Budget-Aware Error Response
- [ ] If budget < 20%, skip retries on recoverable errors
- [ ] If budget < 10%, fail immediately on transient errors
- [ ] Log budget-influenced error decisions
- [ ] Example: "[BUDGET ALERT 10%] Skipping retry for rate limit (budget too low)"

### AC3: Error-Specific Retry Strategies
- [ ] **RateLimitError**: Retry with longer backoff, max 3 attempts
- [ ] **TimeoutError**: Retry with exponential backoff, max 5 attempts
- [ ] **ModelBusy**: Retry with longer initial delay, max 3 attempts
- [ ] **AuthError**: Fail immediately (no point retrying)
- [ ] **InvalidModel**: Fail immediately, suggest alternative
- [ ] **NetworkError**: Retry with increasing delays, max 5 attempts

### AC4: Cost of Failure Tracking
- [ ] Track cost of each error type (retry costs, escalation costs)
- [ ] Track success rate after retries
- [ ] Track failed retry costs (total tokens spent before failure)

### AC5: Error Recovery Metrics
- [ ] Report error recovery metrics in `orchestrator stats`:
  - Error type distribution
  - Retry success rate
  - Average retry cost per error type
  - Failed retry costs
- [ ] Include in daily summary report

### AC6: Configurable Error Handling
- [ ] Configuration options:
  - `error_retry_limits`: dict of error types to max retries
  - `error_default_retries`: int for unspecified error types
  - `error_enable_budget_awareness`: bool (default: True)
- [ ] Defaults documented

## Implementation Plan

### Phase 1: Error Classification (1-2 days)
1. Create error cost classification system
2. Implement default error handling strategies
3. Add configuration schema

### Phase 2: Budget Integration (1 day)
1. Integrate with cost tracking for budget status
2. Implement budget-aware error responses
3. Add logging for decisions

### Phase 3: Metrics & Testing (1 day)
1. Add error recovery metrics
2. Unit tests for error classification
3. Integration tests for error handling

## Testing Requirements

### Unit Tests
- [ ] `test_error_cost_classification`
- [ ] `test_error_specific_retry_limits`
- [ ] `test_budget_aware_error_response`
- [ ] `test_configurable_error_handling`
- [ ] `test_error_recovery_metrics`

### Integration Tests
- [ ] End-to-end: Various errors → correct handling → correct metrics
- [ ] Verify budget-aware decisions when running low on budget

## Error Classification Reference

| Error Type | Classification | Retry Strategy | Max Retries |
|------------|---------------|----------------|-------------|
| RateLimitError | Transient | Exponential backoff | 3 |
| TimeoutError | Transient | Exponential backoff | 5 |
| ModelBusy | Recoverable | Long backoff | 3 |
| NetworkError | Transient | Increasing delays | 5 |
| AuthError | Permanent | Fail fast | 0 |
| InvalidModel | Permanent | Fail fast | 0 |
| BudgetExceededError | Permanent | Fail fast | 0 |

## Dependencies
- P4-1: Cost Alert System (for budget status)
- Core: error_classifier.py, cost.py, tier_manager.py

## Notes
- Error handling affects both cost and reliability
- This feature optimizes for cost while maintaining reliability
- Budget-aware decisions are logged for audit
