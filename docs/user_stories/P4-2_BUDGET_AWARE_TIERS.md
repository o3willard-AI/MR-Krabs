# P4-2: Budget-Aware Tier Management

## Overview
Enhance the tier management system to be aware of budget status and make intelligent tier selection decisions based on remaining budget and task complexity.

## Background
Currently, the tier selection is based primarily on task type and confidence, but doesn't consider the current budget status. This can lead to:
- Expensive models being selected when budget is running low
- Wasted budget on tasks that could be completed on cheaper tiers
- Missed cost optimization opportunities

## User Story
**As a** cost-conscious user  
**I want** the system to make budget-aware tier selection decisions  
**So that** I can optimize my costs and avoid running out of budget unexpectedly

## Acceptance Criteria

### AC1: Budget-Influenced Tier Selection
- [ ] System checks current budget status before tier selection
- [ ] If budget < 30% remaining, prefer cheaper models (L0/L1) for simple tasks
- [ ] If budget < 15% remaining, restrict to L0 for all tasks unless explicitly requested otherwise
- [ ] Budget status logged in tier selection decision

### AC2: Budget-Aware Tier Preferences Configuration
- [ ] Configuration options for budget-tier preferences:
  - `budget_tier_thresholds`: dict mapping budget percentages to preferred tiers
  - Example: `{0.3: "L0", 0.5: "L1", 0.8: "L2"}`
- [ ] Default preferences:
  - Budget > 80%: Use normal tier selection
  - Budget 50-80%: Prefer L1 for simple tasks
  - Budget 30-50%: Prefer L0 for simple tasks
  - Budget < 30%: Restrict to L0 unless forced
- [ ] Configuration validated on startup

### AC3: Budget Warnings with Tier Adjustments
- [ ] When budget warning triggered (e.g., 80%), log preferred tier adjustment
- [ ] Example log: "[BUDGET WARNING 80%] Adjusting tier preference: L2→L1 for simple tasks"
- [ ] Users can see tier adjustment decisions in logs

### AC4: Tier Adjustment Override Options
- [ ] CLI option `--force-tier <tier>` bypasses budget-aware selection
- [ ] API parameter `force_tier` bypasses budget-aware selection
- [ ] Override logged for audit purposes

### AC5: Tier Selection Logging
- [ ] Each tier selection includes budget status in log
- [ ] Format: "Selecting tier L1 (budget: 75% remaining, task type: simple)"
- [ ] Optional detailed logging of budget-influenced decisions

### AC6: Metrics Tracking
- [ ] Track how often budget-aware adjustments are applied
- [ ] Track cost savings from budget-aware selections
- [ ] Report in `orchestrator stats` output

## Implementation Plan

### Phase 1: Core Logic (1-2 days)
1. Modify `TierManager` to accept budget status
2. Implement budget-aware tier preference logic
3. Add configuration schema update

### Phase 2: Integration (1 day)
1. Integrate with `CostTracker` for budget status
2. Add CLI parameter for override
3. Add logging for decisions

### Phase 3: Testing & Documentation (1 day)
1. Unit tests for budget-aware logic
2. Integration tests
3. Update documentation

## Testing Requirements

### Unit Tests
- [ ] `test_budget_influenced_tier_selection`
- [ ] `test_budget_tier_thresholds_configuration`
- [ ] `test_default_budget_preferences`
- [ ] `test_budget_warnings_trigger_adjustments`
- [ ] `test_tier_override_mechanism`
- [ ] `test_tier_selection_logging`

### Integration Tests
- [ ] End-to-end: Budget depletion → tier adjustment → correct tier selection
- [ ] Verify logs show budget-aware decisions

## Metrics
- Track budget-aware adjustment frequency
- Calculate cost savings percentage
- Report in daily summary

## Dependencies
- P4-1: Cost Alert System (provides budget status)
- Core: TierManager, CostTracker, Config

## Notes
- This feature is primarily about cost optimization
- Doesn't change basic tier selection logic, only adds budget awareness
- Users can override via force-tier option
