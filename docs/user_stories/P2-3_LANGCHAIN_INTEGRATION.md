# P2-3: LangChain Integration - Cost Tracking Callback

**Priority:** P1 (Important)  
**Estimate:** 4 days (Weeks 13-14)  
**User Story:** As a LangChain user, I want cost tracking to be automatically added to my LangChain apps with minimal code changes so I can monitor AI spending without refactoring my existing code.

## Context
LangChain is one of the most popular AI development frameworks. We need to provide a seamless integration that:
- Works via LangChain's callback system (no code changes needed)
- Integrates with LangSmith for cost visibility
- Supports all major LangChain patterns (agents, chains, tools)
- Provides detailed cost breakdowns per operation

## Technical Requirements

### 1. LangChain Cost Callback Handler
```python
from cost_orchestrator import LangChainCostCallback

# Existing LangChain code - no changes needed!
from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI

llm = OpenAI()
agent = initialize_agent([...], llm, agent=AGENT_TYPE_ZERO_SHOT)

# Add cost tracking by inserting callback
from langchain.callbacks import CallbackManager
callback_manager = CallbackManager([LangChainCostCallback()])
agent = initialize_agent([...], llm, agent=AGENT_TYPE_ZERO_SHOT, 
                         callback_manager=callback_manager)
```

**Requirements:**
- Implement `on_chain_start`, `on_chain_end` callbacks
- Implement `on_agent_action`, `on_agent_finish` callbacks  
- Implement `on_tool_start`, `on_tool_end` callbacks
- Track costs for all LangChain operations
- Support both sync and async operations

### 2. LangSmith Integration
- Send cost data to LangSmith traces
- Add custom cost attributes to traces
- Show cost breakdown in LangSmith UI
- Support LangSmith's cost reporting format

### 3. Tool Cost Tracking
- Automatically track cost for each LangChain tool execution
- Include cost in tool response metadata
- Log cost to both internal tracker and LangSmith
- Support custom tools and built-in tools

### 4. Tier Selection for LangChain
- Detect task complexity from LangChain prompts
- Auto-select optimal tier based on:
  - Prompt length
  - Number of steps in chain
  - Historical success rate for similar tasks
- Allow override via LangChain metadata

## Acceptance Criteria

### Functional Tests (All Must Pass)
1. ✅ Callback handler installs without errors
2. ✅ Costs tracked for simple chains
3. ✅ Costs tracked for agent workflows
4. ✅ Costs tracked for tool executions
5. ✅ LangSmith integration works correctly
6. ✅ Async operations supported
7. ✅ Cost breakdown shows per-operation details

### Integration Tests
1. ✅ Existing LangChain app adds cost tracking (zero code changes)
2. ✅ LangSmith shows cost data in traces
3. ✅ Multi-agent workflows tracked correctly
4. ✅ Chaining operations tracked correctly
5. ✅ Tool execution costs tracked correctly

### Performance
1. ✅ <3% performance overhead on LangChain workflows
2. ✅ No blocking on callback execution
3. ✅ Minimal memory footprint
4. ✅ Works with LangChain's batch operations

### Documentation
1. ✅ README section: "LangChain Integration"
2. ✅ Code examples: 3 different LangChain patterns
3. ✅ LangSmith integration guide
4. ✅ Troubleshooting for common issues

## Implementation Tasks

### Week 13 (Day 1-2)
- [ ] Study LangChain callback system
- [ ] Implement base callback handler
- [ ] Implement chain callbacks (start/end)
- [ ] Unit tests for chain tracking

### Week 13 (Day 3)
- [ ] Implement agent callbacks
- [ ] Implement tool callbacks
- [ ] Add cost calculation logic
- [ ] Unit tests for agent/tool tracking

### Week 14 (Day 1)
- [ ] Integrate with LangSmith
- [ ] Add custom attributes to traces
- [ ] Test LangSmith UI integration
- [ ] LangSmith documentation

### Week 14 (Day 2-3)
- [ ] Performance benchmarking
- [ ] Async operation support
- [ ] End-to-end testing
- [ ] Documentation completion

## Dependencies
- LangChain >= 0.1.0 (existing dependency)
- LangSmith account (for testing)
- Access to LLM providers for testing

## Risks & Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| LangChain API changes | Medium | Abstract callback layer, test multiple versions |
| LangSmith format changes | Low | Follow official docs, maintain compatibility |
| Performance overhead >3% | Low | Benchmark early, optimize callback execution |

## Success Metrics
- ✅ 5+ LangChain workflow examples with cost tracking
- ✅ <3% performance overhead on standard workflows
- ✅ Positive feedback from LangChain community
- ✅ Integration recommended in LangChain documentation

## Notes
- LangChain has massive adoption - this is critical for visibility
- Callback-based integration means zero code changes for users
- Must work with all LangChain patterns (agents, chains, tools)
- LangSmith integration provides professional-grade visibility
