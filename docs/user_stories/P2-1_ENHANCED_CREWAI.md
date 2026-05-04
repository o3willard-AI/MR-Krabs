# P2-1: Enhanced CrewAI Integration - Cost-Aware Tools

**Priority:** P0 (Critical)  
**Estimate:** 5 days (Weeks 9-10)  
**User Story:** As a CrewAI user, I want my CrewAI tools to show cost information so I can track spending for each tool execution in my workflows.

## Context
Current CrewAI integration only wraps agents at a high level. We need deeper integration that:
- Shows cost for each tool execution
- Logs cost in CrewAI's native logging format
- Maintains compatibility with CrewAI's memory system

## Technical Requirements

### 1. Cost-Aware Tool Decorator
```python
from cost_orchestrator import cost_aware_tool

@cost_aware_tool
def search_web(query: str) -> str:
    return web_search(query)
```

**Requirements:**
- Automatically track tool execution cost
- Include cost in tool response metadata
- Support both OpenRouter and LM Studio providers
- Zero performance overhead (<1% cost)

### 2. CrewAI Memory Compatibility
- Ensure cost tracking doesn't interfere with CrewAI's memory system
- Store cost data separately from conversation memory
- Support both short-term and long-term memory modes

### 3. Advanced Tier Mapping
- Map CrewAI agent roles to cost tiers automatically:
  - "Researcher" → L0 (cheap)
  - "Planner" → L1 (medium)
  - "Coder" → L2 (expensive)
  - "Architect" → L3 (premium)
- Allow manual override via agent config
- Persist tier mapping in CrewAI agent metadata

### 4. Performance Optimization
- Batch cost logging when possible
- Minimize memory footprint
- No blocking on cost tracking
- <5% performance overhead on CrewAI workflows

## Acceptance Criteria

### Functional Tests (All Must Pass)
1. ✅ Tool executions show cost in CrewAI logs
2. ✅ Memory system works without cost tracking interference
3. ✅ Auto-tier mapping correctly assigns tiers based on agent role
4. ✅ Manual tier override works for all agent types
5. ✅ Cost data is logged in CrewAI's native format
6. ✅ Performance overhead <5% on benchmark CrewAI workflow

### Integration Tests
1. ✅ CrewAI agent with cost-aware tools completes workflow
2. ✅ Tool execution logs include cost information
3. ✅ Memory operations preserve cost tracking state
4. ✅ Tier changes mid-workflow are tracked correctly

### Documentation
1. ✅ README section: "Using Cost-Aware Tools with CrewAI"
2. ✅ Code examples: 3 different tool patterns
3. ✅ Troubleshooting guide for common issues
4. ✅ Performance benchmark results documented

### Code Quality
1. ✅ Type hints for all public APIs
2. ✅ Comprehensive docstrings
3. ✅ 90%+ unit test coverage for new code
4. ✅ No breaking changes to existing CrewAI integration

## Implementation Tasks

### Week 9 (Days 1-3)
- [ ] Design cost-aware tool decorator API
- [ ] Implement basic decorator with cost tracking
- [ ] Add metadata storage for cost data
- [ ] Unit tests for decorator functionality

### Week 9 (Days 4-5)
- [ ] Integrate with CrewAI tool execution flow
- [ ] Add cost logging to CrewAI log format
- [ ] Performance benchmarking setup
- [ ] Optimize for minimal overhead

### Week 10 (Days 1-3)
- [ ] Implement auto-tier mapping by agent role
- [ ] Add manual tier override support
- [ ] Persist tier mapping in agent metadata
- [ ] Unit tests for tier mapping logic

### Week 10 (Days 4-5)
- [ ] End-to-end testing with CrewAI workflow
- [ ] Performance validation (<5% overhead)
- [ ] Documentation creation
- [ ] Code review and cleanup

## Dependencies
- CrewAI >= 0.1.0 (existing dependency)
- OpenRouter API key (for testing)
- LM Studio (optional, for offline testing)

## Risks & Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| CrewAI API changes | Medium | Abstract integration layer, version pinning |
| Performance overhead >5% | Low | Benchmark early, optimize hot paths |
| Memory system conflicts | Medium | Test extensively with CrewAI memory features |

## Success Metrics
- ✅ 3+ CrewAI workflow examples demonstrating cost tracking
- ✅ <5% performance overhead on standard workflows
- ✅ Zero breaking changes to existing integrations
- ✅ Community adoption: 10+ external crewAI projects using feature

## Notes
- This is the most critical Phase 2 feature as CrewAI is the primary framework
- Must maintain backward compatibility with existing CrewAI integration
- Performance is critical - users won't adopt if it slows down their workflows
