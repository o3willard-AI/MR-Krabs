# Story P2-2: LangChain Integration

**Priority**: P0 (Critical - Blocks P2-5)  
**Estimate**: 2 weeks  
**Phase**: Weeks 11-12

---

## User Story

As a LangChain user  
I want automatic cost tracking for my LangChain chains and agents  
So that I can use LangChain without worrying about AI costs and get detailed cost analytics

---

## Acceptance Criteria

### AC1: Callback Handler for Cost Tracking

- [ ] `LangChainCallbackHandler` tracks all LangChain events
- [ ] Tracks LLM calls, tool calls, chain starts/completion
- [ ] Records cost for each event
- [ ] Integrates seamlessly with existing LangChain code
- [ ] No configuration required beyond initialization

### AC2: Agent Integration

- [ ] LangChain agents work with cost tracking
- [ ] Agent actions tracked individually
- [ ] Agent thoughts/messages don't trigger false costs
- [ ] Multi-step agents properly costed
- [ ] Agent memory compatible with cost tracking

### AC3: Tool Integration

- [ ] LangChain tools show cost in execution logs
- [ ] Tool costs aggregated in `orchestrator stats`
- [ ] Tools respect budget limits
- [ ] Tool failures handled correctly
- [ ] Tool cost summaries by type

### AC4: LangSmith Compatibility

- [ ] Costs appear in LangSmith traces
- [ ] Cost metadata in LangSmith dashboards
- [ ] Compatible with LangSmith cost features
- [ ] Export costs with LangSmith data
- [ ] Visual cost breakdown in LangSmith

### AC5: Popular Pattern Support

- [ ] Standard chains work (Sequential, LLMChain)
- [ ] Agent workflows supported
- [ ] Retrieval chains compatible
- [ ] Multi-modal chains supported
- [ ] Custom chains documented

### AC6: Error Handling

- [ ] Errors don't break cost tracking
- [ ] Partial costs recorded on failure
- [ ] Clear error messages with cost context
- [ ] Budget errors handled gracefully
- [ ] Recovery possible after errors

---

## Technical Implementation

### Files to Create/Modify

1. `src/integrations/langchain_callback.py` - LangChain callback handler
2. `src/integrations/langchain_tools.py` - Cost-aware LangChain tools
3. `src/core/cost.py` - Extend for LangChain tracking
4. `docs/user_stories/P2-2_LANGCHAIN_INTEGRATION.md` - This story

### Implementation Plan

```python
# src/integrations/langchain_callback.py

from langchain.callbacks.base import BaseCallbackHandler, BaseCallbackManager
from langchain.schema import LLMResult
from src.core.cost import CostTracker, Budget, TokenCount

class LangChainCostCallbackHandler(BaseCallbackHandler):
    """Callback handler for LangChain cost tracking."""
    
    def __init__(self, budget: Budget | None = None):
        self.cost_tracker = CostTracker(budget=budget)
        self.active_runs: dict[str, str] = {}  # run_id -> scope
        
    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        """Record LLM call start."""
        prompt = prompts[0] if prompts else ""
        scope = f"llm-{kwargs.get('run_id', 'unknown')}"
        
        # Reserve budget
        estimated_tokens = len(prompt) // 4
        estimated_cost = Decimal(str(estimated_tokens * 0.000001))
        
        try:
            reservation = self.cost_tracker.reserve_budget(
                scope=scope,
                estimated_cost=estimated_cost
            )
            self.active_runs[kwargs['run_id']] = reservation.id
        except BudgetExceededError:
            raise
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Record LLM call end with cost."""
        run_id = kwargs.get('run_id')
        if run_id not in self.active_runs:
            return
        
        reservation_id = self.active_runs.pop(run_id)
        
        # Calculate actual cost
        token_count = self._extract_tokens(response)
        actual_cost = self.cost_tracker.calculate_cost(
            model=response.llm_output['model_name'],
            tokens=token_count
        )
        
        # Finalize cost
        self.cost_tracker.finalize_spending(reservation_id, actual_cost)
        
        # Log cost
        print(f"[LangChain] {response.llm_output['model_name']}: "
              f"${float(actual_cost):.4f} ({token_count.total_tokens} tokens)")
    
    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Record tool call start."""
        scope = f"tool-{kwargs.get('run_id', 'unknown')}"
        
        # Small reservation for tool
        reservation = self.cost_tracker.reserve_budget(
            scope=scope,
            estimated_cost=Decimal("0.001")
        )
        self.active_runs[kwargs['run_id']] = reservation.id
    
    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Record tool call end with cost."""
        run_id = kwargs.get('run_id')
        if run_id not in self.active_runs:
            return
        
        reservation_id = self.active_runs.pop(run_id)
        
        # Estimate cost based on output
        tokens = len(output) // 4
        cost = Decimal(str(tokens * 0.000001))
        
        self.cost_tracker.finalize_spending(reservation_id, cost)
        print(f"[LangChain Tool] ${float(cost):.4f}")
    
    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any
    ) -> None:
        """Record chain start."""
        # Just track, no cost reservation needed for chains
        self.active_runs[kwargs['run_id']] = "chain"
    
    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Record chain end."""
        self.active_runs.pop(kwargs.get('run_id'), None)
    
    def _extract_tokens(self, response: LLMResult) -> TokenCount:
        """Extract token counts from LLMResult."""
        token_count = TokenCount()
        
        for generations in response.generations:
            for generation in generations:
                if hasattr(generation, 'text') and generation.text:
                    token_count.prompt_tokens += len(generation.text) // 4
                    token_count.completion_tokens += len(generation.text) // 4
        
        return token_count
```

