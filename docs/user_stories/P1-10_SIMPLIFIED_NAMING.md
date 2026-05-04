# Story P1-10: Simplified Tier Naming

**Priority**: P2 (Medium)  
**Estimate**: 2 days  
**Phase**: Week 2

---

## User Story

As a new developer  
I want to use simple tier names like "cheap" instead of "L0-Coder"  
So that I don't need to understand the tier system upfront

---

## Acceptance Criteria

### AC1: Abstract Tier Names
- [ ] Support both old and new naming:
  - Old: "L0-Coder", "L1-Coder", "L2-Coder", "L3-Coder"
  - New: "cheap", "medium", "expensive", "premium"
- [ ] New names map to same models as old names
- [ ] Both names work interchangeably

### AC2: Automatic Mapping
- [ ] `cheap` → `L0-Coder` (free/local)
- [ ] `medium` → `L1-Coder` (cheap cloud)
- [ ] `expensive` → `L2-Coder` (mid-tier cloud)
- [ ] `premium` → `L3-Coder` (premium cloud)

### AC3: User-Friendly Defaults
- [ ] `orchestrator run --tier cheap` works without knowing model names
- [ ] `ask("task")` uses "cheap" tier by default
- [ ] Documentation uses new names primarily

### AC4: Backward Compatibility
- [ ] Old tier names still work
- [ ] No breaking changes to existing code
- [ ] Migration guide in docs

### AC5: Tier Separation Concept
- [ ] Documentation explains: cost tier ≠ task role
- [ ] Future: allow mixing (e.g., "cheap-Reviewer", "premium-Coder")
- [ ] Current: keep L0-Planner, L0-Coder, L0-Reviewer as special cases

---

## Technical Implementation

### Files to Create/Modify
1. `src/core/tier_manager.py` - Add alias mapping

### Implementation Details

```python
# src/core/tier_manager.py

# New alias mapping
TIER_ALIASES = {
    "cheap": "L0-Coder",
    "medium": "L1-Coder",
    "expensive": "L2-Coder",
    "premium": "L3-Coder",
}

def normalize_tier_name(tier: str) -> str:
    """Convert simplified names to actual tier names."""
    return TIER_ALIASES.get(tier.lower(), tier)
```

---

## Testing Requirements

### Unit Tests
1. `test_alias_cheap_maps_to_l0` - cheap → L0-Coder
2. `test_alias_medium_maps_to_l1` - medium → L1-Coder
3. `test_backward_compatibility` - L0-Coder still works
4. `test_normalize_tier_name_uppercase` - CHEAP → L0-Coder

---

## Out of Scope
- User-defined tier names
- Custom tier hierarchies

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass
- [ ] Documentation updated with new names
- [ ] Backward compatibility verified
