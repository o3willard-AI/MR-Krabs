# P2-2: Superpowers Skill Implementation

**Priority:** P1 (Important)  
**Estimate:** 3 days (Weeks 11-12)  
**User Story:** As a Claude Code/OpenCode user, I want the MR-Krabs orchestrator to be available as a Superpowers skill so I can use it directly in my AI coding workflow.

## Context
Superpowers is a framework for AI coding assistants that provides structured skills. We need to create an official MR-Krabs skill that:
- Follows Superpowers skill format exactly
- Integrates with the brainstorming → planning → execution workflow
- Works with Claude Code, Cursor, OpenCode, and other Superpowers-compatible tools

## Technical Requirements

### 1. Superpowers Skill Format
```yaml
# mr-krabs.skill.yaml
name: cost-orchestrator
version: "1.0"
description: Cost-optimized AI orchestration for Claude Code
author: MR-Krabs Team
frameworks: [claude-code, cursor, opencode]
```

### 2. Skill Endpoints
Implement the following Superpowers skill endpoints:

**`/brainstorm`** - Generate task breakdown
- Input: Raw task description
- Output: Structured breakdown with cost estimates per step
- Use L0 tier for brainstorming

**`/plan`** - Create execution plan
- Input: Task breakdown
- Output: Step-by-step plan with tier assignments
- Use L1 tier for planning

**`/execute`** - Execute task with cost tracking
- Input: Execution plan + task details
- Output: Task results with cost breakdown
- Auto-select tier based on task complexity

### 3. Tier Selection Algorithm
```python
def select_tier_for_superpowers(task: str) -> TierLevel:
    """
    Map Superpowers task types to cost tiers:
    - Simple fixes → L0 (cheap)
    - Code generation → L1 (medium)
    - Architecture changes → L2 (expensive)
    - Complex refactoring → L3 (premium)
    """
```

### 4. Response Formatting
- Format outputs to match Superpowers expectations
- Include cost information in skill responses
- Support streaming for long-running tasks
- Handle errors gracefully with Superpowers error format

## Acceptance Criteria

### Functional Tests (All Must Pass)
1. ✅ Skill loads successfully in Claude Code
2. ✅ Skill loads successfully in Cursor
3. ✅ Skill loads successfully in OpenCode
4. ✅ `/brainstorm` endpoint returns valid breakdown
5. ✅ `/plan` endpoint returns valid plan
6. ✅ `/execute` endpoint returns valid results
7. ✅ Cost information included in all responses

### Integration Tests
1. ✅ End-to-end workflow: brainstorm → plan → execute
2. ✅ Tier selection works correctly for different task types
3. ✅ Cost tracking persists across skill endpoints
4. ✅ Error handling matches Superpowers error format

### Community Validation
1. ✅ Skill accepted by Superpowers maintainers
2. ✅ Featured in Superpowers skill directory
3. ✅ Documentation follows Superpowers best practices
4. ✅ 2+ Superpowers community members validate implementation

### Documentation
1. ✅ SKILL.md following Superpowers format exactly
2. ✅ README with installation instructions
3. ✅ Example usage in all supported frameworks
4. ✅ Contribution guidelines for future skill updates

## Implementation Tasks

### Week 11 (Day 1-2)
- [ ] Study Superpowers skill format documentation
- [ ] Create initial SKILL.md structure
- [ ] Implement `/brainstorm` endpoint
- [ ] Unit tests for brainstorm logic

### Week 11 (Day 3)
- [ ] Implement `/plan` endpoint
- [ ] Add tier selection algorithm
- [ ] Unit tests for planning logic

### Week 12 (Day 1)
- [ ] Implement `/execute` endpoint
- [ ] Integrate with existing cost orchestrator
- [ ] Add streaming support for long tasks

### Week 12 (Day 2)
- [ ] Test in Claude Code
- [ ] Test in Cursor
- [ ] Test in OpenCode
- [ ] Fix any compatibility issues

### Week 12 (Day 3)
- [ ] Submit to Superpowers community
- [ ] Create documentation
- [ ] Prepare for validation feedback

## Dependencies
- Superpowers skill format documentation
- Access to Claude Code for testing
- Access to Cursor for testing
- Access to OpenCode for testing
- Superpowers community contact for validation

## Risks & Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| Superpowers format changes | Low | Follow official docs, keep format flexible |
| Compatibility issues | Medium | Test in all 3 frameworks early |
| Community rejection | Low | Engage maintainers early, follow best practices |

## Success Metrics
- ✅ Skill accepted by Superpowers community
- ✅ Featured in Superpowers skill directory
- ✅ 50+ downloads in first week
- ✅ Positive feedback from 3+ Superpowers users

## Notes
- This is crucial for community adoption and visibility
- Must follow Superpowers format EXACTLY - no deviations
- Early engagement with Superpowers maintainers is critical
- Success here enables automatic distribution to 1000+ Superpowers users