### Integration Examples

```python
# Example 1: Basic LangChain integration
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.llms import OpenAI
from src.integrations.langchain_callback import LangChainCostCallbackHandler
from langchain.callbacks import CallbackManager

# Create callback handler
handler = LangChainCostCallbackHandler(budget=Budget(daily_limit_usd=10.0))

# Create chain with callback
prompt = PromptTemplate.from_template("What is {topic}?")
chain = LLMChain(
    llm=OpenAI(),
    prompt=prompt,
    callback_manager=CallbackManager([handler])
)

# Run chain
result = chain.run("AI cost optimization")
print(f"Total cost: ${handler.cost_tracker.get_daily_total():.2f}")
```

```python
# Example 2: LangChain agent
from langchain.agents import initialize_agent, AgentType

handler = LangChainCostCallbackHandler()

agent = initialize_agent(
    tools=[web_search_tool, file_tool],
    llm=OpenAI(),
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    callback_manager=CallbackManager([handler])
)

agent.run("What's the latest AI cost data?")
print(f"Agent cost: ${handler.cost_tracker.get_daily_total():.2f}")
```

```python
# Example 3: LangSmith integration
import langsmith

langsmith.traceable(handler=handler)(my_chain_function)
```

---

## Testing Requirements

### Unit Tests (test_langchain_callback.py)

1. `test_llm_call_tracking` - LLM calls tracked correctly
2. `test_tool_call_tracking` - Tool calls tracked correctly
3. `test_chain_tracking` - Chains tracked without cost
4. `test_token_extraction` - Token counts extracted accurately
5. `test_budget_enforcement` - Budget limits enforced in LangChain
6. `test_error_handling` - Errors don't break tracking

### Integration Tests

1. Real LangChain chain with OpenAI
2. LangChain agent with tools
3. LangSmith integration verified
4. Memory operations tested
5. Complex workflows tested

---

## Out of Scope

- LangChain framework changes (this is additive)
- LangChain CLI integration (separate)
- Native LangChain cost features (external tracking)
- LangChain-specific optimizations

---

## Dependencies

- P1 complete (core cost tracking)
- P2-1 complete (CrewAI integration patterns)
- LangChain framework accessible for testing
- LangSmith account for integration testing

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Callback Overhead** | <3% |
| **Token Extraction** | <1ms |
| **Memory Impact** | None |
| **Concurrent Chains** | No degradation |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] LangSmith compatibility verified
- [ ] Documentation updated
- [ ] Example project included
- [ ] Code reviewed by LangChain community member (preferred)

---

## Success Metrics

- **Adoption**: 5+ production LangChain apps using cost tracking
- **Compatibility**: Works with all major LangChain patterns
- **Community**: Integration with LangSmith documented
- **Performance**: <3% overhead verified

---

*Draft: April 26, 2026*
